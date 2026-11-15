"""Train the tiny U-Net field-edge model (boundary + interior logits) for tap-to-detect (EXP-12).

Data: windows from build_windows.py (open orthophotos of FR/ES/NL/AT + FTW labels), resampled exactly as at
inference (Lanczos to ~2.7 m). Loss is masked to the chip footprint and to <= 8 px from a labelled field.
Export: BatchNorm folded into the convolutions, float16 arrays -> backend/fieldshift/models/fieldedge.npz,
evaluated in numpy by fieldshift/science/fieldedge.py (checked against torch: max |diff| 0.0015).

    TAG=final STEPS=16000 python train_edge.py                          # all four countries
    COUNTRIES=france,spain TAG=A STEPS=10000 python train_edge.py       # cross-fit model for selector.py
Env: CH (channels, default 16,32,64,128), STEPS, COUNTRIES, TAG. Needs torch + a CUDA GPU (~4 min on an RTX 5070 Ti).
"""

import glob
import os
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F  # noqa: N812
from PIL import Image
from scipy import ndimage

torch.backends.cudnn.benchmark = True
B = os.path.expanduser("~/fd_bench")
CH = tuple(int(c) for c in os.environ.get("CH", "16,32,64,128").split(","))
TARGET_M = 2.7


def prep_window(f):
    d = np.load(f)
    img, pxm = d["img"], float(d["pxm"])
    ds = max(1, int(round(TARGET_M / max(pxm, 0.1))))
    h, w = img.shape[0] // ds, img.shape[1] // ds
    x = np.asarray(Image.fromarray(img).resize((w, h), Image.Resampling.LANCZOS))

    def pool(a, fn):
        a = a[: h * ds, : w * ds].reshape(h, ds, w, ds)
        return fn(a, axis=(1, 3))

    bnd = pool(d["bnd"] > 0, np.max)
    ext = pool(d["ext"] > 0, np.mean) > 0.5
    valid = pool(d["valid"] > 0, np.min)
    near = ndimage.binary_dilation(
        ext | bnd, iterations=8
    )  # unlabelled land far from labelled fields is ignored
    valid = valid & near
    return x, np.stack([bnd, ext, valid]).astype(np.uint8)


class Block(nn.Sequential):
    def __init__(self, i, o):
        super().__init__(
            nn.Conv2d(i, o, 3, padding=1, bias=False),
            nn.BatchNorm2d(o),
            nn.ReLU(inplace=True),
            nn.Conv2d(o, o, 3, padding=1, bias=False),
            nn.BatchNorm2d(o),
            nn.ReLU(inplace=True),
        )


class UNet(nn.Module):
    def __init__(self, ch=CH):
        super().__init__()
        self.enc = nn.ModuleList([Block(3, ch[0])] + [Block(ch[i], ch[i + 1]) for i in range(len(ch) - 1)])
        self.up = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Conv2d(ch[i + 1], ch[i], 3, padding=1, bias=False),
                    nn.BatchNorm2d(ch[i]),
                    nn.ReLU(inplace=True),
                )
                for i in reversed(range(len(ch) - 1))
            ]
        )
        self.dec = nn.ModuleList([Block(2 * ch[i], ch[i]) for i in reversed(range(len(ch) - 1))])
        self.head = nn.Conv2d(ch[0], 2, 1)

    def forward(self, x):
        skips = []
        for i, e in enumerate(self.enc):
            x = e(x if i == 0 else F.max_pool2d(x, 2))
            skips.append(x)
        x = skips.pop()
        for u, d in zip(self.up, self.dec, strict=False):
            x = u(F.interpolate(x, scale_factor=2, mode="nearest"))
            x = d(torch.cat([x, skips.pop()], 1))
        return self.head(x)


MEAN = np.array([0.40, 0.42, 0.36], np.float32)
STD = np.array([0.18, 0.16, 0.15], np.float32)


def augment(x, y, rng):
    # x: B,3,H,W float [0,1] on gpu; y: B,3,H,W
    Bn = x.shape[0]
    k = int(rng.integers(4))
    x = torch.rot90(x, k, (2, 3))
    y = torch.rot90(y, k, (2, 3))
    if rng.random() < 0.5:
        x = x.flip(3)
        y = y.flip(3)
    dev = x.device
    br = torch.empty(Bn, 1, 1, 1, device=dev).uniform_(0.7, 1.3)
    ct = torch.empty(Bn, 1, 1, 1, device=dev).uniform_(0.7, 1.4)
    m = x.mean((1, 2, 3), keepdim=True)
    x = (x - m) * ct + m * br
    gray = x.mean(1, keepdim=True)
    sat = torch.empty(Bn, 1, 1, 1, device=dev).uniform_(0.5, 1.4)
    x = gray + (x - gray) * sat
    x = x * torch.empty(Bn, 3, 1, 1, device=dev).uniform_(0.88, 1.12)  # colour cast
    if rng.random() < 0.4:  # blur (Esri mosaics are often softer)
        x = F.avg_pool2d(F.pad(x, (1, 1, 1, 1), mode="replicate"), 3, 1)
    x = x + torch.randn_like(x) * float(rng.uniform(0, 0.03))
    return x.clamp(0, 1), y


