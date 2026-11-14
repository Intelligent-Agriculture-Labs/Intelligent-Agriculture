import React, { useState } from "react";
import { View, type LayoutChangeEvent } from "react-native";
import Svg, { Line, Path, Rect, Text as SvgText, G } from "react-native-svg";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/lib/theme";
import { convert, type UnitSystem } from "@/lib/units";
import type { Series, SeriesPoint } from "@/api/types";
import { Txt } from "./ui";

const PAD = { l: 44, r: 10, t: 10, b: 26 };
const BAR_SERIES = new Set(["precip", "rain", "irrigation", "irrigation_applied", "forecast_precip"]);

function useWidth(): [number, (e: LayoutChangeEvent) => void] {
  const [w, setW] = useState(0);
  return [w, (e) => setW(Math.round(e.nativeEvent.layout.width))];
}

export function niceTicks(min: number, max: number, n = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) {
    max = min + 1;
    min = min - 1;
  }
  const raw = (max - min) / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  const top = Math.ceil(max / step - 1e-9) * step; // always cover the data maximum
  for (let v = Math.floor(min / step) * step; v <= top + step * 0.001; v += step) out.push(Math.round(v * 1e6) / 1e6);
  return out;
}

function fmtTick(v: number) {
  const a = Math.abs(v);
  return a >= 1000 ? `${Math.round(v / 100) / 10}k` : a >= 10 ? String(Math.round(v)) : String(Math.round(v * 100) / 100);
}

function shortDate(iso: string, lang: string) {
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00Z" : ""));
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang, { month: "short", day: "numeric", timeZone: "UTC" });
}

/** One time series, with its climatological normal dashed underneath. Bars for rain-like variables. */
/** Series drawn as reference lines on top of a primary chart with the same unit (e.g. stress threshold on soil depletion). */
export const OVERLAY_SERIES = new Set(["raw_threshold", "taw", "threshold", "normal_band"]);

