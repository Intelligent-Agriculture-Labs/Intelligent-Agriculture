import React, { useState } from "react";
import { Modal, Pressable, ScrollView, View } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { cropName, useCrops } from "@/components/domain";
import { Button, Txt } from "@/components/ui";
import { MIN_TOUCH, space, useTheme } from "@/lib/theme";
import { fmt } from "@/lib/units";
import { type SyncState, useStore } from "@/state/store";

type IonName = React.ComponentProps<typeof Ionicons>["name"];

export function syncIcon(s: SyncState): { name: IonName; colorKey: "primary" | "textMuted" | "risk" } {
  if (!s.enabled) return { name: "cloud-offline-outline", colorKey: "textMuted" };
  if (s.status === "ok") return { name: "cloud-done-outline", colorKey: "primary" };
  if (s.status === "syncing") return { name: "sync-outline", colorKey: "primary" };
  if (s.status === "offline") return { name: "cloud-offline-outline", colorKey: "textMuted" };
  return { name: "alert-circle-outline", colorKey: "risk" };
}

export function useSyncLabel() {
  const { t: tr, i18n } = useTranslation();
  const { sync } = useStore();
  if (!sync.enabled) return tr("sync.statusOff");
  if (sync.status === "syncing") return tr("sync.statusSyncing");
  if (sync.status === "offline") return tr("sync.statusOffline");
  if (sync.status === "error") return tr("sync.statusError");
  const time = sync.lastSync ? new Date(sync.lastSync).toLocaleTimeString(i18n.language, { hour: "2-digit", minute: "2-digit" }) : "";
  return tr("sync.statusOk", { time });
}

/** Compact active-field selector shown at the top of the main tabs; opens a sheet to switch/add/edit/delete fields. */
export function FieldSwitcher() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { field, fields, setActiveField, deleteField, sync, settings } = useStore();
  const crops = useCrops();
  const [open, setOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const syncLabel = useSyncLabel();
  if (!field) return null;
  const ic = syncIcon(sync);
  const icColor = ic.colorKey === "risk" ? t.risk.severe.dot : ic.colorKey === "primary" ? t.primary : t.textMuted;

  const go = (path: string) => {
    setOpen(false);
    router.push(path as never);
  };

  return (
    <>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm, marginBottom: space.sm }}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={tr("fields.switchA11y", { name: field.name, count: fields.length })}
          onPress={() => setOpen(true)}
          testID="field-switcher"
          style={({ pressed }) => ({
            flex: 1,
            flexDirection: "row",
            alignItems: "center",
            gap: space.sm,
            minHeight: MIN_TOUCH,
            paddingHorizontal: space.md,
            borderRadius: 22,
            borderWidth: 1,
            borderColor: t.border,
            backgroundColor: t.card,
            opacity: pressed ? 0.85 : 1,
          })}
        >
          <Ionicons name={field.polygon ? "shapes" : "location"} size={18} color={t.primary} />
          <View style={{ flex: 1 }}>
            <Txt v="label" numberOfLines={1}>
              {field.name}
            </Txt>
            <Txt v="small" muted numberOfLines={1}>
              {cropName(crops, field.crop)}
              {field.area_ha ? ` · ${fmt(field.area_ha, "ha", settings.units, 1)}` : ""}
              {fields.length > 1 ? ` · ${tr("fields.count", { count: fields.length })}` : ""}
            </Txt>
          </View>
          <Ionicons name="chevron-down" size={18} color={t.textMuted} />
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`${tr("sync.title")}: ${syncLabel}`}
          onPress={() => router.push("/settings")}
          style={{ minWidth: MIN_TOUCH, minHeight: MIN_TOUCH, alignItems: "center", justifyContent: "center" }}
          testID="sync-indicator"
        >
          <Ionicons name={ic.name} size={22} color={icColor} />
        </Pressable>
      </View>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={tr("common.close")}
          onPress={() => setOpen(false)}
          style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end", alignItems: "center" }}
        >
          <Pressable
            onPress={() => undefined}
            style={{
              width: "100%",
              maxWidth: 640,
              maxHeight: "85%",
              backgroundColor: t.bg,
              borderTopLeftRadius: 20,
              borderTopRightRadius: 20,
              padding: space.lg,
            }}
            testID="fields-sheet"
          >
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <Txt v="h2">{tr("fields.title")}</Txt>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={tr("common.close")}
                onPress={() => setOpen(false)}
                style={{ minWidth: MIN_TOUCH, minHeight: MIN_TOUCH, alignItems: "center", justifyContent: "center" }}
              >
                <Ionicons name="close" size={24} color={t.text} />
              </Pressable>
            </View>
            <Txt v="small" muted>
              {syncLabel}
            </Txt>
            <ScrollView style={{ marginTop: space.md }} contentContainerStyle={{ gap: space.sm }}>
              {fields.map((f) => {
                const active = f.id === field.id;
                return (
                  <View
                    key={f.id}
                    style={{
                      borderRadius: 14,
                      borderWidth: active ? 2 : 1,
                      borderColor: active ? t.primary : t.border,
                      backgroundColor: active ? t.cardAlt : t.card,
                      padding: space.sm,
                    }}
                  >
                    <Pressable
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                      accessibilityLabel={tr("fields.select", { name: f.name })}
                      onPress={() => {
                        setActiveField(f.id);
                        setOpen(false);
                      }}
                      style={{ flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: MIN_TOUCH }}
                      testID={`field-item-${f.id}`}
                    >
                      <Ionicons name={active ? "checkmark-circle" : f.polygon ? "shapes-outline" : "location-outline"} size={22} color={t.primary} />
                      <View style={{ flex: 1 }}>
                        <Txt v="label">{f.name}</Txt>
                        <Txt v="small" muted>
                          {cropName(crops, f.crop)} · {f.area_ha ? fmt(f.area_ha, "ha", settings.units, 1) : tr("fields.noOutline")}
                        </Txt>
                      </View>
                    </Pressable>
                    <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap", marginTop: 4 }}>
                      <Button kind="ghost" icon="create-outline" label={tr("fields.edit")} onPress={() => go(`/field-editor?id=${f.id}`)} />
                      {confirmDelete === f.id ? (
                        <Button
                          kind="secondary"
                          icon="trash"
                          label={tr("fields.confirmDelete")}
                          onPress={() => {
                            deleteField(f.id);
                            setConfirmDelete(null);
                            if (fields.length <= 1) {
                              setOpen(false);
                              router.replace("/onboarding");
                            }
                          }}
                          testID={`field-delete-confirm-${f.id}`}
                        />
                      ) : (
                        <Button kind="ghost" icon="trash-outline" label={tr("fields.delete")} onPress={() => setConfirmDelete(f.id)} />
                      )}
                    </View>
                  </View>
                );
              })}
            </ScrollView>
            <Button icon="add" label={tr("fields.add")} onPress={() => go("/field-editor?mode=new")} style={{ marginTop: space.md }} testID="field-add" />
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}
