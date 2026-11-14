import React, { useEffect, useState } from "react";
import { Pressable, View } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { router } from "expo-router";
import { api } from "@/api/client";
import type { ActionCard as ActionCardT, CropInfo, RotationMetric, RotationStrategy } from "@/api/types";
import { MIN_TOUCH, radius, space, useTheme } from "@/lib/theme";
import { fmt, type UnitSystem } from "@/lib/units";
import { RiskBadge, Txt } from "./ui";

type IonName = React.ComponentProps<typeof Ionicons>["name"];
const ICON_FALLBACK: Record<ActionCardT["category"], IonName> = {
  water: "water",
  drought: "sunny",
  disease: "medkit",
  pest: "bug",
  planning: "calendar",
  weather: "thermometer",
};

function safeIcon(name: string, cat: ActionCardT["category"]): IonName {
  return (name in Ionicons.glyphMap ? name : ICON_FALLBACK[cat]) as IonName;
}

export function formatDue(iso: string | null, lang: string): string | null {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang, { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" });
}

export function ActionCard({ card, system, compact, testID }: { card: ActionCardT; system: UnitSystem; compact?: boolean; testID?: string }) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const c = t.risk[card.risk];
  const due = formatDue(card.due, i18n.language);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={tr("a11y.openWhy", { title: card.title })}
      accessibilityHint={card.detail}
      onPress={() =>
        card.id === "plan_rotation" ? router.push("/rotations") : router.push({ pathname: "/why/[cardId]", params: { cardId: card.id } })
      }
      testID={testID}
      style={({ pressed }) => [
        {
          backgroundColor: t.card,
          borderColor: t.border,
          borderWidth: 1,
          borderLeftWidth: 6,
          borderLeftColor: c.dot,
          borderRadius: radius.lg,
          padding: compact ? space.md : space.lg,
          marginTop: space.md,
          opacity: pressed ? 0.9 : 1,
        },
      ]}
    >
      <View style={{ flexDirection: "row", gap: space.md, alignItems: "flex-start" }}>
        <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: c.bg, alignItems: "center", justifyContent: "center" }}>
          <Ionicons name={safeIcon(card.icon, card.category)} size={24} color={c.fg} />
        </View>
        <View style={{ flex: 1 }}>
          <Txt v={compact ? "label" : "h3"}>{card.title}</Txt>
          {!compact ? (
            <Txt muted style={{ marginTop: 4 }}>
              {card.detail}
            </Txt>
          ) : null}
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginTop: space.sm, alignItems: "center" }}>
            <RiskBadge risk={card.risk} />
            {card.amount ? <Txt v="label">{fmt(card.amount.value, card.amount.unit, system)}</Txt> : null}
            {due ? (
              <Txt v="small" muted>
                {tr("common.due", { date: due })}
              </Txt>
            ) : null}
          </View>
        </View>
        <View style={{ alignItems: "center", justifyContent: "center", minHeight: MIN_TOUCH }}>
          <Txt v="small" color={t.link}>
            {tr("home.why")}
          </Txt>
          <Ionicons name="chevron-forward" size={18} color={t.link} />
        </View>
      </View>
    </Pressable>
  );
}

let cropCache: CropInfo[] | null = null;
export function useCrops(): CropInfo[] {
  const [crops, setCrops] = useState<CropInfo[]>(cropCache ?? []);
  useEffect(() => {
    if (cropCache) return;
    api
      .crops()
      .then((r) => {
        cropCache = r.data;
        setCrops(r.data);
      })
      .catch(() => undefined);
  }, []);
  return crops;
}
export function cropName(crops: CropInfo[], id: string | null | undefined): string {
  if (!id) return "—";
  return crops.find((c) => c.id === id)?.name ?? id.replace(/_/g, " ");
}

const CROP_COLORS = ["#2f6b3a", "#1d5e8c", "#b5651d", "#7b4fa0", "#a8323e", "#4d7d2b", "#8c6d1d", "#2b6f7d"];
function cropColor(id: string, palette: string[]) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return palette[h % palette.length];
}

