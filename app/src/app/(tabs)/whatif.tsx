import React, { useState } from "react";
import { View } from "react-native";
import { Redirect } from "expo-router";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import { useQuery } from "@/lib/useQuery";
import type { SimulateRequest, SimulateResponse } from "@/api/types";
import { BarChart } from "@/components/charts";
import { useCrops } from "@/components/domain";
import { WhyView } from "@/components/WhyView";
import { Button, Card, Chip, ChipRow, DateField, ErrorView, LabeledSlider, Loading, OriginBanner, Screen, Section, Txt } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { dCToDF, fmt } from "@/lib/units";
import { useStore } from "@/state/store";

type Strategy = SimulateRequest["irrigation_strategy"];
const STRATEGIES: Strategy[] = ["rainfed", "full", "deficit_75", "deficit_50", "allocation"];
type Summary = SimulateResponse["summary"];

function Stat({ label, value, delta, better, testID }: { label: string; value: string; delta?: number | null; better?: "up" | "down"; testID?: string }) {
  const t = useTheme();
  const good = delta === null || delta === undefined || Math.abs(delta) < 0.5 ? null : better === "down" ? delta < 0 : delta > 0;
  return (
    <View style={{ width: "50%", paddingVertical: space.sm, paddingRight: space.sm }} testID={testID}>
      <Txt v="small" muted>
        {label}
      </Txt>
      <Txt v="h3">{value}</Txt>
      {delta !== null && delta !== undefined && Math.abs(delta) >= 0.5 ? (
        <Txt v="small" color={good ? t.risk.low.fg : t.risk.severe.fg} style={{ fontWeight: "700" }}>
          {delta > 0 ? "▲ +" : "▼ "}
          {Math.round(delta)}%
        </Txt>
      ) : null}
    </View>
  );
}

const pct = (v: number, b: number | undefined) => (b && Math.abs(b) > 1e-9 ? ((v - b) / Math.abs(b)) * 100 : null);

