import React, { useMemo, useState } from "react";
import { TextInput, View } from "react-native";
import { Stack } from "expo-router";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { GlossaryEntry } from "@/api/types";
import { Disclosure, GLOSSARY_TERMS } from "@/components/kit";
import { Screen, Txt, styles as ui } from "@/components/ui";
import { useQuery } from "@/lib/useQuery";
import { space, useTheme } from "@/lib/theme";
import { useStore } from "@/state/store";

/** Server glossary ids → bundled glossary keys (so the two lists merge without duplicates). */
const SERVER_TO_BUNDLED: Record<string, string> = {
  et0: "waterDemand",
  soil_water: "soilWater",
  ndvi: "greenness",
  spi: "rainVsNormal",
  drought_levels: "drought",
  kc: "cropWaterFactor",
  rotation: "rotation",
  return_interval: "returnInterval",
  n_credit: "nitrogen",
  erosion: "erosion",
  wetness: "wetness",
  frost_hollow: "frostHollow",
  management_zones: "zones",
  confidence: "confidence",
};

/** Every technical word in plain language. Server glossary when available, bundled copy as fallback. */
export default function Glossary() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { settings } = useStore();
  const q = useQuery<GlossaryEntry[]>(`glossary-${settings.lang}`, () => api.glossary(settings.lang));
  const [search, setSearch] = useState("");
  const bundled: GlossaryEntry[] = useMemo(
    () =>
      GLOSSARY_TERMS.map((k) => ({
        id: k,
        term: tr(`glossary.items.${k}.term`),
        plain: tr(`glossary.items.${k}.plain`),
        why_it_matters: tr(`glossary.items.${k}.why`),
      })),
    [tr],
  );
  const entries = useMemo(() => {
    const server = q.data ?? [];
    const seenIds = new Set(server.map((e) => (e.id ? (SERVER_TO_BUNDLED[e.id] ?? e.id) : "")));
    const seenTerms = new Set(server.map((e) => e.term.toLowerCase()));
    const all = [...server, ...bundled.filter((b) => !seenIds.has(b.id ?? "") && !seenTerms.has(b.term.toLowerCase()))];
    const s = search.trim().toLowerCase();
    return all.filter((e) => !s || e.term.toLowerCase().includes(s) || e.plain.toLowerCase().includes(s)).sort((a, b) => a.term.localeCompare(b.term));
  }, [q.data, bundled, search]);
  return (
    <Screen testID="glossary">
      <Stack.Screen options={{ title: tr("glossary.title") }} />
      <Txt v="h1">{tr("glossary.title")}</Txt>
      <Txt muted style={{ marginTop: space.sm }}>
        {tr("glossary.intro")}
      </Txt>
      <TextInput
        value={search}
        onChangeText={setSearch}
        placeholder={tr("glossary.search")}
        placeholderTextColor={t.textMuted}
        accessibilityLabel={tr("glossary.search")}
        style={[ui.input, { color: t.text, borderColor: t.border, backgroundColor: t.card, marginTop: space.lg }]}
        testID="glossary-search"
      />
      {entries.map((e, i) => (
        <Disclosure key={e.term + i} title={e.term} subtitle={e.plain} testID={i === 0 ? "glossary-first" : undefined}>
          <View>
            <Txt>{e.plain}</Txt>
            <Txt v="small" muted style={{ marginTop: space.sm }}>
              {e.why_it_matters}
            </Txt>
          </View>
        </Disclosure>
      ))}
    </Screen>
  );
}