/** Month × year strip: colour = crop, opacity = ground cover, bare months hatched in sand colour. */
export function CoverCalendar({ strategy, crops }: { strategy: RotationStrategy; crops: CropInfo[] }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const years = Array.from(new Set(strategy.calendar.map((c) => c.year))).sort((a, b) => a - b);
  const legend = Array.from(new Set(strategy.calendar.map((c) => c.crop).filter((c): c is string => !!c)));
  const bareMonths = strategy.calendar.filter((c) => c.cover < 0.3).length;
  return (
    <View accessible accessibilityLabel={`${tr("rotations.calendar")}: ${bareMonths} ${tr("rotations.bare")}`}>
      <View style={{ flexDirection: "row", marginBottom: 2, marginLeft: 26 }}>
        {"JFMAMJJASOND".split("").map((m, i) => (
          <Txt key={i} v="small" muted style={{ flex: 1, textAlign: "center", fontSize: 10 }}>
            {m}
          </Txt>
        ))}
      </View>
      {years.map((y) => (
        <View key={y} style={{ flexDirection: "row", alignItems: "center", marginBottom: 2 }}>
          <Txt v="small" muted style={{ width: 26, fontSize: 11 }}>
            Y{y}
          </Txt>
          {Array.from({ length: 12 }, (_, m) => {
            const cell = strategy.calendar.find((c) => c.year === y && c.month === m + 1);
            const cover = cell?.cover ?? 0;
            const bare = cover < 0.3;
            return (
              <View
                key={m}
                style={{
                  flex: 1,
                  height: 18,
                  marginHorizontal: 1,
                  borderRadius: 3,
                  backgroundColor: bare ? t.bare : cropColor(cell?.crop ?? "x", CROP_COLORS),
                  opacity: bare ? 0.9 : 0.35 + 0.65 * cover,
                }}
              />
            );
          })}
        </View>
      ))}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.md, marginTop: space.sm }}>
        {legend.map((id) => (
          <View key={id} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: cropColor(id, CROP_COLORS) }} />
            <Txt v="small">{cropName(crops, id)}</Txt>
          </View>
        ))}
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: t.bare }} />
          <Txt v="small">{tr("rotations.bare")}</Txt>
        </View>
      </View>
    </View>
  );
}

export function MetricBar({ m, system }: { m: RotationMetric; system: UnitSystem }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const col = m.score >= 66 ? t.risk.low.dot : m.score >= 40 ? t.risk.moderate.dot : t.risk.high.dot;
  const delta = Math.round(m.vs_current);
  return (
    <View
      style={{ marginTop: space.sm }}
      accessible
      accessibilityLabel={`${m.label}: ${fmt(m.value, m.unit, system)}, ${Math.round(m.score)}/100, ${delta >= 0 ? "+" : ""}${delta} ${tr("rotations.vsCurrent")}`}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: space.sm }}>
        <Txt v="small" style={{ flex: 1 }}>
          {m.label}
        </Txt>
        <Txt v="small" muted>
          {fmt(m.value, m.unit, system)}
        </Txt>
        {delta !== 0 ? (
          <Txt v="small" color={delta > 0 ? t.risk.low.fg : t.risk.severe.fg} style={{ fontWeight: "700", minWidth: 36, textAlign: "right" }}>
            {delta > 0 ? `+${delta}` : delta}
          </Txt>
        ) : (
          <View style={{ minWidth: 36 }} />
        )}
      </View>
      <View style={{ height: 8, borderRadius: 4, backgroundColor: t.cardAlt, marginTop: 3, overflow: "hidden" }}>
        <View style={{ width: `${Math.max(2, Math.min(100, m.score))}%`, height: 8, backgroundColor: col }} />
      </View>
    </View>
  );
}

export function ScoreRing({ score, label }: { score: number; label: string }) {
  const t = useTheme();
  const col = score >= 66 ? t.risk.low.dot : score >= 40 ? t.risk.moderate.dot : t.risk.high.dot;
  return (
    <View
      accessible
      accessibilityLabel={`${label} ${Math.round(score)}/100`}
      style={{ width: 64, height: 64, borderRadius: 32, borderWidth: 6, borderColor: col, alignItems: "center", justifyContent: "center" }}
    >
      <Txt v="h3">{Math.round(score)}</Txt>
    </View>
  );
}
