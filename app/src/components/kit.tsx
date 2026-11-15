/**
 * Calm, minimal building blocks for progressive disclosure:
 * Segmented, Disclosure, Sheet, InfoButton (plain-language glossary), Tip (one-time coach mark), ListRow, Stat,
 * EmptyState and CropPicker (searchable, grouped by plant family — scales to dozens of crops).
 */
import React, { useEffect, useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, TextInput, View, type StyleProp, type ViewStyle } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useTranslation } from "react-i18next";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import type { CropInfo, Lang } from "@/api/types";
import { MIN_TOUCH, radius, space, useTheme } from "@/lib/theme";
import { useCrops } from "./domain";
import { Button, Txt, styles as ui } from "./ui";

/** Crop name in `lang` (falls back to the English name). */
const localName = (c: CropInfo, lang?: string) => c.names?.[lang as Lang] ?? c.name;

type IonName = React.ComponentProps<typeof Ionicons>["name"];

/* ---------- Segmented control ---------- */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  testID,
  style,
}: {
  options: { value: T; label: string; testID?: string }[];
  value: T;
  onChange: (v: T) => void;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const t = useTheme();
  return (
    <View
      accessibilityRole="tablist"
      testID={testID}
      style={[{ flexDirection: "row", backgroundColor: t.cardAlt, borderRadius: radius.md, padding: 3, gap: 3 }, style]}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={o.label}
            testID={o.testID}
            onPress={() => onChange(o.value)}
            style={{
              flex: 1,
              minHeight: 40,
              borderRadius: radius.md - 3,
              alignItems: "center",
              justifyContent: "center",
              paddingHorizontal: space.sm,
              backgroundColor: active ? t.card : "transparent",
            }}
          >
            <Txt v="small" color={active ? t.text : t.textMuted} style={{ fontWeight: active ? "700" : "500" }} numberOfLines={1}>
              {o.label}
            </Txt>
          </Pressable>
        );
      })}
    </View>
  );
}

/* ---------- Disclosure / accordion ---------- */
export function Disclosure({
  title,
  subtitle,
  icon,
  children,
  defaultOpen = false,
  testID,
}: {
  title: string;
  subtitle?: string | null;
  icon?: IonName;
  children: React.ReactNode;
  defaultOpen?: boolean;
  testID?: string;
}) {
  const t = useTheme();
  const [open, setOpen] = useState(defaultOpen);
  return (
    <View style={{ marginTop: space.md, borderRadius: radius.lg, backgroundColor: t.card, borderWidth: 1, borderColor: t.border }} testID={testID}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={title}
        onPress={() => setOpen((o) => !o)}
        style={{ flexDirection: "row", alignItems: "center", gap: space.md, padding: space.lg, minHeight: MIN_TOUCH + 8 }}
        testID={testID ? `${testID}-toggle` : undefined}
      >
        {icon ? <Ionicons name={icon} size={20} color={t.primary} /> : null}
        <View style={{ flex: 1 }}>
          <Txt v="label">{title}</Txt>
          {subtitle ? (
            <Txt v="small" muted>
              {subtitle}
            </Txt>
          ) : null}
        </View>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={20} color={t.textMuted} />
      </Pressable>
      {open ? <View style={{ paddingHorizontal: space.lg, paddingBottom: space.lg }}>{children}</View> : null}
    </View>
  );
}

/* ---------- Bottom sheet ---------- */
export function Sheet({
  visible,
  onClose,
  title,
  children,
  testID,
}: {
  visible: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  testID?: string;
}) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable accessibilityLabel={tr("common.close")} onPress={onClose} style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.35)" }} />
      <View
        testID={testID}
        style={{
          backgroundColor: t.bg,
          borderTopLeftRadius: radius.xl,
          borderTopRightRadius: radius.xl,
          maxHeight: "85%",
          paddingBottom: insets.bottom + space.lg,
          width: "100%",
          maxWidth: 760,
          alignSelf: "center",
        }}
      >
        <View style={{ alignItems: "center", paddingTop: space.sm }}>
          <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: t.border }} />
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", paddingHorizontal: space.lg, paddingTop: space.md, gap: space.md }}>
          <Txt v="h3" style={{ flex: 1 }} accessibilityRole="header">
            {title}
          </Txt>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={tr("common.close")}
            onPress={onClose}
            hitSlop={10}
            style={{ minWidth: MIN_TOUCH, minHeight: MIN_TOUCH, alignItems: "center", justifyContent: "center" }}
          >
            <Ionicons name="close" size={24} color={t.textMuted} />
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={{ paddingHorizontal: space.lg, paddingBottom: space.lg }} keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      </View>
    </Modal>
  );
}

