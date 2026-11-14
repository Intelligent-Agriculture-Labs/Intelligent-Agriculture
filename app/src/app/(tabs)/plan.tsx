import React from "react";
import { Redirect, router, useLocalSearchParams } from "expo-router";
import { useTranslation } from "react-i18next";
import { PlanSeason } from "@/components/PlanSeason";
import { RotationPlanner } from "@/components/RotationPlanner";
import { Segmented, Tip } from "@/components/kit";
import { Screen, Txt } from "@/components/ui";
import { space } from "@/lib/theme";
import { useStore } from "@/state/store";

export default function PlanScreen() {
  const { t: tr } = useTranslation();
  const { field } = useStore();
  const params = useLocalSearchParams<{ tab?: string }>();
  const tab = params.tab === "years" ? "years" : "season";
  if (!field) return <Redirect href="/" />;
  return (
    <Screen testID="plan-screen">
      <Txt v="h1">{tr("plan.title")}</Txt>
      <Segmented
        style={{ marginTop: space.md }}
        value={tab}
        onChange={(v) => router.setParams({ tab: v })}
        options={[
          { value: "season", label: tr("plan.tabSeason"), testID: "plan-tab-season" },
          { value: "years", label: tr("plan.tabYears"), testID: "plan-tab-years" },
        ]}
      />
      {tab === "season" ? (
        <>
          <Tip id="plan-season" text={tr("tips.planSeason")} />
          <PlanSeason field={field} />
        </>
      ) : (
        <>
          <Tip id="plan-years" text={tr("tips.planYears")} />
          <RotationPlanner key={field.id} field={field} />
        </>
      )}
    </Screen>
  );
}
