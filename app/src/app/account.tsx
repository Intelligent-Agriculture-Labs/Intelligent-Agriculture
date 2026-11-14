import React, { useState } from "react";
import { Pressable, Switch, TextInput, View } from "react-native";
import { router, Stack } from "expo-router";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import { ApiError } from "@/api/client";
import { Disclosure, Segmented } from "@/components/kit";
import { Button, Card, Screen, Txt, styles as ui } from "@/components/ui";
import { useSyncLabel } from "@/components/FieldSwitcher";
import { validateCredentials } from "@/lib/authStorage";
import { MIN_TOUCH, space, useTheme } from "@/lib/theme";
import { useStore } from "@/state/store";

/** Leave the account screen without stacking a second copy of the tabs underneath. */
function leaveTo(href: "/home" | "/") {
  if (href === "/home" && router.canDismiss()) return router.dismissTo("/home");
  if (router.canDismiss()) router.dismissAll();
  router.replace(href);
}

/** Turn API errors into one friendly sentence. */
export function friendlyError(e: unknown, tr: (k: string) => string): string {
  if (e instanceof ApiError) {
    const m = e.message.match(/"detail"\s*:\s*"([^"]+)"/);
    if (m) return m[1];
    if (e.status === 401) return tr("account.errWrong");
    if (e.status === 409) return tr("account.errExists");
    if (e.status === 429) return tr("account.errTooMany");
    return tr("account.errGeneric");
  }
  return tr("account.errOffline");
}