export default function WhatIf() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { field, settings } = useStore();
  const crops = useCrops();
  const sys = settings.units;
  const [crop, setCrop] = useState(field?.crop ?? "maize");
  const [date, setDate] = useState(field?.planting_date ?? new Date().toISOString().slice(0, 10));
  const [strategy, setStrategy] = useState<Strategy>(field?.irrigation === "none" ? "rainfed" : "full");
  const [alloc, setAlloc] = useState(600);
  const [dT, setDT] = useState(0);
  const [rain, setRain] = useState(1);
  const years = 20;
  const build = (): SimulateRequest | null =>
    field
      ? {
          lat: field.lat,
          lon: field.lon,
          crop,
          planting_date: date,
          irrigation_strategy: strategy,
          water_allocation_mm: strategy === "allocation" ? alloc : null,
          delta_t_c: dT,
          rain_factor: rain,
          years,
        }
      : null;
  // the simulation runs once on open, then only when the user presses "Run"
  const [req, setReq] = useState<SimulateRequest | null>(build);
  const activeReq = req && field && req.lat === field.lat && req.lon === field.lon ? req : build();
  const q = useQuery<SimulateResponse>(activeReq ? JSON.stringify(activeReq) : null, () => api.simulate(activeReq!));
  const { data, origin, error, loading } = q;
  const run = () => {
    const next = build();
    if (JSON.stringify(next) === JSON.stringify(activeReq)) q.refetch();
    else setReq(next);
  };

  if (!field) return <Redirect href="/onboarding" />;
  const s: Summary | undefined = data?.summary;
  const b: Summary | undefined = data?.baseline;
  const tempLabel = (v: number) => (sys === "imperial" ? `+${dCToDF(v).toFixed(1)} °F` : `+${v.toFixed(1)} °C`);

  return (
    <Screen testID="whatif">
      <Txt v="h1">{tr("whatif.title")}</Txt>
      <Txt muted style={{ marginTop: 4 }}>
        {tr("whatif.subtitle", { years })}
      </Txt>
      <OriginBanner origin={origin} />

      <Card>
        <Txt v="label">{tr("whatif.crop")}</Txt>
        <ChipRow>
          {crops
            .filter((c) => c.type !== "cover")
            .map((c) => (
              <Chip key={c.id} label={c.name} selected={crop === c.id} onPress={() => setCrop(c.id)} />
            ))}
        </ChipRow>
        <DateField label={tr("whatif.plantingDate")} value={date} onChange={setDate} testID="whatif-date" />
        <Txt v="label" style={{ marginTop: space.sm }}>
          {tr("whatif.strategy")}
        </Txt>
        <ChipRow>
          {STRATEGIES.map((k) => (
            <Chip key={k} label={tr(`whatif.strategies.${k}`)} selected={strategy === k} onPress={() => setStrategy(k)} testID={`strategy-${k}`} />
          ))}
        </ChipRow>
        {strategy === "allocation" ? (
          <LabeledSlider label={tr("whatif.allocation")} value={alloc} min={0} max={1500} step={25} onChange={setAlloc} format={(v) => fmt(v, "mm", sys)} />
        ) : null}
        <LabeledSlider label={tr("whatif.warming")} value={dT} min={0} max={4} step={0.5} onChange={setDT} format={tempLabel} testID="whatif-dt" />
        <LabeledSlider
          label={tr("whatif.rain")}
          value={rain}
          min={0.5}
          max={1.3}
          step={0.05}
          onChange={setRain}
          format={(v) => `${v >= 1 ? "+" : ""}${Math.round((v - 1) * 100)}%`}
          testID="whatif-rain"
        />
        <Button label={tr("whatif.run")} icon="play" onPress={run} disabled={loading} testID="whatif-run" style={{ marginTop: space.sm }} />
      </Card>

      {loading && !data ? <Loading /> : null}
      {error ? <ErrorView message={error} onRetry={run} /> : null}

      {data && s ? (
        <>
          <Section title={b ? `${tr("whatif.yield")} · ${tr("whatif.vsBaseline")}` : tr("whatif.yield")}>
            <Card>
              <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
                <Stat
                  label={tr("whatif.yield")}
                  value={fmt(s.yield_median, "t/ha", sys)}
                  delta={pct(s.yield_median, b?.yield_median)}
                  better="up"
                  testID="stat-yield"
                />
                <Stat label={tr("whatif.badYear")} value={fmt(s.yield_p10, "t/ha", sys)} delta={pct(s.yield_p10, b?.yield_p10)} better="up" />
                <Stat
                  label={tr("whatif.irrigationNeed")}
                  value={fmt(s.irrigation_median_mm, "mm", sys)}
                  delta={pct(s.irrigation_median_mm, b?.irrigation_median_mm)}
                  better="down"
                />
                <Stat
                  label={tr("whatif.stressDays")}
                  value={String(Math.round(s.stress_days_median))}
                  delta={pct(s.stress_days_median, b?.stress_days_median)}
                  better="down"
                />
                <Stat label={tr("whatif.failureRisk")} value={`${Math.round(s.failure_risk_pct)}%`} />
                <Stat
                  label={tr("whatif.waterProductivity")}
                  value={`${s.water_productivity_kg_m3.toFixed(2)} kg/m³`}
                  delta={pct(s.water_productivity_kg_m3, b?.water_productivity_kg_m3)}
                  better="up"
                />
              </View>
            </Card>
          </Section>
          <Section title={tr("whatif.perYear")}>
            <Card>
              <BarChart
                label={tr("whatif.perYear")}
                unit={sys === "imperial" ? "ton/ac" : "t/ha"}
                data={data.years.map((y) => ({
                  label: String(y.year).slice(2),
                  value: sys === "imperial" ? y.yield_t_ha * 0.446089 : y.yield_t_ha,
                  color: y.stress_days > (s.stress_days_median || 0) * 1.5 + 2 ? t.accent : t.chart[0],
                }))}
                reference={b ? (sys === "imperial" ? b.yield_median * 0.446089 : b.yield_median) : null}
                referenceLabel={tr("whatif.baseline")}
              />
            </Card>
          </Section>
          <WhyView why={data.why} series={data.daily_example ?? []} sources={[]} expert={settings.expert} />
        </>
      ) : null}
    </Screen>
  );
}
