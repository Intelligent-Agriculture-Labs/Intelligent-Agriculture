import "@/i18n";
import React from "react";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";
import { StoreProvider } from "@/state/store";
import { useTheme } from "@/lib/theme";
import { CaptureTour } from "@/lib/captureTour";

function RootStack() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  return (
    <>
      <StatusBar style="auto" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: t.bg },
          headerTintColor: t.primary,
          headerTitleStyle: { color: t.text },
          contentStyle: { backgroundColor: t.bg },
          headerBackTitle: tr("common.back"),
        }}
      >
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="onboarding" options={{ title: tr("app.name"), headerShown: false }} />
        <Stack.Screen name="why/[cardId]" options={{ title: tr("why.title"), presentation: "card" }} />
        <Stack.Screen name="welcome" options={{ headerShown: false }} />
        <Stack.Screen name="account" options={{ title: tr("account.title") }} />
        <Stack.Screen name="share" options={{ title: tr("share.title") }} />
        <Stack.Screen name="glossary" options={{ title: tr("glossary.title") }} />
      </Stack>
    </>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StoreProvider>
        <RootStack />
        <CaptureTour />
      </StoreProvider>
    </SafeAreaProvider>
  );
}
