import React from "react";
import { useWindowDimensions } from "react-native";
import { Tabs } from "expo-router";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/lib/theme";

type IonName = React.ComponentProps<typeof Ionicons>["name"];
const icon = (name: IonName) =>
  function TabBarIcon({ color, size }: { color: unknown; size: number }) {
    return <Ionicons name={name} color={String(color)} size={size} />;
  };

const TABS: { name: string; icon: IonName }[] = [
  { name: "home", icon: "today" },
  { name: "map", icon: "map" },
  { name: "plan", icon: "calendar" },
  { name: "rotations", icon: "repeat" },
  { name: "whatif", icon: "flask" },
  { name: "climate", icon: "trending-up" },
  { name: "settings", icon: "settings" },
];

export default function TabLayout() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { width } = useWindowDimensions();
  const narrow = width < 700; // 7 tabs: use short labels on phones (full label stays the accessibility label)
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: t.primary,
        tabBarInactiveTintColor: t.textMuted,
        tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border, minHeight: 56 },
        tabBarLabelStyle: { fontSize: narrow ? 10 : 12, fontWeight: "600" },
        tabBarItemStyle: narrow ? { paddingHorizontal: 0 } : undefined,
      }}
    >
      {TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: narrow ? tr(`tabsShort.${tab.name}`) : tr(`tabs.${tab.name}`),
            tabBarAccessibilityLabel: tr(`tabs.${tab.name}`),
            tabBarIcon: icon(tab.icon),
            tabBarButtonTestID: `tab-${tab.name}`,
          }}
        />
      ))}
    </Tabs>
  );
}
