/** Capture-build flags and hooks (dependency-free so UI primitives can import it). */
import type { ComponentRef } from "react";
import type { View } from "react-native";

export const CAPTURE_MODE = process.env.EXPO_PUBLIC_CAPTURE_TOUR;
export const CAPTURE_TOUR = CAPTURE_MODE === "1" || CAPTURE_MODE === "film";

/** The mounted <Screen> registers its scroll function and screens register named targets
 *  (e.g. the impact card), so the film tour can scroll a target into view. */
export const captureHooks: {
  scrollBy: ((dy: number) => void) | null;
  targets: Record<string, ComponentRef<typeof View> | null>;
} = { scrollBy: null, targets: {} };
