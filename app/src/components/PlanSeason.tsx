import React, { useState } from "react";
import { TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { api } from "@/api/client";
import { useQuery } from "@/lib/useQuery";
import type { PlannerResponse, Risk } from "@/api/types";
import { cropName, useCrops } from "@/components/domain";
import { SowingScanChart, WaterBudgetChart } from "@/components/planCharts";
import { Button, Card, ErrorView, Loading, OriginBanner, Section, Txt, styles as ui } from "@/components/ui";
import { Disclosure, InfoButton } from "@/components/kit";
import type { Field } from "@/state/farm";
import { space, useTheme } from "@/lib/theme";
import { fmt, inToMm, mmToIn, tHaToTonAc } from "@/lib/units";
import { useStore } from "@/state/store";

type Op = PlannerResponse["operations"][number];
const OP_ICON: Record<Op["kind"], React.ComponentProps<typeof Ionicons>["name"]> = {
  sow: "leaf",
  stage: "flower",
  harvest: "basket",
  scout: "bug",
  water: "water",
};
const riskOf = (pct: number): Risk => (pct >= 50 ? "severe" : pct >= 25 ? "high" : pct >= 10 ? "moderate" : "low");

export function PlanSeason({ field }: { field: Field }) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const { settings, updateField } = useStore();
  const crops = useCrops();
  const sys = settings.units;
  const imperial = sys === "imperial";
  const [showAllOps, setShowAllOps] = useState(false);
  const [allocText, setAllocText] = useState(field.water_allocation_mm ? String(field.water_allocation_mm) : "");
  const alloc = field.water_allocation_mm ?? null;
  const q = useQuery<PlannerResponse>(`${field.lat},${field.lon},${field.crop},${field.planting_date},${field.irrigation},${alloc},${settings.lang}`, () =>
    api.planner({
      lat: field.lat,
      lon: field.lon,
      crop: field.crop,
      planting_date: field.planting_date,
      irrigation: field.irrigation,
      water_allocation_mm: alloc,
      lang: settings.lang,
    }),
  );
  const { data, origin, savedAt, error } = q;

  const dateFmt = (iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" }) =>
    new Date(iso + "T00:00:00Z").toLocaleDateString(i18n.language, { ...opts, timeZone: "UTC" });
  const monthName = (m: number) => new Date(Date.UTC(2020, m - 1, 1)).toLocaleDateString(i18n.language, { month: "short", timeZone: "UTC" });
  const yieldUnit = imperial ? "ton/ac" : "t/ha";
  const yv = (v: number) => (imperial ? tHaToTonAc(v) : v);
  const wv = (v: number) => (imperial ? mmToIn(v) : v);
  const applyAlloc = () => {
    const v = parseFloat(allocText.replace(",", "."));
    updateField(field.id, { water_allocation_mm: Number.isFinite(v) && v > 0 ? Math.round(imperial ? inToMm(v) : v) : null });
  };
  const irrigated = field.irrigation !== "none";

  return (
    <View testID="plan-season">
      <Txt muted style={{ marginTop: space.md }}>
        {tr("plan.subtitle", { crop: cropName(crops, field.crop), place: field.name })}
      </Txt>
      <OriginBanner origin={origin} savedAt={savedAt} />

      {!data && !error ? <Loading label={tr("plan.loading")} /> : null}
      {error && !data ? <ErrorView message={error} onRetry={q.refetch} /> : null}
      {data ? (
        <>
          {data.window ? (
            <Section title={tr("plan.sowing")}>
              <Card testID="plan-window">
                <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                  <Ionicons name="calendar" size={22} color={t.primary} />
                  <Txt v="h3" style={{ flex: 1 }}>
                    {tr("plan.window", { start: dateFmt(data.window.start), end: dateFmt(data.window.end) })}
                  </Txt>
                  <InfoButton term="yieldBadYear" />
                </View>
                <Txt v="small" muted style={{ marginTop: 4 }}>
                  {tr("plan.windowWhy", { n: data.years[1] - data.years[0] + 1, y0: data.years[0], y1: data.years[1] })}
                </Txt>
                <SowingScanChart
                  points={data.sowing_scan.map((s) => ({ date: s.date, median: yv(s.yield_median), p10: yv(s.yield_p10), frostPct: s.frost_risk_pct }))}
                  window={data.window}
                  unit={yieldUnit}
                  labels={{ median: tr("plan.median"), p10: tr("plan.badYear"), frost: tr("plan.frostRisk") }}
                  a11y={tr("plan.scanA11y", {
                    best: dateFmt(data.window.best),
                    y: fmt(Math.max(...data.sowing_scan.map((s) => s.yield_median)), "t/ha", sys, 1),
                  })}
                />
              </Card>
            </Section>
          ) : null}

          <Section title={data.sowing_scan.length ? tr("plan.timeline") : tr("plan.cuttings")}>
            <Card testID="plan-timeline">
              {(showAllOps ? data.operations : data.operations.slice(0, 6)).map((o, i, arr) => (
                <View key={i} style={{ flexDirection: "row", gap: space.md, minHeight: 44 }} testID={`op-${i}`}>
                  <View style={{ alignItems: "center", width: 28 }}>
                    <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: t.cardAlt, alignItems: "center", justifyContent: "center" }}>
                      <Ionicons name={OP_ICON[o.kind]} size={16} color={o.kind === "scout" ? t.accent : t.primary} />
                    </View>
                    {i < arr.length - 1 ? <View style={{ width: 2, flex: 1, backgroundColor: t.border }} /> : null}
                  </View>
                  <View style={{ flex: 1, paddingBottom: space.md }}>
                    <Txt v="label">{dateFmt(o.date, { day: "numeric", month: "short", year: "numeric" })}</Txt>
                    <Txt>
                      {o.label}
                      {(() => {
                        const st = data.stages.find((s) => s.label === o.label && s.date === o.date);
                        return st && st.spread_days ? ` (± ${Math.round(st.spread_days / 2)} ${tr("plan.days")})` : "";
                      })()}
                    </Txt>
                  </View>
                </View>
              ))}
              {data.operations.length > 6 ? (
                <Button
                  kind="ghost"
                  label={showAllOps ? tr("common.showLess") : tr("common.showAll", { n: data.operations.length })}
                  onPress={() => setShowAllOps((v) => !v)}
                  testID="plan-ops-toggle"
                />
              ) : null}
            </Card>
          </Section>

          <Disclosure title={tr("plan.water")} subtitle={tr("plan.waterSubtitle")} icon="water-outline" testID="plan-water-toggle">
            <View testID="plan-water">
              <WaterBudgetChart
                months={data.water_budget.map((b) => monthName(b.month))}
                unit={imperial ? "in" : "mm"}
                series={[
                  { label: tr("plan.cropUse"), color: t.chart[0], values: data.water_budget.map((b) => wv(b.etc)) },
                  { label: tr("plan.rain"), color: t.chart[1], values: data.water_budget.map((b) => wv(b.rain)) },
                  ...(irrigated ? [{ label: tr("plan.irrigation"), color: t.chart[2], values: data.water_budget.map((b) => wv(b.irr)) }] : []),
                ]}
                a11y={tr("plan.waterA11y", {
                  etc: fmt(
                    data.water_budget.reduce((a, b) => a + b.etc, 0),
                    "mm",
                    sys,
                    0,
                  ),
                  rain: fmt(
                    data.water_budget.reduce((a, b) => a + b.rain, 0),
                    "mm",
                    sys,
                    0,
                  ),
                })}
              />
              {irrigated ? (
                <View style={{ marginTop: space.md, gap: 4 }}>
                  <Txt>{tr("plan.fullNeed", { mm: fmt(data.water.full_need_median_mm, "mm", sys, 0) })}</Txt>
                  {data.water.coverage_pct !== null && data.water.allocation_mm ? (
                    <Txt style={{ fontWeight: "700" }} color={data.water.coverage_pct < 90 ? t.risk.high.fg : t.risk.low.fg} testID="plan-coverage">
                      {tr("plan.coverage", { pct: data.water.coverage_pct, alloc: fmt(data.water.allocation_mm, "mm", sys, 0) })}
                      {data.water.coverage_pct < 90 ? ` ${tr("plan.coverageAdvice")}` : ""}
                    </Txt>
                  ) : null}
                </View>
              ) : null}
              {irrigated ? (
                <View style={{ marginTop: space.lg }}>
                  <View style={{ flexDirection: "row", alignItems: "center" }}>
                    <Txt v="label" style={{ flex: 1 }}>
                      {tr("plan.allocation", { unit: imperial ? "in" : "mm" })}
                    </Txt>
                  </View>
                  <Txt v="small" muted>
                    {tr("plan.allocationHint")}
                  </Txt>
                  <View style={{ flexDirection: "row", gap: space.sm, marginTop: space.sm, alignItems: "center" }}>
                    <TextInput
                      accessibilityLabel={tr("plan.allocation", { unit: imperial ? "in" : "mm" })}
                      keyboardType="decimal-pad"
                      value={allocText}
                      onChangeText={setAllocText}
                      placeholder={imperial ? "40" : "1000"}
                      placeholderTextColor={t.textMuted}
                      style={[ui.input, { flex: 1, color: t.text, borderColor: t.border, backgroundColor: t.card }]}
                      testID="plan-allocation"
                    />
                    <Button label={tr("plan.update")} onPress={applyAlloc} icon="refresh" testID="plan-update" />
                  </View>
                </View>
              ) : null}
            </View>
          </Disclosure>

          <Disclosure title={tr("plan.risks")} subtitle={tr("plan.risksSubtitle")} icon="snow-outline" testID="plan-risks-toggle">
            <View>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }} accessible accessibilityLabel={tr("plan.riskA11y")} testID="plan-risks">
                {data.risk_calendar.map((r) => {
                  const rk = riskOf(Math.max(r.frost_pct, r.heat_pct));
                  return (
                    <View key={r.month} style={{ minWidth: 64, flexGrow: 1, padding: 6, borderRadius: 8, backgroundColor: t.risk[rk].bg }}>
                      <Txt v="label" color={t.risk[rk].fg}>
                        {monthName(r.month)}
                      </Txt>
                      <Txt v="small" color={t.risk[rk].fg}>
                        ❄ {r.frost_pct} %
                      </Txt>
                      <Txt v="small" color={t.risk[rk].fg}>
                        ☀ {r.heat_pct} %
                      </Txt>
                    </View>
                  );
                })}
              </View>
              <Txt v="small" muted style={{ marginTop: space.sm }}>
                {tr("plan.riskLegend")}
              </Txt>
            </View>
          </Disclosure>

          <Txt v="small" muted style={{ marginTop: space.lg }}>
            {data.why}
          </Txt>
          <Txt v="small" muted style={{ marginTop: 4 }}>
            {tr("plan.sources")}
          </Txt>
        </>
      ) : null}
    </View>
  );
}