function Field({
  label,
  value,
  onChange,
  secure,
  testID,
  autoComplete,
  keyboardType,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  secure?: boolean;
  testID?: string;
  autoComplete?: "email" | "password" | "new-password" | "name" | "current-password";
  keyboardType?: "email-address" | "default";
}) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const [show, setShow] = useState(false);
  return (
    <View style={{ marginTop: space.md }}>
      <Txt v="label" style={{ marginBottom: space.xs }}>
        {label}
      </Txt>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <TextInput
          accessibilityLabel={label}
          value={value}
          onChangeText={onChange}
          secureTextEntry={secure && !show}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete={autoComplete}
          keyboardType={keyboardType}
          style={[ui.input, { flex: 1, color: t.text, borderColor: t.border, backgroundColor: t.card }]}
          testID={testID}
        />
        {secure ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={show ? tr("account.hidePassword") : tr("account.showPassword")}
            onPress={() => setShow((s) => !s)}
            style={{ width: MIN_TOUCH, height: MIN_TOUCH, alignItems: "center", justifyContent: "center" }}
            testID={testID ? `${testID}-toggle` : undefined}
          >
            <Ionicons name={show ? "eye-off-outline" : "eye-outline"} size={20} color={t.textMuted} />
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

export default function Account() {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const { auth, fields, register, login, logout, changePassword, deleteAccount } = useStore();
  const syncLabel = useSyncLabel();
  const [mode, setMode] = useState<"login" | "register">(fields.length ? "register" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [upload, setUpload] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [delPw, setDelPw] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);

  const submit = async () => {
    setErr(null);
    const bad = validateCredentials(email, password, mode);
    if (bad) {
      setErr(tr(bad === "email" ? "account.errEmail" : mode === "register" ? "account.errPasswordShort" : "account.errPassword"));
      return;
    }
    try {
      if (mode === "register") await register({ email, password, name, uploadLocal: upload });
      else await login(email, password);
      setPassword("");
      leaveTo(fields.length || mode === "login" ? "/home" : "/");
    } catch (e) {
      setErr(friendlyError(e, tr));
    }
  };

  const title = auth.user ? tr("account.title") : tr(mode === "login" ? "account.loginTitle" : "account.registerTitle");

  return (
    <Screen testID="account">
      <Stack.Screen options={{ title: tr("account.title") }} />
      <Txt v="h1">{title}</Txt>

      {auth.user ? (
        <>
          <Card testID="account-profile">
            <View style={{ flexDirection: "row", alignItems: "center", gap: space.md }}>
              <Ionicons name="person-circle" size={44} color={t.primary} />
              <View style={{ flex: 1 }}>
                <Txt v="h3">{auth.user.name || auth.user.email}</Txt>
                <Txt v="small" muted>
                  {auth.user.email}
                </Txt>
              </View>
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: space.md }}>
              <Ionicons name="cloud-done-outline" size={18} color={t.primary} />
              <Txt v="small" style={{ flex: 1 }} testID="account-sync">
                {tr("account.syncInfo")} · {syncLabel}
              </Txt>
            </View>
            <Txt v="small" muted style={{ marginTop: space.sm }}>
              {tr("account.since", { date: new Date(auth.user.created_at).toLocaleDateString(i18n.language) })}
            </Txt>
          </Card>
          <Button
            label={tr("account.logout")}
            kind="secondary"
            icon="log-out-outline"
            onPress={() => logout().then(() => leaveTo("/"))}
            style={{ marginTop: space.lg }}
            testID="logout"
          />

          <Disclosure title={tr("account.changePassword")} icon="key-outline" testID="change-password">
            <Field label={tr("account.oldPassword")} value={oldPw} onChange={setOldPw} secure autoComplete="current-password" />
            <Field label={tr("account.newPassword")} value={newPw} onChange={setNewPw} secure autoComplete="new-password" />
            <Button
              label={tr("common.save")}
              style={{ marginTop: space.md }}
              disabled={newPw.length < 8 || !oldPw}
              onPress={async () => {
                setErr(null);
                setMsg(null);
                try {
                  await changePassword(oldPw, newPw);
                  setOldPw("");
                  setNewPw("");
                  setMsg(tr("account.passwordChanged"));
                } catch (e) {
                  setErr(friendlyError(e, tr));
                }
              }}
            />
          </Disclosure>

          <Disclosure title={tr("account.delete")} icon="trash-outline" testID="delete-account">
            <Txt v="small" muted>
              {tr("account.deleteHint")}
            </Txt>
            <Field label={tr("account.password")} value={delPw} onChange={setDelPw} secure autoComplete="current-password" />
            {confirmDel ? (
              <Button
                label={tr("account.deleteConfirm")}
                style={{ marginTop: space.md, backgroundColor: t.risk.severe.dot }}
                onPress={async () => {
                  setErr(null);
                  try {
                    await deleteAccount(delPw);
                    leaveTo("/");
                  } catch (e) {
                    setErr(friendlyError(e, tr));
                  }
                }}
                testID="delete-confirm"
              />
            ) : (
              <Button label={tr("account.delete")} kind="secondary" style={{ marginTop: space.md }} disabled={!delPw} onPress={() => setConfirmDel(true)} />
            )}
          </Disclosure>
        </>
      ) : (
        <>
          <Txt muted style={{ marginTop: space.sm }}>
            {tr("account.why")}
          </Txt>
          <Segmented
            style={{ marginTop: space.lg }}
            value={mode}
            onChange={(m) => {
              setMode(m);
              setErr(null);
            }}
            options={[
              { value: "login", label: tr("account.login"), testID: "auth-mode-login" },
              { value: "register", label: tr("account.register"), testID: "auth-mode-register" },
            ]}
          />
          {mode === "register" ? <Field label={tr("account.name")} value={name} onChange={setName} autoComplete="name" testID="auth-name" /> : null}
          <Field label={tr("account.email")} value={email} onChange={setEmail} autoComplete="email" keyboardType="email-address" testID="auth-email" />
          <Field
            label={mode === "register" ? tr("account.passwordNew") : tr("account.password")}
            value={password}
            onChange={setPassword}
            secure
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            testID="auth-password"
          />
          {mode === "register" && fields.length ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: space.md, marginTop: space.lg }}>
              <Txt style={{ flex: 1 }}>{tr("account.uploadLocal", { count: fields.length })}</Txt>
              <Switch
                accessibilityLabel={tr("account.uploadLocal", { count: fields.length })}
                value={upload}
                onValueChange={setUpload}
                trackColor={{ true: t.primary, false: t.border }}
              />
            </View>
          ) : null}
          <Button
            label={mode === "login" ? tr("account.login") : tr("account.register")}
            onPress={submit}
            disabled={auth.busy}
            style={{ marginTop: space.xl }}
            testID="auth-submit"
          />
          <Txt v="small" muted style={{ marginTop: space.lg }}>
            {tr("account.privacy")}
          </Txt>
        </>
      )}
      {err ? (
        <Txt color={t.risk.severe.fg} style={{ marginTop: space.md }} testID="auth-error" accessibilityRole="text">
          {err}
        </Txt>
      ) : null}
      {msg ? (
        <Txt color={t.risk.low.fg} style={{ marginTop: space.md }}>
          {msg}
        </Txt>
      ) : null}
    </Screen>
  );
}
