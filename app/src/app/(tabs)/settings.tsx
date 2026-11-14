import React, { useEffect, useState } from "react";
import { Linking, Platform, Switch, View } from "react-native";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api } from "@/api/client";
import { cropName, useCrops } from "@/components/domain";
import { DOCS_BASE } from "@/components/WhyView";
import { Button, Card, Chip, ChipRow, KV, Screen, Section, Txt } from "@/components/ui";
import { LANGUAGES } from "@/i18n";
import { space, useTheme } from "@/lib/theme";
import { toFieldInput, useStore } from "@/state/store";

export default function Settings() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { settings, setSettings, field, setField } = useStore();
  const crops = useCrops();
  const [health, setHealth] = useState<string | null>(null);
  const [cleared, setCleared] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(`${tr("settings.online")} · v${h.version}`))
      .catch(() => setHealth(tr("settings.offline")));
  }, [tr]);

  const open = (url: string) => {
    if (Platform.OS === "web") window.open(url, "_blank");
    else Linking.openURL(url);
  };

  return (
    <Screen testID="settings">
      <Txt v="h1">{tr("settings.title")}</Txt>

      <Section title={tr("settings.language")}>
        <ChipRow>
          {LANGUAGES.map((l) => (
            <Chip key={l.code} label={l.label} selected={settings.lang === l.code} onPress={() => setSettings({ lang: l.code })} testID={`lang-${l.code}`} />
          ))}
        </ChipRow>
      </Section>

      <Section title={tr("settings.units")}>
        <ChipRow>
          <Chip label={tr("settings.metric")} selected={settings.units === "metric"} onPress={() => setSettings({ units: "metric" })} testID="units-metric" />
          <Chip
            label={tr("settings.imperial")}
            selected={settings.units === "imperial"}
            onPress={() => setSettings({ units: "imperial" })}
            testID="units-imperial"
          />
        </ChipRow>
      </Section>

      <Section title={tr("settings.expert")}>
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: space.md }}>
            <Txt muted style={{ flex: 1 }}>
              {tr("settings.expertHint")}
            </Txt>
            <Switch
              accessibilityLabel={tr("settings.expert")}
              value={settings.expert}
              onValueChange={(v) => setSettings({ expert: v })}
              trackColor={{ true: t.primary, false: t.border }}
              testID="expert-switch"
            />
          </View>
          {settings.expert && field ? (
            <View style={{ marginTop: space.md, gap: space.sm }}>
              <Txt v="label">{tr("settings.export")}</Txt>
              <Button
                kind="secondary"
                icon="document-text"
                label={tr("settings.exportCsv")}
                onPress={() => open(api.exportUrl("advice.csv", toFieldInput(field, settings.lang)))}
              />
              <Button
                kind="secondary"
                icon="map"
                label={tr("settings.exportGeojson")}
                onPress={() => open(api.exportUrl("field.geojson", toFieldInput(field, settings.lang)))}
              />
              <Button kind="ghost" icon="book" label={tr("settings.methodology")} onPress={() => open(DOCS_BASE)} />
            </View>
          ) : null}
        </Card>
      </Section>

      {field ? (
        <Section title={tr("settings.field")}>
          <Card>
            <KV k="📍" v={field.name} />
            <KV k={tr("whatif.crop")} v={cropName(crops, field.crop)} />
            <KV k={tr("onboarding.plantingDate")} v={field.planting_date} />
            <KV k={tr("onboarding.irrigation")} v={tr(`irrigation.${field.irrigation}`)} />
            <KV k="lat, lon" v={`${field.lat.toFixed(4)}, ${field.lon.toFixed(4)}`} />
            <Button
              kind="secondary"
              icon="location"
              label={tr("home.changeField")}
              onPress={() => router.push("/onboarding")}
              style={{ marginTop: space.sm }}
            />
          </Card>
        </Section>
      ) : null}

      <Section title={tr("settings.server")}>
        <Card>
          <KV k={tr("settings.serverStatus")} v={health ?? "…"} testID="server-status" />
          <KV k="URL" v={api.base} />
          <Button
            kind="ghost"
            icon="trash"
            label={cleared ? tr("settings.cleared") : tr("settings.clearCache")}
            onPress={async () => {
              const keys = await AsyncStorage.getAllKeys();
              await AsyncStorage.multiRemove(keys.filter((k) => k.startsWith("fieldshift:cache:")));
              setCleared(true);
            }}
          />
          <Button
            kind="ghost"
            icon="refresh-circle"
            label={tr("home.changeField")}
            onPress={() => {
              setField(null);
              router.replace("/onboarding");
            }}
          />
        </Card>
      </Section>

      <Section title={tr("settings.about")}>
        <Card alt>
          <Txt>{tr("settings.aboutText")}</Txt>
        </Card>
      </Section>
    </Screen>
  );
}
