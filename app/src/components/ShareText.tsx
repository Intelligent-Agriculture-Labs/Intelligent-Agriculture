/**
 * "Share as text": this week's advice as a short plain-text message for SMS / WhatsApp —
 * for farmers who pass advice on to workers or family without the app.
 */
import React, { useState } from "react";
import { Platform, Pressable, Share, View } from "react-native";
import Ionicons from "@expo/vector-icons/Ionicons";
import { useTranslation } from "react-i18next";
import { api } from "@/api/client";
import type { AdviceText } from "@/api/types";
import { Sheet } from "@/components/kit";
import { Button, ErrorView, Loading, Txt } from "@/components/ui";
import { radius, space, useTheme } from "@/lib/theme";
import { useQuery } from "@/lib/useQuery";
import { toFieldInput, useStore } from "@/state/store";

/** Copy text on the web (clipboard API, with a textarea fallback for older browsers). */
async function copyWeb(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

function ShareSheetBody({ onClose }: { onClose: () => void }) {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const { field, settings } = useStore();
  const input = field ? toFieldInput(field, settings.lang) : null;
  const q = useQuery<AdviceText>(input ? `advice-text:${JSON.stringify(input)}:${field?.name}` : null, () =>
    api.adviceText(input!, field!.name).then((data) => ({ data, origin: "live" as const, savedAt: null })),
  );
  const [copied, setCopied] = useState(false);
  const webShare = Platform.OS === "web" && typeof navigator !== "undefined" && typeof navigator.share === "function";

  if (q.loading && !q.data) return <Loading label={tr("shareText.loading")} />;
  if (!q.data) return <ErrorView message={q.error ?? tr("account.errOffline")} onRetry={q.refetch} />;
  const text = q.data.text;
  return (
    <View testID="share-text-sheet">
      <View style={{ backgroundColor: t.cardAlt, borderRadius: radius.md, padding: space.md }}>
        <Txt testID="share-text-preview" style={{ fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }), fontSize: 14 }}>
          {text}
        </Txt>
      </View>
      <Txt v="small" muted style={{ marginTop: space.sm }} testID="share-text-sms">
        {tr("shareText.fits", { count: q.data.sms_parts, chars: q.data.chars })}
      </Txt>
      {Platform.OS === "web" ? (
        <Button
          icon={copied ? "checkmark" : "copy-outline"}
          label={copied ? tr("shareText.copied") : tr("shareText.copy")}
          onPress={async () => setCopied(await copyWeb(text))}
          style={{ marginTop: space.lg }}
          testID="share-text-copy"
        />
      ) : null}
      {Platform.OS !== "web" || webShare ? (
        <Button
          icon="share-outline"
          kind={Platform.OS === "web" ? "secondary" : "primary"}
          label={tr("shareText.share")}
          onPress={async () => {
            try {
              if (Platform.OS === "web") await navigator.share({ text });
              else await Share.share({ message: text });
              onClose();
            } catch {
              /* the farmer cancelled the share sheet */
            }
          }}
          style={{ marginTop: space.sm }}
          testID="share-text-share"
        />
      ) : null}
    </View>
  );
}

/** Small row button for Today + the preview sheet. */
export function ShareTextButton() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Pressable
        accessibilityRole="button"
        onPress={() => setOpen(true)}
        testID="share-text"
        style={{ flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44, marginTop: space.md }}
      >
        <Ionicons name="chatbubble-ellipses-outline" size={20} color={t.link} />
        <Txt color={t.link} style={{ flex: 1 }}>
          {tr("shareText.button")}
        </Txt>
      </Pressable>
      <Sheet visible={open} onClose={() => setOpen(false)} title={tr("shareText.title")}>
        {open ? <ShareSheetBody onClose={() => setOpen(false)} /> : null}
      </Sheet>
    </>
  );
}
