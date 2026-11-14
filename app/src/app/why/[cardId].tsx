import React from "react";
import { View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import { OriginBanner, RiskBadge, Screen, Txt } from "@/components/ui";
import { WhyView } from "@/components/WhyView";
import { space } from "@/lib/theme";
import { useStore } from "@/state/store";
import type { Risk } from "@/api/types";

const levelRisk = (l: number): Risk => (l <= 0 ? "low" : l <= 2 ? "moderate" : l <= 3 ? "high" : "severe");

export default function WhyScreen() {
  const { cardId } = useLocalSearchParams<{ cardId: string }>();
  const { t: tr } = useTranslation();
  const { advice, settings } = useStore();
  const a = advice.data;
  if (!a)
    return (
      <Screen>
        <Txt>{tr("why.notFound")}</Txt>
      </Screen>
    );
  const card = a.cards.find((c) => c.id === cardId);
  const isDrought = cardId === "__drought";
  if (!card && !isDrought)
    return (
      <Screen>
        <Txt>{tr("why.notFound")}</Txt>
      </Screen>
    );
  const title = card ? card.title : a.drought.label;
  const risk = card ? card.risk : levelRisk(a.drought.level);
  const why = card ? card.why : a.drought.why;
  return (
    <Screen testID="why">
      <OriginBanner origin={advice.origin} savedAt={advice.savedAt} />
      {a.mock && advice.origin !== "mock" ? <OriginBanner origin="mock" /> : null}
      <Txt v="h2" style={{ marginTop: space.sm }}>
        {title}
      </Txt>
      <View style={{ marginTop: space.sm }}>
        <RiskBadge risk={risk} />
      </View>
      {card ? (
        <Txt muted style={{ marginTop: space.sm }}>
          {card.detail}
        </Txt>
      ) : null}
      <WhyView why={why} series={a.series} sources={a.sources} expert={settings.expert} />
    </Screen>
  );
}
