import React, { useState } from "react";
import { TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Button, Card, Txt, styles as ui } from "@/components/ui";
import { QrCode } from "@/components/QrCode";
import { useSyncLabel } from "@/components/FieldSwitcher";
import { formatSyncCode, isValidSyncCode } from "@/state/farm";
import { space, useTheme } from "@/lib/theme";
import { useStore } from "@/state/store";

/** Share a farm with a short code / QR (family members without an account). */
export function SyncCard() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { sync, enableSync, joinFarm, leaveSync, syncNow, farmName, setFarmName, auth } = useStore();
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
  return (
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
            {!auth.user ? <Button kind="ghost" icon="log-out-outline" label={tr("sync.leave")} onPress={leaveSync} /> : null}
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
  );
}
