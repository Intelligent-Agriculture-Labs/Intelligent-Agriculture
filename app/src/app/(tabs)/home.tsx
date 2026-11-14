import React from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { Redirect, router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { ActionCard, cropName, useCrops } from "@/components/domain";
import { Card, ErrorView, KV, Loading, OriginBanner, RiskBadge, Section, Txt, styles as ui } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { fmt } from "@/lib/units";
import { useStore } from "@/state/store";
import type { Risk } from "@/api/types";

const droughtRisk = (level: number): Risk => (level <= 0 ? "low" : level <= 2 ? "moderate" : level <= 3 ? "high" : "severe");

export default function Home() {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const { ready, field, setField, advice, refreshAdvice, settings } = useStore();
  const crops = useCrops();
  if (!ready) return <Loading />;
  if (!field) return <Redirect href="/onboarding" />;
  const a = advice.data;
  const sys = settings.units;
  const top = a?.cards.slice().sort((x, y) => x.priority - y.priority) ?? [];
  const nasaSources = a ? Array.from(new Set(a.sources.filter((s) => s.status !== "unavailable").map((s) => s.name.split(" ").slice(0, 2).join(" ")))) : [];

  return (
    <SafeAreaView edges={["top", "left", "right"]} style={{ flex: 1, backgroundColor: t.bg }}>
      <ScrollView
        contentContainerStyle={ui.scroll}
        refreshControl={<RefreshControl refreshing={advice.loading && !!a} onRefresh={refreshAdvice} tintColor={t.primary} />}
      >
        <View style={ui.column} testID="home">
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: space.md }}>
            <View style={{ flex: 1 }}>
              <Txt v="h1">{tr("home.title")}</Txt>
              <Txt muted style={{ marginTop: 2 }}>
                {tr("home.subtitle", { crop: cropName(crops, field.crop), place: field.name })}
              </Txt>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={tr("home.changeField")}
              onPress={() => router.push("/onboarding")}
              style={{ minHeight: 44, minWidth: 44, alignItems: "center", justifyContent: "center" }}
              testID="change-field"
            >
              <Ionicons name="location" size={24} color={t.primary} />
              <Txt v="small" color={t.primary}>
                {tr("common.change")}
              </Txt>
            </Pressable>
          </View>

          {field.replay_date ? (
            <View style={{ marginTop: space.md }}>
              <View
                accessibilityRole="radiogroup"
                style={{ flexDirection: "row", backgroundColor: t.cardAlt, borderRadius: 12, padding: 4, gap: 4 }}
              >
                {[null, field.replay_date].map((d) => {
                  const active = (field.as_of ?? null) === d;
                  const label = d
                    ? tr("home.modeReplay", {
                        date: new Date(d + "T00:00:00Z").toLocaleDateString(i18n.language, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }),
                      })
                    : tr("home.modeToday");
                  return (
                    <Pressable
                      key={d ?? "today"}
                      accessibilityRole="radio"
                      accessibilityState={{ checked: active }}
                      accessibilityLabel={label}
                      onPress={() => setField({ ...field, as_of: d })}
                      testID={d ? "mode-replay" : "mode-today"}
                      style={{
                        flex: 1,
                        minHeight: 44,
                        borderRadius: 9,
                        alignItems: "center",
                        justifyContent: "center",
                        backgroundColor: active ? t.card : "transparent",
                      }}
                    >
                      <Txt v="small" style={{ fontWeight: active ? "700" : "500" }} color={active ? t.primary : t.textMuted}>
                        {label}
                      </Txt>
                    </Pressable>
                  );
                })}
              </View>
              {field.as_of ? (
                <Txt v="small" muted style={{ marginTop: 4 }}>
                  {tr("home.replayNote", {
                    date: new Date(field.as_of + "T00:00:00Z").toLocaleDateString(i18n.language, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }),
                  })}
                </Txt>
              ) : null}
            </View>
          ) : null}

          <OriginBanner origin={advice.origin} savedAt={advice.savedAt} demo={a?.offline && advice.origin === "live"} />
          {a?.mock && advice.origin !== "mock" ? <OriginBanner origin="mock" /> : null}

          {!a && advice.loading ? <Loading /> : null}
          {!a && advice.error ? <ErrorView message={advice.error} onRetry={refreshAdvice} /> : null}

          {a ? (
            <>
              <Section
                title={tr("home.topActions")}
                right={
                  <Txt v="small" muted>
                    {tr("home.updated", { date: new Date(a.generated_at).toLocaleDateString(i18n.language) })}
                  </Txt>
                }
              >
                {top.slice(0, 3).map((c, i) => (
                  <ActionCard key={c.id} card={c} system={sys} testID={`action-card-${i}`} />
                ))}
              </Section>

              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${tr("home.drought")}: ${a.drought.label}`}
                onPress={() => router.push({ pathname: "/why/[cardId]", params: { cardId: "__drought" } })}
                testID="drought-chip"
              >
                <Card>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                    <Txt v="h3">{tr("home.drought")}</Txt>
                    <RiskBadge risk={droughtRisk(a.drought.level)} label={a.drought.label} />
                  </View>
                  <View style={{ flexDirection: "row", gap: space.lg, marginTop: space.sm, flexWrap: "wrap" }}>
                    {a.drought.spi90 !== null ? (
                      <Txt v="small" muted>
                        SPI-90: {a.drought.spi90.toFixed(1)}
                      </Txt>
                    ) : null}
                    {a.drought.sm_percentile !== null ? (
                      <Txt v="small" muted>
                        SMAP: P{Math.round(a.drought.sm_percentile)}
                      </Txt>
                    ) : null}
                    {a.drought.vhi !== null ? (
                      <Txt v="small" muted>
                        VHI: {Math.round(a.drought.vhi)}
                      </Txt>
                    ) : null}
                    <Txt v="small" color={t.link}>
                      {tr("home.why")} ›
                    </Txt>
                  </View>
                </Card>
              </Pressable>

              <Section title={tr("home.water")}>
                <Card>
                  <Txt v="label">{tr("home.rootZone")}</Txt>
                  <View style={{ height: 14, borderRadius: 7, backgroundColor: t.cardAlt, marginTop: 6, overflow: "hidden" }}>
                    <View
                      style={{
                        width: `${Math.min(100, (a.water.root_zone_depletion_mm / Math.max(1, a.water.taw_mm)) * 100)}%`,
                        height: 14,
                        backgroundColor: a.water.root_zone_depletion_mm > a.water.raw_mm ? t.risk.high.dot : t.chart[1],
                      }}
                    />
                  </View>
                  <Txt v="small" muted style={{ marginTop: 4 }}>
                    {fmt(a.water.root_zone_depletion_mm, "mm", sys)} / {fmt(a.water.taw_mm, "mm", sys)}
                  </Txt>
                  <View style={{ marginTop: space.sm }}>
                    <KV
                      k={tr("home.nextIrrigation")}
                      v={
                        a.water.next_irrigation_date
                          ? `${fmt(a.water.next_irrigation_mm, "mm", sys)} · ${new Date(a.water.next_irrigation_date + "T00:00:00Z").toLocaleDateString(i18n.language, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" })}`
                          : tr("home.noIrrigationNeeded")
                      }
                    />
                    <KV k={tr("home.rain7d")} v={fmt(a.water.forecast_rain_7d_mm, "mm", sys)} />
                    <KV k={tr("home.et7d")} v={fmt(a.water.forecast_et0_7d_mm, "mm", sys)} />
                  </View>
                </Card>
                <Card alt>
                  <Txt v="label">{tr("home.seasonSoFar")}</Txt>
                  <KV k={tr("home.seasonEt")} v={fmt(a.water.season_et_mm, "mm", sys)} />
                  <KV k={tr("home.seasonRain")} v={fmt(a.water.season_rain_mm, "mm", sys)} />
                  <KV k={tr("home.seasonIrr")} v={fmt(a.water.season_irrigation_mm, "mm", sys)} />
                </Card>
              </Section>

              {top.length > 3 ? (
                <Section title={tr("home.moreActions")}>
                  {top.slice(3).map((c) => (
                    <ActionCard key={c.id} card={c} system={sys} compact />
                  ))}
                </Section>
              ) : null}

              <Txt v="small" muted style={{ marginTop: space.xl }} testID="attribution">
                {tr("home.attribution", { list: nasaSources.join(", ") })}
              </Txt>
            </>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
