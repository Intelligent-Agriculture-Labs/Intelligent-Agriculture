import React from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type StyleProp, type TextStyle, type ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Slider from "@react-native-community/slider";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { MIN_TOUCH, radius, space, useTheme } from "@/lib/theme";
import type { Risk } from "@/api/types";
import type { Origin } from "@/api/client";

/** Content rendered at the top of every <Screen> inside the tab navigator (the field switcher). */
export const ScreenHeaderContext = React.createContext<React.ReactNode>(null);

export function Screen({ children, scroll = true, testID }: { children: React.ReactNode; scroll?: boolean; testID?: string }) {
  const t = useTheme();
  const header = React.useContext(ScreenHeaderContext);
  const inner = (
    <View style={styles.column}>
      {header}
      {children}
    </View>
  );
  return (
    <SafeAreaView edges={["top", "left", "right"]} style={{ flex: 1, backgroundColor: t.bg }} testID={testID}>
      {scroll ? (
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {inner}
        </ScrollView>
      ) : (
        inner
      )}
    </SafeAreaView>
  );
}

type TxtVariant = "h1" | "h2" | "h3" | "body" | "small" | "label";
export function Txt({
  children,
  v = "body",
  muted,
  style,
  color,
  numberOfLines,
  accessibilityRole,
  testID,
}: {
  children: React.ReactNode;
  v?: TxtVariant;
  muted?: boolean;
  style?: StyleProp<TextStyle>;
  color?: string;
  numberOfLines?: number;
  accessibilityRole?: "header" | "text";
  testID?: string;
}) {
  const t = useTheme();
  return (
    <Text
      numberOfLines={numberOfLines}
      testID={testID}
      accessibilityRole={accessibilityRole ?? (v === "h1" || v === "h2" ? "header" : undefined)}
      style={[styles[v], { color: color ?? (muted ? t.textMuted : t.text) }, style]}
    >
      {children}
    </Text>
  );
}

export function Card({ children, style, alt, testID }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; alt?: boolean; testID?: string }) {
  const t = useTheme();
  return (
    <View testID={testID} style={[styles.card, { backgroundColor: alt ? t.cardAlt : t.card, borderColor: t.border }, style]}>
      {children}
    </View>
  );
}

export function Button({
  label,
  onPress,
  icon,
  kind = "primary",
  disabled,
  accessibilityLabel,
  testID,
  style,
}: {
  label: string;
  onPress: () => void;
  icon?: React.ComponentProps<typeof Ionicons>["name"];
  kind?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  accessibilityLabel?: string;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const t = useTheme();
  const bg = kind === "primary" ? t.primary : kind === "secondary" ? t.cardAlt : "transparent";
  const fg = kind === "primary" ? t.primaryText : t.primary;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !!disabled }}
      onPress={onPress}
      disabled={disabled}
      testID={testID}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1, borderColor: kind === "secondary" ? t.border : "transparent" },
        style,
      ]}
    >
      {icon ? <Ionicons name={icon} size={20} color={fg} /> : null}
      <Text style={[styles.buttonText, { color: fg }]}>{label}</Text>
    </Pressable>
  );
}

export function Chip({
  label,
  selected,
  onPress,
  icon,
  testID,
}: {
  label: string;
  selected?: boolean;
  onPress?: () => void;
  icon?: React.ComponentProps<typeof Ionicons>["name"];
  testID?: string;
}) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected }}
      accessibilityLabel={label}
      onPress={onPress}
      testID={testID}
      style={[styles.chip, { backgroundColor: selected ? t.primary : t.card, borderColor: selected ? t.primary : t.border }]}
    >
      {icon ? <Ionicons name={icon} size={16} color={selected ? t.primaryText : t.text} /> : null}
      <Text style={{ color: selected ? t.primaryText : t.text, fontSize: 15, fontWeight: "500" }}>{label}</Text>
    </Pressable>
  );
}

export function ChipRow({ children }: { children: React.ReactNode }) {
  return <View style={styles.chipRow}>{children}</View>;
}

export function RiskBadge({ risk, label }: { risk: Risk; label?: string }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const c = t.risk[risk];
  const text = label ?? tr(`risk.${risk}`);
  return (
    <View style={[styles.badge, { backgroundColor: c.bg }]} accessibilityLabel={tr("a11y.riskLevel", { level: text })}>
      <View style={[styles.dot, { backgroundColor: c.dot }]} />
      <Text style={{ color: c.fg, fontWeight: "700", fontSize: 13 }}>{text}</Text>
    </View>
  );
}

export function OriginBanner({ origin, savedAt, demo }: { origin: Origin | null; savedAt?: string | null; demo?: boolean }) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  if (origin === "mock")
    return (
      <View style={[styles.banner, { backgroundColor: t.banner.mock }]} accessibilityRole="alert" testID="mock-banner">
        <Ionicons name="warning" size={18} color="#fff" />
        <Text style={styles.bannerText}>{tr("banner.mock")}</Text>
      </View>
    );
  if (origin === "cache")
    return (
      <View style={[styles.banner, { backgroundColor: t.banner.offline }]} accessibilityRole="alert" testID="offline-banner">
        <Ionicons name="cloud-offline" size={18} color="#fff" />
        <Text style={styles.bannerText}>{tr("banner.offline", { date: savedAt ? new Date(savedAt).toLocaleString(i18n.language) : "?" })}</Text>
      </View>
    );
  if (demo)
    return (
      <View style={[styles.banner, { backgroundColor: t.banner.info }]} testID="demo-banner">
        <Ionicons name="archive" size={18} color="#fff" />
        <Text style={styles.bannerText}>{tr("banner.demo")}</Text>
      </View>
    );
  return null;
}