def main():
    files = sorted(glob.glob(f"{B}/train/*.npz"))
    if os.environ.get("COUNTRIES"):
        files = [f for f in files if os.path.basename(f).split("_")[0] in os.environ["COUNTRIES"].split(",")]
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(16) as ex:
        data = list(ex.map(prep_window, files, chunksize=8))
    print(
        len(data),
        "windows",
        {c: sum(c in f for f in files) for c in ("france", "spain", "netherlands", "austria")},
        flush=True,
    )
    rng = np.random.default_rng(0)
    dev = "cuda"
    net = UNet().to(dev).to(memory_format=torch.channels_last)
    print("params", sum(p.numel() for p in net.parameters()), flush=True)
    steps = int(os.environ.get("STEPS", 6000))
    bs = 32
    S = 160
    opt = torch.optim.AdamW(net.parameters(), 2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 2e-3, total_steps=steps, pct_start=0.1)
    mean = torch.tensor(MEAN, device=dev).view(1, 3, 1, 1)
    std = torch.tensor(STD, device=dev).view(1, 3, 1, 1)
    t0 = time.time()
    for it in range(steps):
        xs, ys = [], []
        for _ in range(bs):
            x, y = data[rng.integers(len(data))]
            h, w = x.shape[:2]
            r, c = rng.integers(0, h - S + 1), rng.integers(0, w - S + 1)
            xs.append(x[r : r + S, c : c + S])
            ys.append(y[:, r : r + S, c : c + S])
        x = torch.from_numpy(np.stack(xs)).to(dev).permute(0, 3, 1, 2).float() / 255
        y = torch.from_numpy(np.stack(ys)).to(dev).float()
        x, y = augment(x, y, rng)
        x = ((x - mean) / std).contiguous(memory_format=torch.channels_last)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out = net(x)
        out = out.float()
        v = y[:, 2]
        lb = F.binary_cross_entropy_with_logits(
            out[:, 0], y[:, 0], pos_weight=torch.tensor(4.0, device=dev), reduction="none"
        )
        le = F.binary_cross_entropy_with_logits(out[:, 1], y[:, 1], reduction="none")
        pb = torch.sigmoid(out[:, 0]) * v
        dice = 1 - (2 * (pb * y[:, 0]).sum() + 1) / (pb.sum() + (y[:, 0] * v).sum() + 1)
        loss = (lb * v).sum() / v.sum().clamp(min=1) + (le * v).sum() / v.sum().clamp(min=1) + dice
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        sched.step()
        if it % 250 == 0:
            print(it, round(loss.item(), 4), round(time.time() - t0), flush=True)
    tag = os.environ.get("TAG", "_".join(map(str, CH)))
    torch.save(net.state_dict(), f"{B}/edge_{tag}.pt")
    export(net, f"{B}/fieldedge_{tag}.npz")


def export(net, path):
    """Fold BN into conv weights; save float16 arrays in forward order."""
    net = net.cpu().eval()
    arrs = {}

    def fold(conv, bn):
        w = conv.weight.detach().numpy().astype(np.float64)
        g = bn.weight.detach().numpy()
        b = bn.bias.detach().numpy()
        m = bn.running_mean.numpy()
        v = bn.running_var.numpy()
        s = g / np.sqrt(v + bn.eps)
        return (w * s[:, None, None, None]).astype(np.float32), (b - m * s).astype(np.float32)

    def block(prefix, blk):
        arrs[prefix + "a_w"], arrs[prefix + "a_b"] = fold(blk[0], blk[1])
        arrs[prefix + "b_w"], arrs[prefix + "b_b"] = fold(blk[3], blk[4])

    for i, e in enumerate(net.enc):
        block(f"enc{i}_", e)
    for i, (u, d) in enumerate(zip(net.up, net.dec, strict=False)):
        arrs[f"up{i}_w"], arrs[f"up{i}_b"] = fold(u[0], u[1])
        block(f"dec{i}_", d)
    arrs["head_w"] = net.head.weight.detach().numpy()
    arrs["head_b"] = net.head.bias.detach().numpy()
    arrs = {k: v.astype(np.float16) for k, v in arrs.items()}
    np.savez_compressed(
        path, **arrs, mean=MEAN, std=STD, levels=np.array(len(net.enc)), target_m=np.array(TARGET_M)
    )
    print("exported", path, os.path.getsize(path), flush=True)


if __name__ == "__main__":
    main()