/* ---------- Plain-language info button ---------- */
export const GLOSSARY_TERMS = [
  "waterDemand",
  "soilWater",
  "easyWater",
  "greenness",
  "rainVsNormal",
  "drought",
  "cropWaterFactor",
  "zones",
  "erosion",
  "wetness",
  "frostHollow",
  "rotation",
  "nitrogen",
  "breakCrop",
  "returnInterval",
  "confidence",
  "satellite",
  "yieldBadYear",
] as const;
export type GlossaryTerm = (typeof GLOSSARY_TERMS)[number];

export function InfoButton({ term, size = 18 }: { term: GlossaryTerm; size?: number }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const [open, setOpen] = useState(false);
  const title = tr(`glossary.items.${term}.term`);
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={tr("glossary.explain", { term: title })}
        onPress={() => setOpen(true)}
        hitSlop={12}
        testID={`info-${term}`}
        style={{ width: 28, height: 28, alignItems: "center", justifyContent: "center" }}
      >
        <Ionicons name="help-circle-outline" size={size} color={t.textMuted} />
      </Pressable>
      <Sheet visible={open} onClose={() => setOpen(false)} title={title}>
        <Txt style={{ marginTop: space.sm }}>{tr(`glossary.items.${term}.plain`)}</Txt>
        <Txt v="small" muted style={{ marginTop: space.md }}>
          {tr(`glossary.items.${term}.why`)}
        </Txt>
      </Sheet>
    </>
  );
}

/* ---------- One-time tip (coach mark) ---------- */
const TIP_PREFIX = "fieldshift:tip:";
export function Tip({ id, text, testID }: { id: string; text: string; testID?: string }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const [show, setShow] = useState(false);
  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(TIP_PREFIX + id)
      .then((v) => alive && setShow(v !== "1"))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [id]);
  if (!show) return null;
  return (
    <View
      testID={testID ?? `tip-${id}`}
      style={{
        flexDirection: "row",
        alignItems: "flex-start",
        gap: space.md,
        backgroundColor: t.cardAlt,
        borderRadius: radius.lg,
        padding: space.md,
        marginTop: space.md,
      }}
    >
      <Ionicons name="bulb-outline" size={20} color={t.accent} style={{ marginTop: 2 }} />
      <Txt v="small" style={{ flex: 1 }}>
        {text}
      </Txt>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={tr("common.gotIt")}
        hitSlop={10}
        onPress={() => {
          setShow(false);
          AsyncStorage.setItem(TIP_PREFIX + id, "1").catch(() => undefined);
        }}
      >
        <Txt v="small" color={t.primary} style={{ fontWeight: "700" }}>
          {tr("common.gotIt")}
        </Txt>
      </Pressable>
    </View>
  );
}

/* ---------- List row ---------- */
export function ListRow({
  icon,
  title,
  subtitle,
  onPress,
  right,
  testID,
  danger,
}: {
  icon?: IonName;
  title: string;
  subtitle?: string | null;
  onPress?: () => void;
  right?: React.ReactNode;
  testID?: string;
  danger?: boolean;
}) {
  const t = useTheme();
  const color = danger ? t.risk.severe.dot : t.text;
  return (
    <Pressable
      accessibilityRole={onPress ? "button" : undefined}
      accessibilityLabel={subtitle ? `${title}. ${subtitle}` : title}
      onPress={onPress}
      disabled={!onPress}
      testID={testID}
      style={({ pressed }) => ({
        flexDirection: "row",
        alignItems: "center",
        gap: space.md,
        paddingVertical: space.md,
        minHeight: MIN_TOUCH + 12,
        opacity: pressed ? 0.7 : 1,
      })}
    >
      {icon ? (
        <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: t.cardAlt, alignItems: "center", justifyContent: "center" }}>
          <Ionicons name={icon} size={19} color={danger ? color : t.primary} />
        </View>
      ) : null}
      <View style={{ flex: 1 }}>
        <Txt v="label" color={color}>
          {title}
        </Txt>
        {subtitle ? (
          <Txt v="small" muted>
            {subtitle}
          </Txt>
        ) : null}
      </View>
      {right ?? (onPress ? <Ionicons name="chevron-forward" size={18} color={t.textMuted} /> : null)}
    </Pressable>
  );
}

