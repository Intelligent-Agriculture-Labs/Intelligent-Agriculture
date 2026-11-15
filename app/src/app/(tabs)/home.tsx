import React from "react";
import { Pressable, RefreshControl, ScrollView, View } from "react-native";
import { Redirect, router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { ActionCard, cropName, useCrops } from "@/components/domain";
import { IrrigationLog } from "@/components/IrrigationLog";
import { FieldSwitcher } from "@/components/FieldSwitcher";
import { ShareTextButton } from "@/components/ShareText";
import { Disclosure, EmptyState, InfoButton, Segmented, Stat, StatRow, Tip } from "@/components/kit";
import { ErrorView, KV, Loading, OriginBanner, RiskBadge, Txt, styles as ui } from "@/components/ui";
import { radius, space, useTheme } from "@/lib/theme";
import { fmt } from "@/lib/units";
import { useStore } from "@/state/store";
import type { Risk } from "@/api/types";

const droughtRisk = (level: number): Risk => (level <= 0 ? "low" : level <= 2 ? "moderate" : level <= 3 ? "high" : "severe");

export default function Home() {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const { ready, field, setField, advice, refreshAdvice, settings, auth } = useStore();
  const crops = useCrops();
  if (!ready) return <Loading />;
  if (!field) return <Redirect href="/" />;
  const a = advice.data;
  const sys = settings.units;
  const top = a?.cards.slice().sort((x, y) => x.priority - y.priority) ?? [];
  const nasaSources = a ? Array.from(new Set(a.sources.filter((s) => s.status !== "unavailable").map((s) => s.name.split(" ").slice(0, 2).join(" ")))) : [];
  const dateLong = (iso: string) =>
    new Date(iso + "T00:00:00Z").toLocaleDateString(i18n.language, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
  const water = a?.water;
  const usedPct = water && water.taw_mm > 0 ? Math.min(100, (water.root_zone_depletion_mm / water.taw_mm) * 100) : 0;
  const stressed = water ? water.root_zone_depletion_mm > water.raw_mm : false;

  return (
    <SafeAreaView edges={["top", "left", "right"]} style={{ flex: 1, backgroundColor: t.bg }}>
      <ScrollView
        contentContainerStyle={ui.scroll}
        refreshControl={<RefreshControl refreshing={advice.loading && !!a} onRefresh={refreshAdvice} tintColor={t.primary} />}
      >
        <View style={ui.column} testID="home">
          <FieldSwitcher />
          <View style={{ marginTop: space.md }}>
            <Txt v="small" muted>
              {a ? dateLong(a.as_of) : " "}
            </Txt>
            <Txt v="h1" style={{ marginTop: 2 }}>
              {tr("home.title")}
            </Txt>
            <Txt muted style={{ marginTop: 2 }}>
              {tr("home.subtitle", { crop: cropName(crops, field.crop), place: field.name })}
            </Txt>
          </View>

          {field.replay_date ? (
            <View style={{ marginTop: space.lg }}>
              <Segmented
                value={field.as_of ? "replay" : "today"}
                onChange={(v) => setField({ ...field, as_of: v === "replay" ? (field.replay_date ?? null) : null })}
                options={[
                  { value: "today", label: tr("home.modeToday"), testID: "mode-today" },
                  {
                    value: "replay",
                    label: tr("home.modeReplay", {
                      date: new Date(field.replay_date + "T00:00:00Z").toLocaleDateString(i18n.language, {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                        timeZone: "UTC",
                      }),
                    }),
                    testID: "mode-replay",
                  },
                ]}
              />
              {field.as_of ? (
                <Txt v="small" muted style={{ marginTop: space.xs }}>
                  {tr("home.replayNote", {
                    date: new Date(field.as_of + "T00:00:00Z").toLocaleDateString(i18n.language, {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                      timeZone: "UTC",
                    }),
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
              <Tip id="today-v2" text={tr("tips.today")} />
              <View style={{ marginTop: space.sm }}>
                {top.length ? (
                  top.slice(0, 3).map((c, i) => <ActionCard key={c.id} card={c} system={sys} testID={`action-card-${i}`} />)
                ) : (
                  <EmptyState icon="checkmark-circle-outline" title={tr("home.allClearTitle")} text={tr("home.allClearText")} />
                )}
              </View>
              {!field.as_of ? <ShareTextButton /> : null}

              {!auth.user ? (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => router.push("/account")}
                  testID="account-nudge"
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: space.md,
                    marginTop: space.lg,
                    padding: space.md,
                    borderRadius: radius.lg,
                    backgroundColor: t.cardAlt,
                  }}
                >
                  <Ionicons name="phone-portrait-outline" size={20} color={t.primary} />
                  <Txt v="small" style={{ flex: 1 }}>
                    {tr("account.nudge")}
                  </Txt>
                  <Ionicons name="chevron-forward" size={16} color={t.textMuted} />
                </Pressable>
              ) : null}

              <Disclosure title={tr("home.moreTitle")} subtitle={tr("home.moreSubtitle")} icon="leaf-outline" testID="more-week">
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`${tr("home.drought")}: ${a.drought.label}`}
                  onPress={() => router.push({ pathname: "/why/[cardId]", params: { cardId: "__drought" } })}
                  testID="drought-chip"
                  style={{ flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: space.sm }}
                >
                  <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 4 }}>
                    <Txt v="label">{tr("home.drought")}</Txt>
                    <InfoButton term="drought" />
                  </View>
                  <RiskBadge risk={droughtRisk(a.drought.level)} label={a.drought.label} />
                  <Ionicons name="chevron-forward" size={16} color={t.textMuted} />
                </Pressable>
                {settings.expert ? (
                  <Txt v="small" muted>
                    {[
                      a.drought.spi90 !== null ? `SPI-90 ${a.drought.spi90.toFixed(1)}` : null,
                      a.drought.sm_percentile !== null ? `SMAP P${Math.round(a.drought.sm_percentile)}` : null,
                      a.drought.vhi !== null ? `VHI ${Math.round(a.drought.vhi)}` : null,
                      a.drought.grace_da ? tr("home.expertGraceDa", { p: Math.round(a.drought.grace_da.groundwater_pct) }) : null,
                      a.water?.satellite?.smap?.rootzone_m3m3 != null ? `SMAP L4 ${a.water.satellite.smap.rootzone_m3m3.toFixed(2)} m³/m³` : null,
                      a.water?.satellite?.et ? tr("home.expertEcostress", { v: a.water.satellite.et.last_et_mm.toFixed(1) }) : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Txt>
                ) : null}

                {water ? (
                  <View style={{ marginTop: space.lg }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                      <Txt v="label" style={{ flex: 1 }}>
                        {tr("home.rootZone")}
                      </Txt>
                      <InfoButton term="soilWater" />
                    </View>
                    <View style={{ height: 10, borderRadius: 5, backgroundColor: t.cardAlt, marginTop: space.sm, overflow: "hidden" }}>
                      <View style={{ width: `${usedPct}%`, height: 10, backgroundColor: stressed ? t.risk.high.dot : t.chart[1] }} />
                    </View>
                    <Txt v="small" muted style={{ marginTop: 4 }}>
                      {tr("home.waterUsed", { used: fmt(water.root_zone_depletion_mm, "mm", sys), total: fmt(water.taw_mm, "mm", sys) })}
                    </Txt>
                    <StatRow>
                      <Stat
                        label={tr("home.nextIrrigation")}
                        value={water.next_irrigation_date ? fmt(water.next_irrigation_mm, "mm", sys) : tr("home.noIrrigationNeededShort")}
                        sub={
                          water.next_irrigation_date
                            ? new Date(water.next_irrigation_date + "T00:00:00Z").toLocaleDateString(i18n.language, {
                                weekday: "short",
                                month: "short",
                                day: "numeric",
                                timeZone: "UTC",
                              })
                            : null
                        }
                      />
                      <Stat label={tr("home.rain7d")} value={fmt(water.forecast_rain_7d_mm, "mm", sys)} />
                      <Stat label={tr("home.et7d")} value={fmt(water.forecast_et0_7d_mm, "mm", sys)} />
                    </StatRow>
                    {field.irrigation !== "none" && !field.as_of ? (
                      <IrrigationLog
                        date={field.last_irrigation_date}
                        mm={field.last_irrigation_mm}
                        today={a.as_of}
                        system={sys}
                        onSave={(d, mm) => setField({ ...field, last_irrigation_date: d, last_irrigation_mm: mm })}
                      />
                    ) : null}
                  </View>
                ) : null}

                {water ? (
                  <View style={{ marginTop: space.lg }}>
                    <Txt v="label">{tr("home.seasonSoFar")}</Txt>
                    <KV k={tr("home.seasonEt")} v={fmt(water.season_et_mm, "mm", sys)} />
                    <KV k={tr("home.seasonRain")} v={fmt(water.season_rain_mm, "mm", sys)} />
                    <KV k={tr("home.seasonIrr")} v={fmt(water.season_irrigation_mm, "mm", sys)} />
                  </View>
                ) : null}

                {top.length > 3 ? (
                  <View style={{ marginTop: space.lg }}>
                    <Txt v="label">{tr("home.moreActions")}</Txt>
                    {top.slice(3).map((c) => (
                      <ActionCard key={c.id} card={c} system={sys} compact />
                    ))}
                  </View>
                ) : null}
              </Disclosure>

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
