import React from "react";
import { Tabs } from "expo-router";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { useTheme } from "@/lib/theme";
import { ScreenHeaderContext } from "@/components/ui";
import { FieldSwitcher } from "@/components/FieldSwitcher";

type IonName = React.ComponentProps<typeof Ionicons>["name"];
const icon = (name: IonName) =>
  function TabBarIcon({ color, size }: { color: unknown; size: number }) {
    return <Ionicons name={name} color={String(color)} size={size} />;
  };

/** Five calm tabs. What-if, Climate and the rotation explorer live under Insights (tabs without a button, still deep-linkable). */
const TABS: { name: string; icon: IonName }[] = [
  { name: "home", icon: "sunny-outline" },
  { name: "map", icon: "map-outline" },
  { name: "plan", icon: "calendar-outline" },
  { name: "insights", icon: "bulb-outline" },
  { name: "settings", icon: "ellipsis-horizontal-circle-outline" },
];
const HIDDEN = ["rotations", "whatif", "climate"];

export default function TabLayout() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  return (
    <ScreenHeaderContext.Provider value={<FieldSwitcher />}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: t.primary,
          tabBarInactiveTintColor: t.textMuted,
          tabBarStyle: { backgroundColor: t.card, borderTopColor: t.border, minHeight: 58 },
          tabBarLabelStyle: { fontSize: 12, fontWeight: "600" },
        }}
      >
        {TABS.map((tab) => (
          <Tabs.Screen
            key={tab.name}
            name={tab.name}
            options={{
              title: tr(`tabs.${tab.name}`),
              tabBarAccessibilityLabel: tr(`tabs.${tab.name}`),
              tabBarIcon: icon(tab.icon),
              tabBarButtonTestID: `tab-${tab.name}`,
            }}
          />
        ))}
        {HIDDEN.map((name) => (
          // not `href: null`: in this expo-router version hidden tabs redirect away; an invisible tab button keeps them routable
          <Tabs.Screen key={name} name={name} options={{ title: tr(`tabs.${name}`), tabBarButton: () => null, tabBarItemStyle: { display: "none" } }} />
        ))}
      </Tabs>
    </ScreenHeaderContext.Provider>
  );
}
