import React, { useEffect, useState } from "react";
import { router, Stack, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import { Button, ErrorView, Loading, Screen, Txt } from "@/components/ui";
import { formatSyncCode, isValidSyncCode } from "@/state/farm";
import { useStore } from "@/state/store";

/** Deep link target of the sync QR code: fieldshift://join?code=XXXX-XXXX (also /join?code=… on the web). */
export default function Join() {
  const { t: tr } = useTranslation();
  const { code } = useLocalSearchParams<{ code?: string }>();
  const { ready, joinFarm } = useStore();
  const [state, setState] = useState<"working" | "error" | "invalid">(code && isValidSyncCode(code) ? "working" : "invalid");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!ready || state !== "working" || !code) return;
    joinFarm(code)
      .then(() => router.replace("/home"))
      .catch((e: unknown) => {
        setErr(e instanceof Error ? e.message : String(e));
        setState("error");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  return (
    <Screen testID="join">
      <Stack.Screen options={{ headerShown: false }} />
      <Txt v="h1">{tr("sync.joinTitle")}</Txt>
      {state === "working" ? <Loading label={tr("sync.joining", { code: formatSyncCode(code ?? "") })} /> : null}
      {state === "invalid" ? <Txt>{tr("sync.invalidCode")}</Txt> : null}
      {state === "error" ? <ErrorView message={err ?? ""} /> : null}
      {state !== "working" ? <Button label={tr("sync.openSettings")} onPress={() => router.replace("/settings")} /> : null}
    </Screen>
  );
}
