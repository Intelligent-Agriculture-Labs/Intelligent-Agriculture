import React from "react";
import { router } from "expo-router";
import { useTranslation } from "react-i18next";
import { Group, ListRow, Tip } from "@/components/kit";
import { Screen, Section, Txt } from "@/components/ui";
import { space } from "@/lib/theme";

/** Deeper analysis, one tap away: scenario simulator, climate trends, rotation alternatives, glossary. */
export default function Insights() {
  const { t: tr } = useTranslation();
  return (
    <Screen testID="insights">
      <Txt v="h1">{tr("insights.title")}</Txt>
      <Txt muted style={{ marginTop: space.xs }}>
        {tr("insights.subtitle")}
      </Txt>
      <Tip id="insights" text={tr("tips.insights")} />
      <Group>
        <ListRow
          icon="flask-outline"
          title={tr("insights.whatif")}
          subtitle={tr("insights.whatifSub")}
          onPress={() => router.push("/whatif")}
          testID="insights-whatif"
        />
        <ListRow
          icon="trending-up-outline"
          title={tr("insights.climate")}
          subtitle={tr("insights.climateSub")}
          onPress={() => router.push("/climate")}
          testID="insights-climate"
        />
        <ListRow
          icon="git-compare-outline"
          title={tr("insights.alternatives")}
          subtitle={tr("insights.alternativesSub")}
          onPress={() => router.push("/rotations")}
          testID="insights-rotations"
        />
      </Group>
      <Section title={tr("insights.learn")}>
        <Group>
          <ListRow
            icon="book-outline"
            title={tr("glossary.title")}
            subtitle={tr("glossary.subtitle")}
            onPress={() => router.push("/glossary")}
            testID="insights-glossary"
          />
          <ListRow
            icon="calendar-outline"
            title={tr("insights.planYears")}
            subtitle={tr("insights.planYearsSub")}
            onPress={() => router.push("/plan?tab=years")}
          />
        </Group>
      </Section>
    </Screen>
  );
}