export function Loading({ label }: { label?: string }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  return (
    <View style={styles.center} accessibilityLiveRegion="polite">
      <ActivityIndicator size="large" color={t.primary} />
      <Txt muted style={{ marginTop: space.md }}>
        {label ?? tr("common.loading")}
      </Txt>
    </View>
  );
}

export function ErrorView({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t: tr } = useTranslation();
  return (
    <Card>
      <Txt v="h3">{tr("common.error")}</Txt>
      <Txt muted style={{ marginVertical: space.sm }}>
        {message}
      </Txt>
      {onRetry ? <Button label={tr("common.retry")} onPress={onRetry} icon="refresh" /> : null}
    </Card>
  );
}

export function Section({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <View style={{ marginTop: space.xxl }}>
      <View style={styles.sectionHead}>
        <Txt v="h3" accessibilityRole="header">
          {title}
        </Txt>
        {right}
      </View>
      {children}
    </View>
  );
}

export function LabeledSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  testID,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  testID?: string;
}) {
  const t = useTheme();
  const shown = format ? format(value) : String(value);
  return (
    <View style={{ marginVertical: space.sm }}>
      <View style={styles.sectionHead}>
        <Txt v="label">{label}</Txt>
        <Txt v="label" color={t.primary}>
          {shown}
        </Txt>
      </View>
      <Slider
        testID={testID}
        accessibilityLabel={`${label}: ${shown}`}
        style={{ width: "100%", height: MIN_TOUCH }}
        minimumValue={min}
        maximumValue={max}
        step={step}
        value={value}
        onSlidingComplete={onChange}
        onValueChange={onChange}
        minimumTrackTintColor={t.primary}
        maximumTrackTintColor={t.border}
        thumbTintColor={t.primary}
      />
    </View>
  );
}

export function DateField({ label, value, onChange, testID }: { label: string; value: string; onChange: (v: string) => void; testID?: string }) {
  const t = useTheme();
  const shift = (days: number) => {
    const d = new Date(value + "T00:00:00Z");
    if (Number.isNaN(d.getTime())) return;
    d.setUTCDate(d.getUTCDate() + days);
    onChange(d.toISOString().slice(0, 10));
  };
  return (
    <View style={{ marginVertical: space.sm }}>
      <Txt v="label" style={{ marginBottom: space.xs }}>
        {label}
      </Txt>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
        <IconButton icon="remove" label="-7 days" onPress={() => shift(-7)} />
        <TextInput
          testID={testID}
          accessibilityLabel={label}
          value={value}
          onChangeText={onChange}
          placeholder="YYYY-MM-DD"
          placeholderTextColor={t.textMuted}
          style={[styles.input, { color: t.text, borderColor: t.border, backgroundColor: t.card, flex: 1, textAlign: "center" }]}
        />
        <IconButton icon="add" label="+7 days" onPress={() => shift(7)} />
      </View>
    </View>
  );
}

export function IconButton({
  icon,
  label,
  onPress,
  color,
}: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  onPress: () => void;
  color?: string;
}) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={6}
      style={({ pressed }) => [styles.iconBtn, { backgroundColor: t.cardAlt, borderColor: t.border, opacity: pressed ? 0.7 : 1 }]}
    >
      <Ionicons name={icon} size={20} color={color ?? t.primary} />
    </Pressable>
  );
}

export function KV({ k, v, testID }: { k: string; v: string; testID?: string }) {
  return (
    <View style={styles.kv} testID={testID}>
      <Txt muted style={{ flex: 1 }}>
        {k}
      </Txt>
      <Txt v="label">{v}</Txt>
    </View>
  );
}

export const styles = StyleSheet.create({
  scroll: { paddingBottom: 48 },
  column: { width: "100%", maxWidth: 760, alignSelf: "center", paddingHorizontal: space.lg, paddingTop: space.md, flex: 1 },
  h1: { fontSize: 26, fontWeight: "700", letterSpacing: -0.3, lineHeight: 32 },
  h2: { fontSize: 20, fontWeight: "700", lineHeight: 26 },
  h3: { fontSize: 17, fontWeight: "600", lineHeight: 23 },
  body: { fontSize: 16, lineHeight: 24 },
  small: { fontSize: 13, lineHeight: 19 },
  label: { fontSize: 15, fontWeight: "600" },
  card: { borderRadius: radius.lg, padding: space.lg, borderWidth: 1, marginTop: space.md },
  button: {
    minHeight: MIN_TOUCH + 4,
    borderRadius: radius.md,
    paddingHorizontal: space.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space.sm,
    borderWidth: 1,
  },
  buttonText: { fontSize: 16, fontWeight: "700" },
  chip: {
    minHeight: 40,
    paddingHorizontal: space.md,
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginTop: space.sm },
  badge: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, alignSelf: "flex-start" },
  dot: { width: 10, height: 10, borderRadius: 5 },
  banner: { flexDirection: "row", alignItems: "center", gap: space.sm, padding: space.md, borderRadius: radius.md, marginTop: space.md },
  bannerText: { color: "#fff", fontWeight: "600", flex: 1, fontSize: 14 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: space.xxl },
  sectionHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space.sm },
  input: { minHeight: MIN_TOUCH, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: space.md, fontSize: 16 },
  iconBtn: { width: MIN_TOUCH, height: MIN_TOUCH, borderRadius: radius.md, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  kv: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, gap: space.md },
});
