/**
 * Scripted "capture tour" for screenshots and screen recordings of native builds.
 * Enabled ONLY in builds made with EXPO_PUBLIC_CAPTURE_TOUR=1 (see app/scripts/capture-native.sh);
 * normal builds never run it. Needed because XCUITest (and therefore Maestro) does not work with the
 * Xcode 27 beta toolchain on this machine; the tour is timing-based and prints markers to the device log.
 */
import { useEffect } from "react";
import { router } from "expo-router";
import { api } from "@/api/client";
import { useStore } from "@/state/store";

import { CAPTURE_MODE as MODE, CAPTURE_TOUR, captureHooks } from "./captureHooks";

export { CAPTURE_TOUR, captureHooks };
const PRESET = process.env.EXPO_PUBLIC_CAPTURE_PRESET ?? "fallon_nv";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function CaptureTour() {
  const { ready, setField, setSettings } = useStore();
  useEffect(() => {
    if (!CAPTURE_TOUR || !ready || MODE !== "film") return;
    let cancelled = false;
    // Film tour: each screen is given time to load real data, then "[shot] <name>" tells the host
    // (app/scripts/capture-film-ios.sh) to take the screenshot right away.
    const shot = async (name: string, go: () => void, waitMs: number) => {
      if (cancelled) return;
      go();
      await sleep(waitMs);
      console.log(`[shot] ${name}`);
      await sleep(2500);
    };
    const scrollTo = async (target: string, top = 140) => {
      const el = captureHooks.targets[target];
      if (!el || !captureHooks.scrollBy) return;
      await new Promise<void>((res) => el.measureInWindow((_x: number, y: number) => { captureHooks.scrollBy?.(y - top); res(); }));
      await sleep(1200);
    };
    (async () => {
      const presets = (await api.presets()).data;
      const field = (id: string, replay: boolean) => {
        const p = presets.find((x) => x.id === id) ?? presets[0];
        return {
          lat: p.lat, lon: p.lon, crop: p.crop, planting_date: p.planting_date, irrigation: p.irrigation, name: p.name,
          presetId: p.id, current_rotation: p.current_rotation,
          polygon: p.polygon && p.polygon.length >= 3 ? p.polygon : undefined,
          replay_date: p.replay_date ?? null, as_of: replay ? (p.replay_date ?? null) : null,
        };
      };
      setSettings({ lang: "en" });
      await shot("welcome", () => router.replace("/welcome"), 4000);
      await shot("home", () => { setField(field("fallon_nv", true)); router.replace("/home"); }, 22000);
      await shot("why", () => router.push({ pathname: "/why/[cardId]", params: { cardId: "irrigate" } }), 7000);
      await shot("satellite", () => router.replace({ pathname: "/map", params: { view: "satellite" } }), 20000);
      await shot("plan-years", () => router.replace({ pathname: "/plan", params: { tab: "years" } }), 32000);
      await scrollTo("impact");
      await shot("impact", () => undefined, 1500);
      await shot("insights", () => router.replace("/insights"), 5000);
      await shot("climate", () => router.replace("/climate"), 14000);
      await shot("field-editor", () => router.replace("/field-editor"), 9000);
      await shot("account", () => router.push("/account"), 5000);
      for (const lang of ["sw", "hi", "es"] as const) {
        await shot(`home-${lang}`, () => { setSettings({ lang }); router.replace("/home"); }, 14000);
      }
      setSettings({ lang: "en" });
      await shot("terrain-ke", () => { setField(field("machakos_ke", false)); router.replace({ pathname: "/map", params: { view: "terrain" } }); }, 24000);
      await shot("home-ke", () => router.replace("/home"), 16000);
      console.log("[shot] done");
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, setField, setSettings]);
  useEffect(() => {
    if (!CAPTURE_TOUR || !ready || MODE === "film") return;
    let cancelled = false;
    const step = async (name: string, go: () => void, waitMs: number) => {
      if (cancelled) return;
      go();
      console.log(`[capture] ${name}`);
      await sleep(waitMs);
    };
    (async () => {
      await step("welcome", () => router.replace("/welcome"), 5000);
      await step("onboarding", () => router.replace("/onboarding"), 5000);
      const presets = (await api.presets()).data;
      const p = presets.find((x) => x.id === PRESET) ?? presets[0];
      const base = {
        lat: p.lat,
        lon: p.lon,
        crop: p.crop,
        planting_date: p.planting_date,
        irrigation: p.irrigation,
        name: p.name,
        presetId: p.id,
        current_rotation: p.current_rotation,
        polygon: p.polygon && p.polygon.length >= 3 ? p.polygon : undefined,
        replay_date: p.replay_date ?? null,
      };
      await step(
        "home-today",
        () => {
          setField({ ...base, as_of: null });
          router.replace("/home");
        },
        12000,
      );
      await step("home-replay", () => setField({ ...base, as_of: p.replay_date ?? null }), 14000);
      await step("why", () => router.push({ pathname: "/why/[cardId]", params: { cardId: "irrigate" } }), 9000);
      await step("map", () => router.replace({ pathname: "/map", params: { view: "terrain" } }), 16000);
      await step("satellite", () => router.replace({ pathname: "/map", params: { view: "satellite" } }), 14000);
      await step("plan", () => router.replace({ pathname: "/plan", params: { tab: "season" } }), 16000);
      await step("plan-years", () => router.replace({ pathname: "/plan", params: { tab: "years" } }), 25000);
      await step("insights", () => router.replace("/insights"), 6000);
      await step("rotations", () => router.replace("/rotations"), 30000);
      await step("whatif", () => router.replace("/whatif"), 20000);
      await step("climate", () => router.replace("/climate"), 12000);
      await step("account", () => router.push("/account"), 6000);
      await step("field-editor", () => router.replace("/field-editor"), 10000);
      await step("done", () => router.replace("/home"), 1000);
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, setField]);
  return null;
}
