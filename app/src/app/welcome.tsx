import React, { useState } from "react";
import { Image, Pressable, View } from "react-native";
import { router } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";
import Ionicons from "@expo/vector-icons/Ionicons";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Button, Txt } from "@/components/ui";
import { MIN_TOUCH, radius, space, useTheme } from "@/lib/theme";

export const WELCOMED_KEY = "fieldshift:welcomed:v1";
const APP_ICON = require("../../assets/icon.png");
type IonName = React.ComponentProps<typeof Ionicons>["name"];
const STEPS: { icon: IonName; points: IonName[] }[] = [
  { icon: "planet-outline", points: ["sunny-outline", "map-outline", "calendar-outline"] },
  { icon: "scan-outline", points: ["hand-left-outline", "sparkles-outline", "create-outline"] },
  { icon: "leaf-outline", points: ["help-circle-outline", "phone-portrait-outline", "cloud-offline-outline"] },
];

/** First-run: what IA (Intelligent Agriculture) does, how to add a field, what you get — then add a field or try a demo farm. */
export default function Welcome() {
  const t = useTheme();
  const { t: tr } = useTranslation();
  const [step, setStep] = useState(0);
  const last = step === STEPS.length - 1;
  const done = (to: string) => {
    AsyncStorage.setItem(WELCOMED_KEY, "1").catch(() => undefined);
    router.replace(to as never);
  };
  const s = STEPS[step];
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }} testID="welcome">
      <View style={{ flex: 1, width: "100%", maxWidth: 560, alignSelf: "center", paddingHorizontal: space.xl, paddingTop: space.lg }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", minHeight: MIN_TOUCH }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm, flexShrink: 1 }}>
            <Image source={APP_ICON} style={{ width: 24, height: 24, borderRadius: 6 }} accessibilityIgnoresInvertColors />
            <Txt v="small" color={t.primary} style={{ fontWeight: "700", letterSpacing: 1, flexShrink: 1 }} numberOfLines={1}>
              {`${tr("app.name")} · ${tr("app.fullName")}`.toUpperCase()}
            </Txt>
          </View>
          {!last ? (
            <Pressable accessibilityRole="button" onPress={() => done("/onboarding")} hitSlop={10} testID="welcome-skip">
              <Txt v="small" muted>
                {tr("welcome.skip")}
              </Txt>
            </Pressable>
          ) : null}
        </View>

        <View style={{ flex: 1, justifyContent: "center" }}>
          {step === 0 ? (
            <>
              <Image source={APP_ICON} style={{ width: 88, height: 88, borderRadius: 22 }} accessibilityIgnoresInvertColors testID="welcome-logo" />
              <Txt v="small" color={t.primary} style={{ fontWeight: "700", marginTop: space.md }} testID="welcome-slogan">
                {tr("app.slogan")}
              </Txt>
            </>
          ) : (
            <View style={{ width: 88, height: 88, borderRadius: 44, backgroundColor: t.cardAlt, alignItems: "center", justifyContent: "center" }}>
              <Ionicons name={s.icon} size={44} color={t.primary} />
            </View>
          )}
          <Txt v="h1" style={{ marginTop: space.xl }} testID={`welcome-title-${step}`}>
            {tr(`welcome.s${step + 1}.title`)}
          </Txt>
          <Txt muted style={{ marginTop: space.sm }}>
            {tr(`welcome.s${step + 1}.text`)}
          </Txt>
          <View style={{ marginTop: space.xl, gap: space.lg }}>
            {s.points.map((ic, i) => (
              <View key={i} style={{ flexDirection: "row", gap: space.md, alignItems: "flex-start" }}>
                <View style={{ width: 36, height: 36, borderRadius: radius.md, backgroundColor: t.card, alignItems: "center", justifyContent: "center" }}>
                  <Ionicons name={ic} size={19} color={t.primary} />
                </View>
                <Txt style={{ flex: 1, marginTop: 6 }}>{tr(`welcome.s${step + 1}.p${i + 1}`)}</Txt>
              </View>
            ))}
          </View>
        </View>

        <View
          style={{ flexDirection: "row", justifyContent: "center", gap: 8, marginBottom: space.lg }}
          accessibilityLabel={tr("welcome.stepOf", { n: step + 1, total: STEPS.length })}
        >
          {STEPS.map((_, i) => (
            <View key={i} style={{ width: i === step ? 22 : 8, height: 8, borderRadius: 4, backgroundColor: i === step ? t.primary : t.border }} />
          ))}
        </View>
        <View style={{ gap: space.sm, marginBottom: space.xl }}>
          {last ? (
            <>
              <Button label={tr("welcome.addField")} icon="scan" onPress={() => done("/field-editor?mode=new&first=1")} testID="welcome-add" />
              <Button label={tr("welcome.demo")} kind="secondary" onPress={() => done("/onboarding")} testID="welcome-demo" />
              <Button label={tr("welcome.haveAccount")} kind="ghost" onPress={() => done("/account")} testID="welcome-login" />
            </>
          ) : (
            <>
              <Button label={tr("welcome.next")} onPress={() => setStep(step + 1)} testID="welcome-next" />
              {step > 0 ? <Button label={tr("common.back")} kind="ghost" onPress={() => setStep(step - 1)} /> : null}
            </>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}
