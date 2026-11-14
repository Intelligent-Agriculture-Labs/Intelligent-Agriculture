/**
 * Scripted "capture tour" for screenshots and screen recordings of native builds.
 * Enabled ONLY in builds made with EXPO_PUBLIC_CAPTURE_TOUR=1 (see app/scripts/capture-native.sh);
 * normal builds never run it. Needed because XCUITest (and therefore Maestro) does not work with the
 * Xcode 27 beta toolchain on this machine; the tour is timing-based and prints markers to the device log.
 */
import { useEffect } from "react";
import { router } from "expo-router";
import { api } from "@/api/client";
import { useStore } from "@/state/store";

export const CAPTURE_TOUR = process.env.EXPO_PUBLIC_CAPTURE_TOUR === "1";
const PRESET = process.env.EXPO_PUBLIC_CAPTURE_PRESET ?? "fallon_nv";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function CaptureTour() {
  const { ready, setField } = useStore();
  useEffect(() => {
    if (!CAPTURE_TOUR || !ready) return;
    let cancelled = false;
    const step = async (name: string, go: () => void, waitMs: number) => {
      if (cancelled) return;
      go();
      console.log(`[capture] ${name}`);
      await sleep(waitMs);
    };
    (async () => {
      await step("onboarding", () => router.replace("/onboarding"), 5000);
      const presets = (await api.presets()).data;
      const p = presets.find((x) => x.id === PRESET) ?? presets[0];
      const base = {
        lat: p.lat,
        lon: p.lon,
        crop: p.crop,
        planting_date: p.planting_date,
        irrigation: p.irrigation,
        name: p.name,
        presetId: p.id,
        current_rotation: p.current_rotation,
        replay_date: p.replay_date ?? null,
      };
      await step("home-today", () => {
        setField({ ...base, as_of: null });
        router.replace("/home");
      }, 12000);
      await step("home-replay", () => setField({ ...base, as_of: p.replay_date ?? null }), 14000);
      await step("why", () => router.push({ pathname: "/why/[cardId]", params: { cardId: "irrigate" } }), 9000);
      await step("rotations", () => router.replace("/rotations"), 30000);
      await step("whatif", () => router.replace("/whatif"), 20000);
      await step("climate", () => router.replace("/climate"), 12000);
      await step("done", () => router.replace("/home"), 1000);
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, setField]);
  return null;
}
