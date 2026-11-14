import React, { useState } from "react";
import { View, type LayoutChangeEvent } from "react-native";
import Svg, { Circle, G, Line, Path, Rect, Text as SvgText } from "react-native-svg";
import { niceTicks } from "@/components/charts";
import { Txt } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";

const PAD = { l: 40, r: 10, t: 12, b: 26 };

function useWidth(): [number, (e: LayoutChangeEvent) => void] {
  const [w, setW] = useState(0);
  return [w, (e) => setW(Math.round(e.nativeEvent.layout.width))];
}

const tick = (v: number) => (Math.abs(v) >= 10 ? String(Math.round(v)) : String(Math.round(v * 10) / 10));

/** Sowing-date scan: median yield line, bad-year (p10) dashed line, best window shaded, frost-risk dots. */
export function SowingScanChart({
  points,
  window,
  unit,
  labels,
  a11y,
  height = 190,
}: {
  points: { date: string; median: number; p10: number; frostPct: number }[];
  window: { start: string; end: string } | null;
  unit: string;
  labels: { median: string; p10: string; frost: string };
  a11y: string;
  height?: number;
}) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  if (!points.length) return null;
  const hi = Math.max(...points.map((p) => p.median), 0.1);
  const ticks = niceTicks(0, hi, 4);
  const top = ticks[ticks.length - 1] ?? hi;
  const iw = Math.max(1, w - PAD.l - PAD.r);
  const ih = height - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (i / Math.max(1, points.length - 1)) * iw;
  const y = (v: number) => PAD.t + ih - (v / (top || 1)) * ih;
  const path = (key: "median" | "p10") => points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const wi0 = window ? points.findIndex((p) => p.date >= window.start) : -1;
  const wi1 = window ? points.map((p) => p.date <= window.end).lastIndexOf(true) : -1;
  const short = (iso: string) => {
    const d = new Date(iso + "T00:00:00Z");
    return `${d.getUTCDate()}.${d.getUTCMonth() + 1}`;
  };
  const every = Math.ceil(points.length / 5);
  return (
    <View onLayout={onLayout} accessible accessibilityRole="image" accessibilityLabel={a11y}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          {wi0 >= 0 && wi1 >= wi0 ? <Rect x={x(wi0) - 4} y={PAD.t} width={Math.max(8, x(wi1) - x(wi0) + 8)} height={ih} fill={t.risk.low.bg} /> : null}
          {ticks.map((tk) => (
            <G key={tk}>
              <Line x1={PAD.l} x2={w - PAD.r} y1={y(tk)} y2={y(tk)} stroke={t.border} />
              <SvgText x={PAD.l - 6} y={y(tk) + 4} fontSize={11} fill={t.textMuted} textAnchor="end">
                {tick(tk)}
              </SvgText>
            </G>
          ))}
          <Path d={path("p10")} stroke={t.accent} strokeWidth={2} strokeDasharray="6,4" fill="none" />
          <Path d={path("median")} stroke={t.primary} strokeWidth={3} fill="none" />
          {points.map((p, i) => (
            <G key={p.date}>
              {p.frostPct >= 10 ? <Circle cx={x(i)} cy={PAD.t + 6} r={3 + Math.min(5, p.frostPct / 10)} fill={t.chart[3]} opacity={0.8} /> : null}
              {i % every === 0 ? (
                <SvgText x={x(i)} y={height - 6} fontSize={10} fill={t.textMuted} textAnchor="middle">
                  {short(p.date)}
                </SvgText>
              ) : null}
            </G>
          ))}
        </Svg>
      ) : null}
      <View style={{ flexDirection: "row", gap: space.md, flexWrap: "wrap", marginTop: 4 }}>
        <Txt v="small" color={t.primary}>
          ━ {labels.median} ({unit})
        </Txt>
        <Txt v="small" color={t.accent}>
          ┅ {labels.p10}
        </Txt>
        <Txt v="small" color={t.chart[3]}>
          ● {labels.frost}
        </Txt>
      </View>
    </View>
  );
}

/** Grouped monthly bars: crop water use vs. rain vs. irrigation. */
export function WaterBudgetChart({
  months,
  series,
  unit,
  a11y,
  height = 190,
}: {
  months: string[];
  series: { label: string; color: string; values: number[] }[];
  unit: string;
  a11y: string;
  height?: number;
}) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  const hi = Math.max(0.1, ...series.flatMap((s) => s.values));
  const ticks = niceTicks(0, hi, 4);
  const top = ticks[ticks.length - 1] ?? hi;
  const iw = Math.max(1, w - PAD.l - PAD.r);
  const ih = height - PAD.t - PAD.b;
  const gw = iw / Math.max(1, months.length);
  const bw = (gw * 0.8) / Math.max(1, series.length);
  const y = (v: number) => PAD.t + ih - (v / (top || 1)) * ih;
  return (
    <View onLayout={onLayout} accessible accessibilityRole="image" accessibilityLabel={a11y}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          {ticks.map((tk) => (
            <G key={tk}>
              <Line x1={PAD.l} x2={w - PAD.r} y1={y(tk)} y2={y(tk)} stroke={t.border} />
              <SvgText x={PAD.l - 6} y={y(tk) + 4} fontSize={11} fill={t.textMuted} textAnchor="end">
                {tick(tk)}
              </SvgText>
            </G>
          ))}
          {months.map((m, i) => (
            <G key={m + i}>
              {series.map((s, k) => (
                <Rect
                  key={s.label}
                  x={PAD.l + i * gw + gw * 0.1 + k * bw}
                  y={y(s.values[i] ?? 0)}
                  width={Math.max(1, bw - 1)}
                  height={Math.max(0, y(0) - y(s.values[i] ?? 0))}
                  rx={1.5}
                  fill={s.color}
                />
              ))}
              <SvgText x={PAD.l + i * gw + gw / 2} y={height - 6} fontSize={10} fill={t.textMuted} textAnchor="middle">
                {m}
              </SvgText>
            </G>
          ))}
        </Svg>
      ) : null}
      <View style={{ flexDirection: "row", gap: space.md, flexWrap: "wrap", marginTop: 4 }}>
        {series.map((s) => (
          <Txt key={s.label} v="small" color={s.color}>
            ▮ {s.label} ({unit})
          </Txt>
        ))}
      </View>
    </View>
  );
}
