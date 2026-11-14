import React, { useEffect, useState } from "react";
import { Linking, Platform, Switch, View } from "react-native";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Ionicons from "@expo/vector-icons/Ionicons";
import { api } from "@/api/client";
import { cropName, useCrops } from "@/components/domain";
import { DOCS_BASE } from "@/components/WhyView";
import { Disclosure, Group, ListRow, Segmented, Sheet } from "@/components/kit";
import { Button, KV, Screen, Section, Txt } from "@/components/ui";
import { useSyncLabel } from "@/components/FieldSwitcher";
import { LANGUAGES } from "@/i18n";
import { space, useTheme } from "@/lib/theme";
import { toFieldInput, useStore } from "@/state/store";

/** "More": account, sharing, preferences, help and data — calm grouped lists. */
export default function Settings() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { settings, setSettings, field, fields, sync, auth } = useStore();
  const syncLabel = useSyncLabel();
  const crops = useCrops();
  const [health, setHealth] = useState<string | null>(null);
  const [cleared, setCleared] = useState(false);
  const [langOpen, setLangOpen] = useState(false);

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
  const langLabel = LANGUAGES.find((l) => l.code === settings.lang)?.label ?? settings.lang;

  return (
    <Screen testID="settings">
      <Txt v="h1">{tr("settings.title")}</Txt>

      <Group>
        <ListRow
          icon={auth.user ? "person-circle-outline" : "person-add-outline"}
          title={auth.user ? auth.user.name || auth.user.email : tr("account.signInRow")}
          subtitle={auth.user ? `${auth.user.email} · ${syncLabel}` : tr("account.signInRowSub")}
          onPress={() => router.push("/account")}
          testID="row-account"
        />
        <ListRow
          icon="qr-code-outline"
          title={tr("share.title")}
          subtitle={sync.enabled ? syncLabel : tr("share.rowSub")}
          onPress={() => router.push("/share")}
          testID="row-share"
        />
      </Group>

      {field ? (
        <Section title={tr("settings.field")}>
          <Group>
            <ListRow
              icon="create-outline"
              title={field.name}
              subtitle={`${cropName(crops, field.crop)} · ${tr(`irrigation.${field.irrigation}`)} · ${tr("fields.count", { count: fields.length })}`}
              onPress={() => router.push(`/field-editor?id=${field.id}`)}
              testID="row-edit-field"
            />
            <ListRow icon="add-circle-outline" title={tr("fields.add")} onPress={() => router.push("/field-editor?mode=new")} testID="row-add-field" />
            <ListRow icon="albums-outline" title={tr("fields.demoFarms")} onPress={() => router.push("/onboarding")} />
          </Group>
        </Section>
      ) : null}

      <Section title={tr("settings.preferences")}>
        <Group>
          <ListRow icon="language-outline" title={tr("settings.language")} subtitle={langLabel} onPress={() => setLangOpen(true)} testID="row-language" />
          <View style={{ paddingVertical: space.md }}>
            <Txt v="label" style={{ marginBottom: space.sm }}>
              {tr("settings.units")}
            </Txt>
            <Segmented
              value={settings.units}
              onChange={(v) => setSettings({ units: v })}
              options={[
                { value: "metric", label: tr("settings.metric"), testID: "units-metric" },
                { value: "imperial", label: tr("settings.imperial"), testID: "units-imperial" },
              ]}
            />
          </View>
          <ListRow
            icon="flask-outline"
            title={tr("settings.expert")}
            subtitle={tr("settings.expertHint")}
            right={
              <Switch
                accessibilityLabel={tr("settings.expert")}
                value={settings.expert}
                onValueChange={(v) => setSettings({ expert: v })}
                trackColor={{ true: t.primary, false: t.border }}
                testID="expert-switch"
              />
            }
          />
        </Group>
      </Section>

      <Section title={tr("settings.help")}>
        <Group>
          <ListRow
            icon="book-outline"
            title={tr("glossary.title")}
            subtitle={tr("glossary.subtitle")}
            onPress={() => router.push("/glossary")}
            testID="row-glossary"
          />
          <ListRow icon="play-circle-outline" title={tr("welcome.again")} onPress={() => router.push("/welcome")} testID="row-welcome" />
          <ListRow icon="document-text-outline" title={tr("settings.methodology")} onPress={() => open(DOCS_BASE)} />
        </Group>
      </Section>

      {settings.expert && field ? (
        <Section title={tr("settings.export")}>
          <Group>
            <ListRow
              icon="document-text"
              title={tr("settings.exportCsv")}
              onPress={() => open(api.exportUrl("advice.csv", toFieldInput(field, settings.lang)))}
            />
            <ListRow icon="map" title={tr("settings.exportGeojson")} onPress={() => open(api.exportUrl("field.geojson", toFieldInput(field, settings.lang)))} />
          </Group>
        </Section>
      ) : null}

      <Disclosure title={tr("settings.about")} subtitle={health ?? "…"} icon="information-circle-outline" testID="about">
        <Txt>{tr("settings.aboutText")}</Txt>
        <View style={{ marginTop: space.md }}>
          <KV k={tr("settings.serverStatus")} v={health ?? "…"} testID="server-status" />
          <KV k="URL" v={api.base} />
        </View>
        <Button
          kind="ghost"
          icon="trash-outline"
          label={cleared ? tr("settings.cleared") : tr("settings.clearCache")}
          onPress={async () => {
            const keys = await AsyncStorage.getAllKeys();
            await AsyncStorage.multiRemove(keys.filter((k) => k.startsWith("fieldshift:cache:")));
            setCleared(true);
          }}
        />
      </Disclosure>

      <Sheet visible={langOpen} onClose={() => setLangOpen(false)} title={tr("settings.language")}>
        {LANGUAGES.map((l) => (
          <ListRow
            key={l.code}
            title={l.label}
            onPress={() => {
              setSettings({ lang: l.code });
              setLangOpen(false);
            }}
            right={settings.lang === l.code ? <Ionicons name="checkmark" size={20} color={t.primary} /> : <View />}
            testID={`lang-${l.code}`}
          />
        ))}
      </Sheet>
    </Screen>
  );
}
