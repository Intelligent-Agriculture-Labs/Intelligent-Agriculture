import React, { useEffect, useState } from "react";
import { Redirect } from "expo-router";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useStore } from "@/state/store";
import { Loading } from "@/components/ui";
import { WELCOMED_KEY } from "./welcome";

/** Entry: farm with fields → Today; first visit → welcome; returning without fields → add a field / demo. */
export default function Index() {
  const { ready, field } = useStore();
  const [welcomed, setWelcomed] = useState<boolean | null>(null);
  useEffect(() => {
    AsyncStorage.getItem(WELCOMED_KEY)
      .then((v) => setWelcomed(v === "1"))
      .catch(() => setWelcomed(true));
  }, []);
  if (!ready || welcomed === null) return <Loading />;
  if (field) return <Redirect href="/home" />;
  return <Redirect href={welcomed ? "/onboarding" : "/welcome"} />;
}
