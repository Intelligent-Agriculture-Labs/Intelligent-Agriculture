import React, { useMemo } from "react";
import Svg, { Path, Rect } from "react-native-svg";
import qrcodeFactory from "qrcode-generator";

/** QR matrix as a single SVG path (one rect per dark module), quiet zone of 4 modules. */
export function qrPath(text: string): { size: number; d: string } {
  const qr = qrcodeFactory(0, "M");
  qr.addData(text);
  qr.make();
  const n = qr.getModuleCount();
  let d = "";
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      if (qr.isDark(r, c)) d += `M${c + 4} ${r + 4}h1v1h-1z`;
    }
  }
  return { size: n + 8, d };
}

export function QrCode({ value, size = 200, accessibilityLabel }: { value: string; size?: number; accessibilityLabel: string }) {
  const { size: n, d } = useMemo(() => qrPath(value), [value]);
  return (
    <Svg width={size} height={size} viewBox={`0 0 ${n} ${n}`} accessibilityLabel={accessibilityLabel} accessibilityRole="image">
      <Rect x={0} y={0} width={n} height={n} fill="#ffffff" />
      <Path d={d} fill="#111111" />
    </Svg>
  );
}
