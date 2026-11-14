import React from "react";
import { Tabs } from "expo-router";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/lib/theme";

type IonName = React.ComponentProps<typeof Ionicons>["name"];
const icon = (name: IonName) =>
  function TabBarIcon({ color, size }: { color: unknown; size: number }) {
    return <Ionicons name={name} color={String(color)} size={size} />;
  };

export default function TabLayout() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: t.primary,
        tabBarInactiveTintColor: t.textMuted,
        tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border, minHeight: 56 },
        tabBarLabelStyle: { fontSize: 12, fontWeight: "600" },
      }}
    >
      <Tabs.Screen name="home" options={{ title: tr("tabs.home"), tabBarIcon: icon("today"), tabBarButtonTestID: "tab-home" }} />
      <Tabs.Screen name="rotations" options={{ title: tr("tabs.rotations"), tabBarIcon: icon("repeat"), tabBarButtonTestID: "tab-rotations" }} />
      <Tabs.Screen name="whatif" options={{ title: tr("tabs.whatif"), tabBarIcon: icon("flask"), tabBarButtonTestID: "tab-whatif" }} />
      <Tabs.Screen name="climate" options={{ title: tr("tabs.climate"), tabBarIcon: icon("trending-up"), tabBarButtonTestID: "tab-climate" }} />
      <Tabs.Screen name="settings" options={{ title: tr("tabs.settings"), tabBarIcon: icon("settings"), tabBarButtonTestID: "tab-settings" }} />
    </Tabs>
  );
}