export function SeriesChart({
  s,
  system,
  height = 170,
  testID,
  overlays = [],
}: {
  s: Series;
  system: UnitSystem;
  height?: number;
  testID?: string;
  overlays?: Series[];
}) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const [w, onLayout] = useWidth();
  const conv = (p: SeriesPoint) => (p.value === null ? null : convert(p.value, s.unit, system).value);
  const unit = convert(1, s.unit, system).unit;
  const pts = s.points.map((p) => ({ d: p.date, v: conv(p) }));
  const nrm = (s.normal ?? []).map((p) => ({ d: p.date, v: conv(p) }));
  const ovs = overlays.map((o) => ({ o, pts: o.points.map((p) => ({ d: p.date, v: p.value === null ? null : convert(p.value, o.unit, system).value })) }));
  const dates = Array.from(new Set([...pts.map((p) => p.d), ...nrm.map((p) => p.d), ...ovs.flatMap((x) => x.pts.map((p) => p.d))])).sort();
  const vals = [...pts, ...nrm, ...ovs.flatMap((x) => x.pts)].map((p) => p.v).filter((v): v is number => v !== null);
  const isBar = BAR_SERIES.has(s.id);
  const lo = isBar ? 0 : Math.min(...vals);
  const hi = Math.max(...vals);
  const ticks = niceTicks(lo, hi);
  const y0 = ticks[0] ?? lo;
  const y1 = ticks[ticks.length - 1] ?? hi;
  const iw = Math.max(1, w - PAD.l - PAD.r);
  const ih = height - PAD.t - PAD.b;
  const di = new Map(dates.map((d, i) => [d, i]));
  const x = (d: string) => PAD.l + ((di.get(d) ?? 0) / Math.max(1, dates.length - 1)) * iw;
  const y = (v: number) => PAD.t + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
  const path = (arr: { d: string; v: number | null }[]) => {
    let out = "";
    let pen = false;
    for (const p of arr) {
      if (p.v === null) {
        pen = false;
        continue;
      }
      out += `${pen ? "L" : "M"}${x(p.d).toFixed(1)},${y(p.v).toFixed(1)}`;
      pen = true;
    }
    return out;
  };
  const last = [...pts].reverse().find((p) => p.v !== null);
  const color = s.kind === "forecast" ? t.chart[1] : s.kind === "modelled" ? t.chart[2] : t.chart[0];
  const a11y = tr("a11y.chart", {
    label: s.label,
    start: dates[0] ?? "",
    end: dates[dates.length - 1] ?? "",
    last: last ? `${fmtTick(last.v as number)} ${unit}` : "—",
  });
  const xLabels = dates.length ? [dates[0], dates[Math.floor(dates.length / 2)], dates[dates.length - 1]] : [];
  const bw = Math.max(1, iw / Math.max(1, dates.length) - 1);

  return (
    <View onLayout={onLayout} accessible accessibilityRole="image" accessibilityLabel={a11y} testID={testID}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 4 }}>
        <Txt v="label">{s.label}</Txt>
        <Txt v="small" muted>
          {unit}
        </Txt>
      </View>
      {w > 0 && vals.length > 0 ? (
        <Svg width={w} height={height}>
          {ticks.map((tk) => (
            <G key={tk}>
              <Line x1={PAD.l} x2={w - PAD.r} y1={y(tk)} y2={y(tk)} stroke={t.border} strokeWidth={1} />
              <SvgText x={PAD.l - 6} y={y(tk) + 4} fontSize={11} fill={t.textMuted} textAnchor="end">
                {fmtTick(tk)}
              </SvgText>
            </G>
          ))}
          {nrm.length > 0 ? <Path d={path(nrm)} stroke={t.textMuted} strokeWidth={1.5} strokeDasharray="5,4" fill="none" /> : null}
          {ovs.map((x, i) => (
            <Path key={x.o.id} d={path(x.pts)} stroke={t.chart[(i + 3) % t.chart.length]} strokeWidth={1.8} strokeDasharray="7,4" fill="none" />
          ))}
          {isBar ? (
            pts.map((p) => (p.v ? <Rect key={p.d} x={x(p.d) - bw / 2} y={y(p.v)} width={bw} height={Math.max(0, y(y0) - y(p.v))} fill={color} rx={1} /> : null))
          ) : (
            <Path d={path(pts)} stroke={color} strokeWidth={2.5} fill="none" strokeLinejoin="round" />
          )}
          {xLabels.map((d, i) => (
            <SvgText key={d + i} x={x(d)} y={height - 6} fontSize={11} fill={t.textMuted} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>
              {shortDate(d, i18n.language)}
            </SvgText>
          ))}
        </Svg>
      ) : (
        <Txt muted>{tr("common.noData")}</Txt>
      )}
      <View style={{ flexDirection: "row", flexWrap: "wrap", columnGap: 16, rowGap: 4, marginTop: 4 }}>
        <Legend color={color} label={s.kind === "forecast" ? tr("why.forecast") : s.kind === "modelled" ? tr("why.model") : tr("why.observed")} />
        {nrm.length > 0 ? <Legend color={t.textMuted} label={tr("why.normal")} dashed /> : null}
        {ovs.map((x, i) => (
          <Legend key={x.o.id} color={t.chart[(i + 3) % t.chart.length]} label={x.o.label} dashed />
        ))}
      </View>
    </View>
  );
}

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
      <Svg width={18} height={6}>
        <Line x1={0} x2={18} y1={3} y2={3} stroke={color} strokeWidth={2.5} strokeDasharray={dashed ? "4,3" : undefined} />
      </Svg>
      <Txt v="small" muted>
        {label}
      </Txt>
    </View>
  );
}

/** Simple vertical bar chart (e.g. simulated yield per season) with an optional reference line. */
export function BarChart({
  data,
  unit,
  reference,
  referenceLabel,
  height = 170,
  label,
}: {
  data: { label: string; value: number; color?: string }[];
  unit: string;
  reference?: number | null;
  referenceLabel?: string;
  height?: number;
  label: string;
}) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  const hi = Math.max(...data.map((d) => d.value), reference ?? 0, 0.0001);
  const ticks = niceTicks(0, hi);
  const top = ticks[ticks.length - 1] ?? hi;
  const iw = Math.max(1, w - PAD.l - PAD.r);
  const ih = height - PAD.t - PAD.b;
  const bw = iw / Math.max(1, data.length);
  const y = (v: number) => PAD.t + ih - (v / (top || 1)) * ih;
  const every = Math.ceil(data.length / 6);
  return (
    <View
      onLayout={onLayout}
      accessible
      accessibilityRole="image"
      accessibilityLabel={`${label}: ${data.map((d) => `${d.label} ${fmtTick(d.value)} ${unit}`).join(", ")}`}
    >
      {w > 0 ? (
        <Svg width={w} height={height}>
          {ticks.map((tk) => (
            <G key={tk}>
              <Line x1={PAD.l} x2={w - PAD.r} y1={y(tk)} y2={y(tk)} stroke={t.border} />
              <SvgText x={PAD.l - 6} y={y(tk) + 4} fontSize={11} fill={t.textMuted} textAnchor="end">
                {fmtTick(tk)}
              </SvgText>
            </G>
          ))}
          {data.map((d, i) => (
            <G key={d.label + i}>
              <Rect
                x={PAD.l + i * bw + bw * 0.15}
                y={y(d.value)}
                width={bw * 0.7}
                height={Math.max(0, y(0) - y(d.value))}
                rx={2}
                fill={d.color ?? t.chart[0]}
              />
              {i % every === 0 ? (
                <SvgText x={PAD.l + i * bw + bw / 2} y={height - 6} fontSize={10} fill={t.textMuted} textAnchor="middle">
                  {d.label}
                </SvgText>
              ) : null}
            </G>
          ))}
          {reference ? (
            <G>
              <Line x1={PAD.l} x2={w - PAD.r} y1={y(reference)} y2={y(reference)} stroke={t.accent} strokeWidth={2} strokeDasharray="6,4" />
              {referenceLabel ? (
                <SvgText x={w - PAD.r} y={y(reference) - 4} fontSize={11} fill={t.accent} textAnchor="end">
                  {referenceLabel}
                </SvgText>
              ) : null}
            </G>
          ) : null}
        </Svg>
      ) : null}
    </View>
  );
}

