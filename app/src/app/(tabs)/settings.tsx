import React, { useEffect, useState } from "react";
import { Linking, Platform, Switch, TextInput, View } from "react-native";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api } from "@/api/client";
import { cropName, useCrops } from "@/components/domain";
import { DOCS_BASE } from "@/components/WhyView";
import { Button, Card, Chip, ChipRow, KV, Screen, Section, Txt, styles as ui } from "@/components/ui";
import { QrCode } from "@/components/QrCode";
import { useSyncLabel } from "@/components/FieldSwitcher";
import { formatSyncCode, isValidSyncCode } from "@/state/farm";
import { LANGUAGES } from "@/i18n";
import { space, useTheme } from "@/lib/theme";
import { toFieldInput, useStore } from "@/state/store";

export default function Settings() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { settings, setSettings, field, fields, sync, enableSync, joinFarm, leaveSync, syncNow, farmName, setFarmName } = useStore();
  const syncLabel = useSyncLabel();
  const [joinCode, setJoinCode] = useState("");
  const [syncErr, setSyncErr] = useState<string | null>(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const runSync = async (fn: () => Promise<void>) => {
    setSyncErr(null);
    setSyncBusy(true);
    try {
      await fn();
    } catch (e) {
      setSyncErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncBusy(false);
    }
  };
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

      <Section title={tr("sync.title")}>
        <Card testID="sync-card">
          <Txt muted>{tr("sync.intro")}</Txt>
          <View style={{ marginTop: space.md }}>
            <Txt v="label">{tr("sync.farmName")}</Txt>
            <TextInput
              accessibilityLabel={tr("sync.farmName")}
              value={farmName}
              onChangeText={setFarmName}
              style={[ui.input, { color: t.text, borderColor: t.border, backgroundColor: t.card, marginTop: space.xs }]}
              testID="farm-name"
            />
          </View>
          {sync.enabled && sync.syncCode ? (
            <View style={{ marginTop: space.md, alignItems: "center", gap: space.sm }}>
              <Txt v="label">{tr("sync.yourCode")}</Txt>
              <Txt v="h1" style={{ letterSpacing: 4 }} testID="sync-code" accessibilityRole="text">
                {formatSyncCode(sync.syncCode)}
              </Txt>
              <View style={{ padding: space.sm, backgroundColor: "#ffffff", borderRadius: 12 }}>
                <QrCode value={`fieldshift://join?code=${formatSyncCode(sync.syncCode)}`} size={180} accessibilityLabel={tr("sync.qrA11y")} />
              </View>
              <Txt v="small" muted style={{ textAlign: "center" }}>
                {tr("sync.codeHint")}
              </Txt>
              <Txt v="small" testID="sync-status">
                {syncLabel}
              </Txt>
              <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap", justifyContent: "center" }}>
                <Button kind="secondary" icon="sync" label={tr("sync.syncNow")} onPress={() => runSync(syncNow)} disabled={syncBusy} testID="sync-now" />
                <Button kind="ghost" icon="log-out-outline" label={tr("sync.leave")} onPress={leaveSync} />
              </View>
            </View>
          ) : (
            <View style={{ marginTop: space.md, gap: space.sm }}>
              <Button icon="cloud-upload" label={tr("sync.enable")} onPress={() => runSync(enableSync)} disabled={syncBusy} testID="sync-enable" />
              <Txt v="label" style={{ marginTop: space.sm }}>
                {tr("sync.joinLabel")}
              </Txt>
              <View style={{ flexDirection: "row", gap: space.sm }}>
                <TextInput
                  accessibilityLabel={tr("sync.joinLabel")}
                  autoCapitalize="characters"
                  placeholder="XXXX-XXXX"
                  placeholderTextColor={t.textMuted}
                  value={joinCode}
                  onChangeText={(v) => setJoinCode(formatSyncCode(v).slice(0, 9))}
                  style={[ui.input, { flex: 1, color: t.text, borderColor: t.border, backgroundColor: t.card, letterSpacing: 2 }]}
                  testID="join-code"
                />
                <Button
                  kind="secondary"
                  label={tr("sync.join")}
                  onPress={() => runSync(() => joinFarm(joinCode))}
                  disabled={syncBusy || !isValidSyncCode(joinCode)}
                  testID="join-button"
                />
              </View>
              <Txt v="small" muted>
                {tr("sync.privacy")}
              </Txt>
            </View>
          )}
          {syncErr ? (
            <Txt v="small" color={t.risk.severe.fg} style={{ marginTop: space.sm }}>
              {syncErr}
            </Txt>
          ) : null}
        </Card>
      </Section>

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
            <KV k={tr("fields.title")} v={String(fields.length)} />
            <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap", marginTop: space.sm }}>
              <Button kind="secondary" icon="create-outline" label={tr("fields.edit")} onPress={() => router.push(`/field-editor?id=${field.id}`)} />
              <Button kind="secondary" icon="add" label={tr("fields.add")} onPress={() => router.push("/field-editor?mode=new")} />
              <Button kind="ghost" icon="albums-outline" label={tr("fields.demoFarms")} onPress={() => router.push("/onboarding")} />
            </View>
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
