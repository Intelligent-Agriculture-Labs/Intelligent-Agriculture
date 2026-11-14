/**
 * "Impact of the improved plan": what switching from the farmer's plan to the improved one changes —
 * water, climate gas, soil and income — as a few big, honest numbers (trade-offs shown as trade-offs).
 */
import React from "react";
import { View } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import type { RotationPlanResponse } from "@/api/types";
import { Disclosure } from "@/components/kit";
import { Card, Txt } from "@/components/ui";
import { radius, space, useTheme } from "@/lib/theme";

type Impact = NonNullable<RotationPlanResponse["impact"]>;
type IonName = React.ComponentProps<typeof Ionicons>["name"];

export interface ImpactMetric {
  key: "water" | "co2e" | "soil" | "margin" | "nitrogen" | "bare";
  value: number; // positive = better with the improved plan
  unit: string;
  icon: IonName;
}

/** Non-zero metrics in story order (water, climate, soil, money, fertiliser, bare soil); whole-field totals when the area is known. */
export function impactMetrics(impact: Impact): ImpactMetric[] {
  const ft = impact.field_total;
  const ph = impact.per_ha;
  const all: ImpactMetric[] = [
    { key: "water", value: ft ? ft.water_saved_m3_per_yr : ph.water_saved_m3_per_ha_per_yr, unit: ft ? "m³" : "m³/ha", icon: "water" },
    { key: "co2e", value: ft ? ft.co2e_avoided_kg : ph.co2e_avoided_kg_ha, unit: ft ? "kg CO₂e" : "kg CO₂e/ha", icon: "leaf" },
    { key: "soil", value: ft ? ft.soil_kept_t : ph.soil_kept_t_ha, unit: ft ? "t" : "t/ha", icon: "layers" },
    { key: "margin", value: ft ? ft.margin_gain_usd : ph.margin_gain_usd_ha, unit: ft ? "$" : "$/ha", icon: "cash" },
    { key: "nitrogen", value: ft ? ft.n_fertiliser_saved_kg : ph.n_fertiliser_saved_kg_ha, unit: ft ? "kg N" : "kg N/ha", icon: "flask" },
    { key: "bare", value: ph.bare_days_fewer_per_yr, unit: "", icon: "sunny" },
  ];
  return all.filter((m) => Math.abs(m.value) >= 0.05);
}

/** Absolute value, localised, 0 decimals from 100 up, else 1. */
export function formatImpact(v: number, lang: string): string {
  const a = Math.abs(v);
  return a.toLocaleString(lang, { maximumFractionDigits: a >= 100 ? 0 : 1 });
}

/** Big headline number: savings unsigned, trade-offs with "+" (more needed), money signed. */
export function impactValue(m: ImpactMetric, lang: string): string {
  const num = formatImpact(m.value, lang);
  const good = m.value > 0;
  if (m.key === "margin") return `${good ? "+" : "−"}$${num}${m.unit === "$/ha" ? "/ha" : ""}`;
  if (m.key === "bare") return num;
  return `${good ? "" : "+"}${num} ${m.unit}`;
}

export function ImpactCard({ impact }: { impact: Impact }) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const metrics = impactMetrics(impact).slice(0, 4);
  const scope =
    impact.field_total && impact.field_area_ha
      ? tr("plan.impact.scopeField", { area: impact.field_area_ha.toFixed(1), years: impact.years })
      : tr("plan.impact.scopeHa", { years: impact.years });
  return (
    <Card testID="rplan-impact">
      <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
        <Ionicons name="earth" size={22} color={t.primary} />
        <View style={{ flex: 1 }}>
          <Txt v="h3">{tr("plan.impact.title")}</Txt>
          <Txt v="small" muted>
            {scope}
          </Txt>
        </View>
      </View>
      {metrics.length ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginTop: space.md }}>
          {metrics.map((m) => {
            const good = m.value > 0;
            const c = good ? t.risk.low : t.risk.moderate;
            const big = impactValue(m, i18n.language);
            const label = tr(`plan.impact.${m.key}.${good ? "good" : "bad"}`);
            return (
              <View
                key={m.key}
                style={{ flexGrow: 1, flexBasis: "45%", minWidth: 140, backgroundColor: c.bg, borderRadius: radius.md, padding: space.md }}
                testID={`impact-${m.key}`}
                accessible
                accessibilityLabel={`${big} ${label}`}
              >
                <Ionicons name={m.icon} size={20} color={c.dot} />
                <Txt v="h2" color={c.fg} style={{ marginTop: space.xs }}>
                  {big}
                </Txt>
                <Txt v="small" color={c.fg}>
                  {label}
                </Txt>
              </View>
            );
          })}
        </View>
      ) : null}
      <Txt style={{ marginTop: space.md }}>{impact.headline}</Txt>
      <Disclosure title={tr("plan.impact.how")} icon="calculator-outline" testID="rplan-impact-method">
        <Txt v="small" muted>
          {impact.method}
        </Txt>
      </Disclosure>
    </Card>
  );
}