/** Year-by-year trend line with least-squares fit. */
export function TrendChart({ years, values, unit, height = 150 }: { years: number[]; values: (number | null)[]; unit: string; height?: number }) {
  const t = useTheme();
  const [w, onLayout] = useWidth();
  const pts = years.map((yr, i) => ({ yr, v: values[i] })).filter((p): p is { yr: number; v: number } => p.v !== null && p.v !== undefined);
  if (!pts.length) return null;
  const lo = Math.min(...pts.map((p) => p.v));
  const hi = Math.max(...pts.map((p) => p.v));
  const ticks = niceTicks(lo, hi, 3);
  const y0 = ticks[0] ?? lo;
  const y1 = ticks[ticks.length - 1] ?? hi;
  const iw = Math.max(1, w - PAD.l - PAD.r);
  const ih = height - PAD.t - PAD.b;
  const x0 = pts[0].yr;
  const xN = pts[pts.length - 1].yr;
  const x = (yr: number) => PAD.l + ((yr - x0) / Math.max(1, xN - x0)) * iw;
  const y = (v: number) => PAD.t + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
  const n = pts.length;
  const mx = pts.reduce((a, p) => a + p.yr, 0) / n;
  const my = pts.reduce((a, p) => a + p.v, 0) / n;
  const slope =
    pts.reduce((a, p) => a + (p.yr - mx) * (p.v - my), 0) /
    Math.max(
      1e-9,
      pts.reduce((a, p) => a + (p.yr - mx) ** 2, 0),
    );
  const fit = (yr: number) => my + slope * (yr - mx);
  return (
    <View onLayout={onLayout} accessible accessibilityRole="image" accessibilityLabel={`${x0}–${xN}, ${fmtTick(slope * 10)} ${unit}/10y`}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          {ticks.map((tk) => (
            <G key={tk}>
              <Line x1={PAD.l} x2={w - PAD.r} y1={y(tk)} y2={y(tk)} stroke={t.border} />
              <SvgText x={PAD.l - 6} y={y(tk) + 4} fontSize={11} fill={t.textMuted} textAnchor="end">
                {fmtTick(tk)}
              </SvgText>
            </G>
          ))}
          <Path
            d={pts.map((p, i) => `${i ? "L" : "M"}${x(p.yr).toFixed(1)},${y(p.v).toFixed(1)}`).join("")}
            stroke={t.chart[1]}
            strokeWidth={1.5}
            fill="none"
          />
          <Line x1={x(x0)} x2={x(xN)} y1={y(fit(x0))} y2={y(fit(xN))} stroke={t.accent} strokeWidth={2.5} />
          {[x0, Math.round((x0 + xN) / 2), xN].map((yr, i) => (
            <SvgText key={yr} x={x(yr)} y={height - 6} fontSize={11} fill={t.textMuted} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>
              {String(yr)}
            </SvgText>
          ))}
        </Svg>
      ) : null}
    </View>
  );
}

export function ConfidenceMeter({ value, note }: { value: number; note?: string }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const label = value >= 0.7 ? tr("why.confidenceHigh") : value >= 0.45 ? tr("why.confidenceMedium") : tr("why.confidenceLow");
  const col = value >= 0.7 ? t.risk.low.dot : value >= 0.45 ? t.risk.moderate.dot : t.risk.high.dot;
  return (
    <View accessible accessibilityLabel={`${label} ${pct}%. ${note ?? ""}`} testID="confidence">
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Txt v="label">{label}</Txt>
        <Txt v="label">{pct}%</Txt>
      </View>
      <View style={{ height: 10, borderRadius: 5, backgroundColor: t.cardAlt, marginTop: 6, overflow: "hidden" }}>
        <View style={{ width: `${pct}%`, height: 10, backgroundColor: col }} />
      </View>
      {note ? (
        <Txt v="small" muted style={{ marginTop: 6 }}>
          {note}
        </Txt>
      ) : null}
    </View>
  );
}
