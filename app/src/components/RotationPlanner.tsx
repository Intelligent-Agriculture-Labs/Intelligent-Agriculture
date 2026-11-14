/**
 * Per-field multi-year rotation planner ("Plan → Next years").
 * The farmer edits what grew before (history) and the plan for the next years; the server checks every year
 * biologically (disease breaks, return intervals, nitrogen, cover) and agronomically (simulated yield & water at
 * this field) and proposes improvements and an optimised plan.
 */
import React, { useMemo, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import { useQuery } from "@/lib/useQuery";
import type { RotationPlanResponse, RotationYear, RotationYearCheck } from "@/api/types";
import { cropName, useCrops } from "@/components/domain";
import { CropPicker, Disclosure, InfoButton, Stat, StatRow, cropIcon } from "@/components/kit";
import { ImpactCard } from "@/components/ImpactCard";
import { Button, Card, ErrorView, Loading, Section, Txt } from "@/components/ui";
import { radius, space, useTheme } from "@/lib/theme";
import { fmt, tHaToTonAc } from "@/lib/units";
import { addPlanYear, defaultPlanYears, normalizeHistory, normalizePlan, removeLastPlanYear, setPlanCrop, type Field } from "@/state/farm";
import { useStore } from "@/state/store";

type Verdict = "good" | "caution" | "problem";
const VERDICT_RISK: Record<Verdict, "low" | "moderate" | "severe"> = { good: "low", caution: "moderate", problem: "severe" };
const VERDICT_ICON: Record<Verdict, React.ComponentProps<typeof Ionicons>["name"]> = {
  good: "checkmark-circle",
  caution: "alert-circle",
  problem: "close-circle",
};

export function planKey(f: Field, history: RotationYear[], plan: RotationYear[]) {
  return JSON.stringify([f.lat, f.lon, f.irrigation, f.water_allocation_mm ?? null, f.polygon ?? null, history, plan]);
}

export function RotationPlanner({ field }: { field: Field }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { updateField, settings } = useStore();
  const crops = useCrops();
  const sys = settings.units;
  const imperial = sys === "imperial";

  const years = useMemo(() => {
    const p = field.plan ?? [];
    return p.length ? p.map((x) => x.year) : defaultPlanYears(new Date(), 4);
  }, [field.plan]);
  const plan = useMemo(() => normalizePlan(field.plan, years, field.crop), [field.plan, years, field.crop]);
  const history = useMemo(() => normalizeHistory(field.history, plan[0].year, 3, field.crop), [field.history, plan, field.crop]);

  const key = planKey(field, history, plan);
  // the check runs for a pinned request key: on mount, on "Check", and right after applying a suggestion
  const [requestKey, setRequestKey] = useState(key);
  const [autoNext, setAutoNext] = useState(false);
  if (autoNext && requestKey !== key) {
    setAutoNext(false);
    setRequestKey(key);
  }
  const q = useQuery<RotationPlanResponse>(requestKey, () =>
    api.rotationPlan({
      lat: field.lat,
      lon: field.lon,
      polygon: field.polygon && field.polygon.length >= 3 ? field.polygon : null,
      irrigation: field.irrigation,
      water_allocation_mm: field.water_allocation_mm ?? null,
      history,
      plan,
      lang: settings.lang,
      optimize: true,
    }),
  );
  const result = q.data;
  const loading = q.loading;
  const error = q.error;
  const stale = !!result && requestKey !== key;
  const run = () => (requestKey === key ? q.refetch() : setRequestKey(key));
  const [selectedChoice, setSelected] = useState<number | null | undefined>(undefined);
  const firstBad = result?.years.find((y) => y.verdict !== "good")?.year ?? null;
  const selected = selectedChoice === undefined ? firstBad : selectedChoice;

  const savePlan = (p: RotationYear[]) => updateField(field.id, { plan: p });
  const saveHistory = (h: RotationYear[]) => updateField(field.id, { history: h });
  const apply = (p: RotationYear[]) => {
    savePlan(p.map((x) => ({ year: x.year, crop: x.crop, cover_crop: x.cover_crop ?? null })));
    setAutoNext(true); // re-check the applied plan on the next render
    setSelected(undefined);
  };

  const yv = (v: number) => (imperial ? tHaToTonAc(v) : v);
  const yUnit = imperial ? "ton/ac" : "t/ha";
  const sel: RotationYearCheck | undefined = result?.years.find((y) => y.year === selected);
  const verdict = result?.summary.verdict ?? "good";
  const vc = t.risk[VERDICT_RISK[verdict]];

  return (
    <View testID="rotation-planner">
      {/* ---------- headline ---------- */}
      {loading && !result ? <Loading label={tr("plan.years.checking")} /> : null}
      {error && !result ? <ErrorView message={error} onRetry={run} /> : null}
      {result ? (
        <Card testID="rplan-headline" style={{ backgroundColor: vc.bg, borderColor: vc.bg }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: space.md }}>
            <Ionicons name={VERDICT_ICON[verdict]} size={30} color={vc.dot} />
            <View style={{ flex: 1 }}>
              <Txt v="h3" color={vc.fg}>
                {result.summary.headline}
              </Txt>
            </View>
            <View style={{ alignItems: "center" }}>
              <Txt v="h2" color={vc.fg}>
                {Math.round(result.summary.score)}
              </Txt>
              <Txt v="small" color={vc.fg}>
                / 100
              </Txt>
            </View>
          </View>
          {stale ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: space.md }}>
              <Txt v="small" color={vc.fg} style={{ flex: 1 }}>
                {tr("plan.years.stale")}
              </Txt>
              <Button label={tr("plan.years.check")} onPress={run} icon="refresh" kind="secondary" testID="rplan-check" />
            </View>
          ) : null}
        </Card>
      ) : null}

      {/* ---------- year timeline ---------- */}
      {result ? (
        <>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: space.md }} contentContainerStyle={{ gap: space.sm }}>
            {result.years.map((y) => {
              const c = t.risk[VERDICT_RISK[y.verdict]];
              const active = selected === y.year;
              return (
                <Pressable
                  key={y.year}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={tr("plan.years.yearA11y", {
                    year: y.year,
                    crop: cropName(crops, y.crop),
                    verdict: tr(`plan.years.verdict.${y.verdict}`),
                  })}
                  onPress={() => setSelected(active ? null : y.year)}
                  testID={`rplan-year-${y.year}`}
                  style={{
                    width: 132,
                    padding: space.md,
                    borderRadius: radius.lg,
                    backgroundColor: t.card,
                    borderWidth: active ? 2 : 1,
                    borderColor: active ? t.primary : t.border,
                  }}
                >
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                    <Txt v="label">{y.year}</Txt>
                    <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: c.dot }} />
                  </View>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: space.sm }}>
                    <Ionicons name={cropIcon(crops.find((x) => x.id === y.crop))} size={16} color={t.primary} />
                    <Txt v="small" style={{ fontWeight: "600", flex: 1 }} numberOfLines={2}>
                      {cropName(crops, y.crop)}
                    </Txt>
                  </View>
                  {y.cover_crop ? (
                    <Txt v="small" muted numberOfLines={1}>
                      + {cropName(crops, y.cover_crop)}
                    </Txt>
                  ) : null}
                  <Txt v="small" muted style={{ marginTop: space.sm }}>
                    {fmt(yv(y.sim.yield_t_ha), yUnit, sys, 1)}
                  </Txt>
                  <Txt v="small" muted>
                    💧 {fmt(y.sim.irrigation_mm || y.sim.water_use_mm, "mm", sys, 0)}
                  </Txt>
                  <Txt v="small" muted>
                    N {y.sim.n_balance_kg_ha >= 0 ? "+" : ""}
                    {Math.round(y.sim.n_balance_kg_ha)}
                  </Txt>
                </Pressable>
              );
            })}
          </ScrollView>

          {sel ? (
            <Card testID="rplan-detail">
              <Txt v="h3">
                {sel.year} · {cropName(crops, sel.crop)}
                {sel.cover_crop ? ` + ${cropName(crops, sel.cover_crop)}` : ""}
              </Txt>
              {sel.issues.length === 0 && sel.benefits.length === 0 ? (
                <Txt muted style={{ marginTop: space.sm }}>
                  {tr("plan.years.noIssues")}
                </Txt>
              ) : null}
              {sel.issues.map((iss, i) => {
                const rc = t.risk[iss.severity === "problem" ? "severe" : iss.severity === "caution" ? "moderate" : "low"];
                return (
                  <View key={iss.id + i} style={{ marginTop: space.md, flexDirection: "row", gap: space.sm }} testID={`rplan-issue-${i}`}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: rc.dot, marginTop: 8 }} />
                    <View style={{ flex: 1 }}>
                      <Txt v="label">{iss.title}</Txt>
                      <Txt style={{ marginTop: 2 }}>{iss.explanation}</Txt>
                      {iss.suggestion ? (
                        <Txt style={{ marginTop: 4 }} color={t.primary}>
                          → {iss.suggestion}
                        </Txt>
                      ) : null}
                      {iss.sources.length ? (
                        <Txt v="small" muted style={{ marginTop: 4 }}>
                          {tr("plan.years.source")}: {iss.sources.join("; ")}
                        </Txt>
                      ) : null}
                    </View>
                  </View>
                );
              })}
              {sel.benefits.map((b, i) => (
                <View key={i} style={{ marginTop: space.md, flexDirection: "row", gap: space.sm }}>
                  <Ionicons name="add-circle" size={16} color={t.risk.low.dot} style={{ marginTop: 3 }} />
                  <Txt style={{ flex: 1 }}>{b}</Txt>
                </View>
              ))}
              <StatRow>
                <Stat
                  label={tr("plan.years.yield")}
                  value={fmt(yv(sel.sim.yield_t_ha), yUnit, sys, 1)}
                  sub={`${tr("plan.badYear")}: ${fmt(yv(sel.sim.yield_p10), yUnit, sys, 1)}`}
                />
                <Stat label={tr("plan.years.water")} value={fmt(sel.sim.irrigation_mm || sel.sim.water_use_mm, "mm", sys, 0)} />
                <Stat label={tr("plan.years.nitrogen")} value={`${sel.sim.n_balance_kg_ha >= 0 ? "+" : ""}${Math.round(sel.sim.n_balance_kg_ha)} kg/ha`} />
              </StatRow>
              {settings.expert ? (
                <Txt v="small" muted style={{ marginTop: space.sm }}>
                  {tr("plan.years.expert", {
                    margin: Math.round(sel.sim.margin_usd_ha),
                    bare: sel.sim.bare_days,
                    effect: sel.sim.rotation_effect_pct,
                    erosion: sel.sim.erosion_t_ha ?? "–",
                  })}
                </Txt>
              ) : null}
            </Card>
          ) : (
            <Txt v="small" muted style={{ marginTop: space.sm }}>
              {tr("plan.years.tapYear")}
            </Txt>
          )}

          {result.summary.disease_pressure.length ? (
            <Disclosure title={tr("plan.years.diseaseTitle")} subtitle={tr("plan.years.diseaseSubtitle")} icon="bug-outline" testID="rplan-disease">
              {result.summary.disease_pressure.map((d) => (
                <View key={d.pathogen} style={{ marginTop: space.sm }}>
                  <Txt v="small" style={{ fontWeight: "600" }}>
                    {d.name}
                  </Txt>
                  <View style={{ flexDirection: "row", gap: 4, marginTop: 4 }}>
                    {result.years.map((y) => {
                      const on = d.years.includes(y.year);
                      const rk = on ? (d.level === "high" ? "severe" : d.level === "medium" ? "moderate" : "low") : null;
                      return (
                        <View
                          key={y.year}
                          style={{ flex: 1, height: 18, borderRadius: 4, backgroundColor: rk ? t.risk[rk].dot : t.cardAlt }}
                          accessibilityLabel={`${y.year}: ${on ? d.level : "—"}`}
                        />
                      );
                    })}
                  </View>
                </View>
              ))}
            </Disclosure>
          ) : null}

          {/* ---------- improvements ---------- */}
          {result.optimized || result.suggestions.length || result.impact ? (
            <Section title={tr("plan.years.improve")}>
              {result.impact ? <ImpactCard impact={result.impact} /> : null}
              {result.optimized && result.optimized.score > result.summary.score + 0.5 ? (
                <Card testID="rplan-optimized">
                  <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                    <Ionicons name="sparkles" size={20} color={t.accent} />
                    <Txt v="h3" style={{ flex: 1 }}>
                      {tr("plan.years.optimized")}
                    </Txt>
                    <Txt v="label" color={t.primary}>
                      {Math.round(result.summary.score)} → {Math.round(result.optimized.score)}
                    </Txt>
                  </View>
                  <Txt style={{ marginTop: space.sm }}>
                    {result.optimized.plan
                      .map((p) => `${p.year}: ${cropName(crops, p.crop)}${p.cover_crop ? ` + ${cropName(crops, p.cover_crop)}` : ""}`)
                      .join(" → ")}
                  </Txt>
                  <Txt v="small" muted style={{ marginTop: space.sm }}>
                    {result.optimized.explanation}
                  </Txt>
                  <Button
                    label={tr("plan.years.apply")}
                    onPress={() => apply(result.optimized!.plan)}
                    icon="checkmark"
                    style={{ marginTop: space.md }}
                    testID="rplan-optimized-apply"
                  />
                </Card>
              ) : null}
              {result.suggestions.map((s, i) => (
                <Card key={i} testID={`rplan-suggestion-${i}`}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
                    <Txt v="label" style={{ flex: 1 }}>
                      {s.title}
                    </Txt>
                    <Txt v="small" color={t.primary} style={{ fontWeight: "700" }}>
                      +{Math.round(s.score_gain)}
                    </Txt>
                  </View>
                  <Txt v="small" muted style={{ marginTop: 4 }}>
                    {s.explanation}
                  </Txt>
                  <Button
                    label={tr("plan.years.apply")}
                    kind="secondary"
                    onPress={() => apply(s.plan)}
                    style={{ marginTop: space.sm }}
                    testID={`rplan-suggestion-${i}-apply`}
                  />
                </Card>
              ))}
            </Section>
          ) : null}
        </>
      ) : null}

      {/* ---------- editor ---------- */}
      <Section title={tr("plan.years.yourPlan")} right={<InfoButton term="rotation" />}>
        <Card>
          {plan.map((p) => (
            <View key={p.year} style={{ flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: p === plan[0] ? 0 : space.md }}>
              <Txt v="label" style={{ width: 48 }}>
                {p.year}
              </Txt>
              <View style={{ flex: 3 }}>
                <CropPicker
                  label={tr("plan.years.mainCrop", { year: p.year })}
                  value={p.crop}
                  onChange={(c) => c && savePlan(setPlanCrop(plan, p.year, c))}
                  testID={`rplan-crop-${p.year}`}
                />
              </View>
              <View style={{ flex: 2 }}>
                <CropPicker
                  compact
                  allowNone
                  label={tr("plan.years.coverCrop", { year: p.year })}
                  value={p.cover_crop ?? null}
                  onChange={(c) => savePlan(setPlanCrop(plan, p.year, c ?? "", "cover_crop"))}
                  testID={`rplan-cover-${p.year}`}
                />
              </View>
            </View>
          ))}
          <View style={{ flexDirection: "row", gap: space.sm, marginTop: space.lg, flexWrap: "wrap" }}>
            <Button
              label={tr("plan.years.addYear")}
              kind="secondary"
              icon="add"
              onPress={() => savePlan(addPlanYear(plan, field.crop))}
              disabled={plan.length >= 8}
            />
            <Button
              label={tr("plan.years.removeYear")}
              kind="ghost"
              icon="remove"
              onPress={() => savePlan(removeLastPlanYear(plan))}
              disabled={plan.length <= 1}
            />
          </View>
          <Txt v="small" muted style={{ marginTop: space.sm }}>
            {tr("plan.years.coverHint")}
          </Txt>
        </Card>
        <Disclosure title={tr("plan.years.history")} subtitle={tr("plan.years.historyHint")} icon="time-outline" testID="rplan-history">
          {history.map((h) => (
            <View key={h.year} style={{ flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: space.sm }}>
              <Txt v="label" style={{ width: 48 }}>
                {h.year}
              </Txt>
              <View style={{ flex: 1 }}>
                <CropPicker
                  label={tr("plan.years.pastCrop", { year: h.year })}
                  value={h.crop}
                  onChange={(c) => c && saveHistory(history.map((x) => (x.year === h.year ? { ...x, crop: c } : x)))}
                  testID={`rplan-hist-${h.year}`}
                />
              </View>
            </View>
          ))}
        </Disclosure>
        {!result || stale ? (
          <Button
            label={tr("plan.years.check")}
            icon="shield-checkmark"
            onPress={run}
            disabled={loading}
            style={{ marginTop: space.lg }}
            testID="rplan-check-main"
          />
        ) : null}
        {loading && result ? <Loading label={tr("plan.years.checking")} /> : null}
        {error && result ? <ErrorView message={error} onRetry={run} /> : null}
      </Section>

      {result ? (
        <Txt v="small" muted style={{ marginTop: space.xl }}>
          {result.disclaimer}
        </Txt>
      ) : null}
    </View>
  );
}