/** White surface that groups list rows with thin separators. */
export function Group({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  const t = useTheme();
  const items = React.Children.toArray(children).filter(Boolean);
  return (
    <View
      style={[
        { backgroundColor: t.card, borderRadius: radius.lg, borderWidth: 1, borderColor: t.border, paddingHorizontal: space.lg, marginTop: space.md },
        style,
      ]}
    >
      {items.map((c, i) => (
        <View key={i} style={i > 0 ? { borderTopWidth: 1, borderTopColor: t.border } : undefined}>
          {c}
        </View>
      ))}
    </View>
  );
}

/* ---------- Stat tile ---------- */
export function Stat({ label, value, sub, testID }: { label: string; value: string; sub?: string | null; testID?: string }) {
  const t = useTheme();
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: t.cardAlt, borderRadius: radius.md, padding: space.md }} testID={testID}>
      <Txt v="small" muted>
        {label}
      </Txt>
      <Txt v="h3" style={{ marginTop: 2 }}>
        {value}
      </Txt>
      {sub ? (
        <Txt v="small" muted>
          {sub}
        </Txt>
      ) : null}
    </View>
  );
}

export function StatRow({ children }: { children: React.ReactNode }) {
  return <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.sm, marginTop: space.md }}>{children}</View>;
}

/* ---------- Empty state ---------- */
export function EmptyState({
  icon,
  title,
  text,
  action,
  onAction,
  testID,
}: {
  icon: IonName;
  title: string;
  text: string;
  action?: string;
  onAction?: () => void;
  testID?: string;
}) {
  const t = useTheme();
  return (
    <View style={{ alignItems: "center", paddingVertical: space.xxxl, paddingHorizontal: space.lg }} testID={testID}>
      <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: t.cardAlt, alignItems: "center", justifyContent: "center" }}>
        <Ionicons name={icon} size={30} color={t.primary} />
      </View>
      <Txt v="h3" style={{ marginTop: space.lg, textAlign: "center" }}>
        {title}
      </Txt>
      <Txt muted style={{ marginTop: space.sm, textAlign: "center", maxWidth: 420 }}>
        {text}
      </Txt>
      {action && onAction ? <Button label={action} onPress={onAction} style={{ marginTop: space.xl, alignSelf: "stretch" }} /> : null}
    </View>
  );
}

/* ---------- Crop picker (search + plant family groups) ---------- */
const FAMILY_ORDER = ["Poaceae", "Fabaceae", "Brassicaceae", "Solanaceae", "Asteraceae", "Amaranthaceae", "Cucurbitaceae", "Apiaceae", "Amaryllidaceae"];

export function cropIcon(c: CropInfo | undefined): IonName {
  const name = c?.icon ?? "leaf";
  return (name in Ionicons.glyphMap ? name : "leaf") as IonName;
}

