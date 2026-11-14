import React, { useState } from "react";
import { Text, View, type LayoutChangeEvent } from "react-native";
import Svg, { Circle, G, Line, Path, Rect, Text as SvgText } from "react-native-svg";
import { useTranslation } from "react-i18next";
import type { SatelliteResponse, SeriesPoint } from "@/api/types";
import { useTheme } from "@/lib/theme";

const PAD = { l: 36, r: 10, t: 16, b: 26 };

const toT = (iso: string) => Date.parse(iso.length === 10 ? `${iso}T00:00:00Z` : iso);

/** Field-mean Sentinel-2 NDVI: clear scenes (dots), smoothed curve, bare-soil periods (shaded), phenology markers. */
export function NdviChart({ data, height = 220 }: { data: SatelliteResponse; height?: number }) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const pts: SeriesPoint[] = (data.timeseries ?? []).filter((p) => p.value !== null);
  const sm: SeriesPoint[] = (data.smoothed ?? []).filter((p) => p.value !== null);
  const all = [...pts, ...sm];
  const ph = data.phenology;
  const summary = ph
    ? tr("sat.chartA11y", {
        n: pts.length,
        peak: ph.peak_ndvi !== null && ph.peak_ndvi !== undefined ? ph.peak_ndvi.toFixed(2) : "–",
        type: ph.season_type,
      })
    : tr("sat.chartA11yShort", { n: pts.length });

  if (!all.length) return null;
  const t0 = Math.min(...all.map((p) => toT(p.date)));
  const t1 = Math.max(...all.map((p) => toT(p.date)));
  const ymin = Math.min(0, ...all.map((p) => p.value as number));
  const ymax = Math.max(0.9, ...all.map((p) => p.value as number));
  const iw = Math.max(1, w - PAD.l - PAD.r);
  const ih = height - PAD.t - PAD.b;
  const x = (iso: string) => PAD.l + ((toT(iso) - t0) / Math.max(1, t1 - t0)) * iw;
  const y = (v: number) => PAD.t + (1 - (v - ymin) / (ymax - ymin)) * ih;
  const ticks = [0, 0.2, 0.4, 0.6, 0.8].filter((v) => v >= ymin && v <= ymax);
  const path = sm.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.value as number).toFixed(1)}`).join("");
  const months: number[] = [];
  const d = new Date(t0);
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + 1);
  while (d.getTime() <= t1) {
    months.push(d.getTime());
    d.setUTCMonth(d.getUTCMonth() + 2);
  }
  const markers: { date: string; label: string; color: string }[] = [];
  if (ph?.greenup) markers.push({ date: ph.greenup, label: tr("sat.greenup"), color: t.chart[0] });
  if (ph?.peak) markers.push({ date: ph.peak, label: tr("sat.peak"), color: t.chart[2] });
  if (ph?.senescence) markers.push({ date: ph.senescence, label: tr("sat.senescence"), color: t.chart[3] });
  const harvests = (ph?.harvest_events ?? []).filter((h) => toT(h) >= t0 && toT(h) <= t1);

  return (
    <View onLayout={onLayout} accessible accessibilityRole="image" accessibilityLabel={summary} testID="ndvi-chart">
      {w > 0 ? (
        <Svg width={w} height={height}>
          {(ph?.bare_periods ?? []).map((b, i) => (
            <Rect
              key={`bare${i}`}
              x={Math.max(PAD.l, x(b.start))}
              y={PAD.t}
              width={Math.max(2, Math.min(PAD.l + iw, x(b.end)) - Math.max(PAD.l, x(b.start)))}
              height={ih}
              fill={t.bare}
              opacity={0.25}
            />
          ))}
          {ticks.map((v) => (
            <G key={`y${v}`}>
              <Line x1={PAD.l} x2={PAD.l + iw} y1={y(v)} y2={y(v)} stroke={t.border} strokeWidth={1} />
              <SvgText x={PAD.l - 6} y={y(v) + 4} fontSize={11} fill={t.textMuted} textAnchor="end">
                {v.toFixed(1)}
              </SvgText>
            </G>
          ))}
          {months.map((m) => (
            <SvgText key={`m${m}`} x={PAD.l + ((m - t0) / Math.max(1, t1 - t0)) * iw} y={height - 8} fontSize={11} fill={t.textMuted} textAnchor="middle">
              {new Date(m).toLocaleDateString(i18n.language, { month: "short", timeZone: "UTC" })}
            </SvgText>
          ))}
          {markers.map((mk) => (
            <G key={mk.label}>
              <Line x1={x(mk.date)} x2={x(mk.date)} y1={PAD.t} y2={PAD.t + ih} stroke={mk.color} strokeWidth={1.5} strokeDasharray="4,3" />
              <SvgText x={x(mk.date) + 3} y={PAD.t + 10} fontSize={11} fill={mk.color} fontWeight="700">
                {mk.label}
              </SvgText>
            </G>
          ))}
          {harvests.map((h) => (
            <G key={`h${h}`}>
              <Line x1={x(h)} x2={x(h)} y1={PAD.t + 14} y2={PAD.t + ih} stroke={t.accent} strokeWidth={1} opacity={0.6} />
              <Path d={`M${x(h) - 6},${PAD.t + ih - 14} L${x(h) + 6},${PAD.t + ih - 14} L${x(h)},${PAD.t + ih - 4} Z`} fill={t.accent} />
            </G>
          ))}
          {path ? <Path d={path} stroke={t.chart[0]} strokeWidth={2.5} fill="none" /> : null}
          {pts.map((p) => (
            <Circle key={p.date} cx={x(p.date)} cy={y(p.value as number)} r={3.5} fill={t.card} stroke={t.chart[1]} strokeWidth={2} />
          ))}
        </Svg>
      ) : (
        <View style={{ height }} />
      )}
      {harvests.length ? (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }} testID="harvest-legend">
          <Svg width={12} height={10}>
            <Path d="M0,0 L12,0 L6,10 Z" fill={t.accent} />
          </Svg>
          <Text style={{ color: t.textMuted, fontSize: 12 }}>{tr("sat.harvestLegend")}</Text>
        </View>
      ) : null}
    </View>
  );
}
