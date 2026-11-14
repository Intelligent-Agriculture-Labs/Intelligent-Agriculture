import { BackLink } from "@/components/kit";
import React from "react";
import { View } from "react-native";
import { Redirect, router } from "expo-router";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { api } from "@/api/client";
import { useQuery } from "@/lib/useQuery";
import type { ClimateResponse } from "@/api/types";
import { BarChart, TrendChart } from "@/components/charts";
import { Card, ErrorView, Loading, OriginBanner, Screen, Section, Txt } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { fmt } from "@/lib/units";
import { useStore } from "@/state/store";

export default function Climate() {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const { field, settings } = useStore();
  const sys = settings.units;
  const q = useQuery<ClimateResponse>(field ? `${field.lat},${field.lon}` : null, () => api.climate(field!.lat, field!.lon));
  const { data, origin, error } = q;

  if (!field) return <Redirect href="/onboarding" />;
  const y0 = data?.years[0];
  const y15 = data ? data.years[Math.min(14, data.years.length - 1)] : undefined;
  const months = Array.from({ length: 12 }, (_, m) => new Date(Date.UTC(2020, m, 1)).toLocaleDateString(i18n.language, { month: "narrow", timeZone: "UTC" }));

  return (
    <Screen testID="climate">
      <BackLink label={tr("tabs.insights")} onPress={() => router.navigate("/insights")} testID="back-insights" />
      <Txt v="h1">{tr("climate.title")}</Txt>
      <Txt muted style={{ marginTop: 4 }}>
        {tr("climate.subtitle", { start: y0 ?? "1985" })}
      </Txt>
      <OriginBanner origin={origin} />
      {!data && !error ? <Loading /> : null}
      {error ? <ErrorView message={error} onRetry={q.refetch} /> : null}
      {data ? (
        <>
          {data.insights.length ? (
            <Section title={tr("climate.insights")}>
              <Card alt>
                {data.insights.map((s, i) => (
                  <View key={i} style={{ flexDirection: "row", gap: space.sm, marginTop: i ? space.sm : 0 }}>
                    <Ionicons name="bulb" size={18} color={t.accent} style={{ marginTop: 2 }} />
                    <Txt style={{ flex: 1 }}>{s}</Txt>
                  </View>
                ))}
              </Card>
            </Section>
          ) : null}
          {data.metrics.map((m) => {
            const sig = m.p_value < 0.05;
            const trendUnit = m.unit === "°C" ? "°C/decade" : m.unit === "mm" ? "mm/decade" : m.unit;
            return (
              <Card key={m.id}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", gap: space.sm }}>
                  <Txt v="label" style={{ flex: 1 }}>
                    {m.label}
                  </Txt>
                  <Txt v="label" color={sig ? t.accent : t.textMuted}>
                    {m.trend_per_decade >= 0 ? "+" : ""}
                    {fmt(m.trend_per_decade, trendUnit, sys, 1)} {trendUnit.includes("decade") ? "" : tr("climate.perDecade")}
                  </Txt>
                </View>
                <Txt v="small" muted>
                  {sig ? tr("climate.significant") : tr("climate.notSignificant")} (p={m.p_value.toFixed(3)})
                </Txt>
                <TrendChart years={data.years} values={m.values} unit={m.unit} />
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Txt v="small" muted>
                    {tr("climate.then", { start: y0, end: y15 })}: {fmt(m.baseline_mean, m.unit, sys)}
                  </Txt>
                  <Txt v="small">
                    {tr("climate.now")}: {fmt(m.recent_mean, m.unit, sys)}
                  </Txt>
                </View>
              </Card>
            );
          })}
          <Section title={tr("climate.normals")}>
            <Card>
              <BarChart
                label={tr("climate.normals")}
                unit={sys === "imperial" ? "in" : "mm"}
                data={data.monthly_normals.map((n, i) => ({ label: months[i], value: sys === "imperial" ? n.precip / 25.4 : n.precip, color: t.chart[1] }))}
              />
              <Txt v="small" muted>
                ▮ {tr("home.seasonRain")} · ET₀ {data.monthly_normals.map((n) => fmt(n.et0 * 30, "mm", sys, 0)).join(" · ")}
              </Txt>
            </Card>
          </Section>
          <Txt v="small" muted style={{ marginTop: space.lg }}>
            {data.source.name} · {data.source.provider} · {data.source.resolution}
          </Txt>
        </>
      ) : null}
    </Screen>
  );
}