export function groupCrops(crops: CropInfo[], query: string, lang?: string): { family: string; crops: CropInfo[] }[] {
  const q = query.trim().toLowerCase();
  const hit = crops.filter(
    (c) => !q || localName(c, lang).toLowerCase().includes(q) || c.name.toLowerCase().includes(q) || c.id.includes(q) || c.family.toLowerCase().includes(q),
  );
  const by = new Map<string, CropInfo[]>();
  for (const c of hit) by.set(c.family, [...(by.get(c.family) ?? []), c]);
  const fams = [...by.keys()].sort((a, b) => {
    const ia = FAMILY_ORDER.indexOf(a);
    const ib = FAMILY_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
  return fams.map((f) => ({ family: f, crops: (by.get(f) ?? []).sort((a, b) => localName(a, lang).localeCompare(localName(b, lang), lang)) }));
}

export function CropPicker({
  value,
  onChange,
  label,
  allowNone,
  filter,
  testID,
  compact,
}: {
  value: string | null;
  onChange: (id: string | null) => void;
  label: string;
  allowNone?: boolean;
  filter?: (c: CropInfo) => boolean;
  testID?: string;
  compact?: boolean;
}) {
  const t = useTheme();
  const { t: tr, i18n } = useTranslation();
  const all = useCrops();
  const crops = useMemo(() => (filter ? all.filter(filter) : all), [all, filter]);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const current = all.find((c) => c.id === value);
  const groups = useMemo(() => groupCrops(crops, q, i18n.language), [crops, q, i18n.language]);
  const choose = (id: string | null) => {
    onChange(id);
    setOpen(false);
    setQ("");
  };
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}: ${current?.name ?? tr("plan.years.none")}`}
        onPress={() => setOpen(true)}
        testID={testID}
        style={({ pressed }) => ({
          flexDirection: "row",
          alignItems: "center",
          gap: space.sm,
          minHeight: MIN_TOUCH,
          paddingHorizontal: compact ? space.sm : space.md,
          borderRadius: radius.md,
          backgroundColor: t.cardAlt,
          opacity: pressed ? 0.8 : 1,
        })}
      >
        <Ionicons name={value ? cropIcon(current) : "add"} size={18} color={t.primary} />
        <Txt v={compact ? "small" : "label"} style={{ flex: 1, fontWeight: "600" }} numberOfLines={1}>
          {value ? (current?.name ?? value.replace(/_/g, " ")) : tr("plan.years.none")}
        </Txt>
        {!compact ? <Ionicons name="chevron-down" size={16} color={t.textMuted} /> : null}
      </Pressable>
      <Sheet visible={open} onClose={() => setOpen(false)} title={label} testID={testID ? `${testID}-sheet` : undefined}>
        <TextInput
          value={q}
          onChangeText={setQ}
          placeholder={tr("crops.search")}
          placeholderTextColor={t.textMuted}
          accessibilityLabel={tr("crops.search")}
          autoFocus={false}
          style={[ui.input, { color: t.text, borderColor: t.border, backgroundColor: t.card, marginTop: space.sm }]}
          testID={testID ? `${testID}-search` : undefined}
        />
        {allowNone ? <ListRow icon="remove-circle-outline" title={tr("plan.years.none")} onPress={() => choose(null)} /> : null}
        {groups.map((g) => (
          <View key={g.family} style={{ marginTop: space.md }}>
            <Txt v="small" muted style={{ textTransform: "uppercase", letterSpacing: 0.6 }}>
              {tr(`crops.family.${g.family}`, { defaultValue: g.family })}
            </Txt>
            {g.crops.map((c) => (
              <ListRow
                key={c.id}
                icon={cropIcon(c)}
                title={localName(c, i18n.language)}
                subtitle={[
                  c.n_fixing ? tr("crops.fixesN") : null,
                  c.type === "perennial" ? tr("crops.perennial") : c.type === "cover" ? tr("crops.cover") : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
                onPress={() => choose(c.id)}
                right={c.id === value ? <Ionicons name="checkmark" size={20} color={t.primary} /> : <View />}
                testID={testID ? `${testID}-opt-${c.id}` : undefined}
              />
            ))}
          </View>
        ))}
        {groups.length === 0 ? (
          <Txt muted style={{ marginTop: space.lg }}>
            {tr("crops.noMatch")}
          </Txt>
        ) : null}
      </Sheet>
    </>
  );
}

/* ---------- back link for screens opened from a hub (Insights) ---------- */
export function BackLink({ label, onPress, testID }: { label: string; onPress: () => void; testID?: string }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      hitSlop={8}
      testID={testID}
      style={{ flexDirection: "row", alignItems: "center", gap: 4, minHeight: MIN_TOUCH, alignSelf: "flex-start" }}
    >
      <Ionicons name="chevron-back" size={18} color={t.primary} />
      <Txt v="small" color={t.primary} style={{ fontWeight: "600" }}>
        {label}
      </Txt>
    </Pressable>
  );
}
