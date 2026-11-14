import React from "react";
import { Linking, Pressable, View } from "react-native";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { ConfidenceMeter, OVERLAY_SERIES, SeriesChart } from "@/components/charts";
import { Card, Section, Txt } from "@/components/ui";
import { space, useTheme } from "@/lib/theme";
import { fmt } from "@/lib/units";
import { useStore } from "@/state/store";
import type { Series, SourceRef, WhyBlock } from "@/api/types";

export const DOCS_BASE = process.env.EXPO_PUBLIC_DOCS_URL ?? "https://github.com/fieldshift/fieldshift/blob/main/docs/MODELS.md";

export function WhyView({ why, series, sources, expert }: { why: WhyBlock; series: Series[]; sources: SourceRef[]; expert: boolean }) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const { settings } = useStore();
  const all = why.series.map((id) => series.find((s) => s.id === id)).filter((s): s is Series => !!s);
  // threshold-like series are drawn on top of the first chart with the same unit instead of on their own
  const used = all.filter((s) => !OVERLAY_SERIES.has(s.id) || !all.some((p) => !OVERLAY_SERIES.has(p.id) && p.unit === s.unit));
  const overlaysFor = (p: Series) =>
    used.find((u) => u.unit === p.unit && !OVERLAY_SERIES.has(u.id)) === p ? all.filter((s) => OVERLAY_SERIES.has(s.id) && s.unit === p.unit) : [];
  const srcs = why.sources.map((id) => sources.find((s) => s.id === id)).filter((s): s is SourceRef => !!s);
  return (
    <>
      <Card>
        <Txt>{why.summary}</Txt>
      </Card>

      <Section title={tr("why.howWeGotThere")}>
        <Card>
          {why.steps.map((s, i) => (
            <View key={i} style={{ flexDirection: "row", gap: space.sm, marginTop: i ? space.sm : 0 }}>
              <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: t.cardAlt, alignItems: "center", justifyContent: "center" }}>
                <Txt v="small" style={{ fontWeight: "700" }}>
                  {i + 1}
                </Txt>
              </View>
              <Txt style={{ flex: 1 }}>{s}</Txt>
            </View>
          ))}
        </Card>
      </Section>

      {used.length ? (
        <Section title={tr("why.data")}>
          {used.map((s) => (
            <Card key={s.id}>
              <SeriesChart s={s} system={settings.units} testID={`chart-${s.id}`} overlays={overlaysFor(s)} />
              {expert ? (
                <View style={{ marginTop: space.sm }}>
                  <Txt v="small" muted>
                    {tr("settings.rawSeries")} ({s.points.length})
                  </Txt>
                  {s.points.slice(-10).map((p) => (
                    <View key={p.date} style={{ flexDirection: "row", justifyContent: "space-between" }}>
                      <Txt v="small">{p.date}</Txt>
                      <Txt v="small">{p.value === null ? "—" : fmt(p.value, s.unit, settings.units, 2)}</Txt>
                    </View>
                  ))}
                </View>
              ) : null}
            </Card>
          ))}
        </Section>
      ) : null}

      <Section title={tr("common.confidence")}>
        <Card>
          <ConfidenceMeter value={why.confidence} note={why.confidence_note} />
          <View style={{ marginTop: space.md }}>
            <Txt v="small" muted>
              {tr("why.model")}
            </Txt>
            <Txt v="label">{why.model}</Txt>
            <Pressable
              accessibilityRole="link"
              accessibilityLabel={`${tr("common.learnMore")}: ${why.model}`}
              onPress={() => Linking.openURL(`${DOCS_BASE}#${why.model_doc}`)}
              style={{ minHeight: 44, justifyContent: "center" }}
            >
              <Txt v="small" color={t.link}>
                {tr("common.learnMore")} ↗
              </Txt>
            </Pressable>
          </View>
        </Card>
      </Section>

      {why.caveats.length ? (
        <Section title={tr("why.caveats")}>
          <Card alt>
            {why.caveats.map((c, i) => (
              <View key={i} style={{ flexDirection: "row", gap: space.sm, marginTop: i ? space.sm : 0 }}>
                <Ionicons name="information-circle" size={18} color={t.accent} />
                <Txt style={{ flex: 1 }}>{c}</Txt>
              </View>
            ))}
          </Card>
        </Section>
      ) : null}

      {srcs.length ? (
        <Section title={tr("common.sources")}>
          {srcs.map((s) => (
            <Card key={s.id}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: space.sm }}>
                <Txt v="label" style={{ flex: 1 }}>
                  {s.name}
                </Txt>
                <Txt v="small" color={s.is_nasa ? t.primary : t.textMuted} style={{ fontWeight: "700" }}>
                  {s.is_nasa ? tr("why.nasa") : tr("why.partner")}
                </Txt>
              </View>
              <Txt v="small" muted>
                {s.provider}
              </Txt>
              <Txt v="small" muted>
                {tr("why.resolution")}: {s.resolution} · {tr("why.latency")}: {s.latency}
                {s.last_date ? ` · ${tr("why.lastDate")}: ${new Date(s.last_date + "T00:00:00Z").toLocaleDateString(i18n.language, { timeZone: "UTC" })}` : ""}
                {s.status !== "live" ? ` · ${s.status}` : ""}
              </Txt>
              <Pressable
                accessibilityRole="link"
                accessibilityLabel={s.url}
                onPress={() => Linking.openURL(s.url)}
                style={{ minHeight: 36, justifyContent: "center" }}
              >
                <Txt v="small" color={t.link} numberOfLines={1}>
                  {s.url}
                </Txt>
              </Pressable>
            </Card>
          ))}
        </Section>
      ) : null}
    </>
  );
}
