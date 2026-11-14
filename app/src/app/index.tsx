import React from "react";
import { Redirect } from "expo-router";
import { useStore } from "@/state/store";
import { Loading } from "@/components/ui";

export default function Index() {
  const { ready, field } = useStore();
  if (!ready) return <Loading />;
  return <Redirect href={field ? "/home" : "/onboarding"} />;
}
