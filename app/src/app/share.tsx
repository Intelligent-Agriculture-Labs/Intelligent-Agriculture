import React from "react";
import { Stack } from "expo-router";
import { useTranslation } from "react-i18next";
import { SyncCard } from "@/components/SyncCard";
import { Screen, Txt } from "@/components/ui";
import { space } from "@/lib/theme";

/** Share the farm with a code / QR — for family members or helpers without an account. */
export default function Share() {
  const { t: tr } = useTranslation();
  return (
    <Screen testID="share">
      <Stack.Screen options={{ title: tr("share.title") }} />
      <Txt v="h1">{tr("share.title")}</Txt>
      <Txt muted style={{ marginTop: space.sm }}>
        {tr("share.intro")}
      </Txt>
      <SyncCard />
    </Screen>
  );
}
