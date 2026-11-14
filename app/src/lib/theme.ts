import { useColorScheme } from "react-native";
import type { Risk } from "@/api/types";

/** Colour tokens. All text/background pairs are WCAG AA (>= 4.5:1) in both schemes. */
const light = {
  bg: "#f6f8f3",
  card: "#ffffff",
  cardAlt: "#eef3e8",
  text: "#17241a",
  textMuted: "#4a5a4d",
  border: "#d5dfcf",
  primary: "#2f6b3a",
  primaryText: "#ffffff",
  accent: "#b5651d",
  link: "#1d5e8c",
  bare: "#c9a66b",
  chart: ["#2f6b3a", "#1d5e8c", "#b5651d", "#7b4fa0", "#a8323e"],
  risk: {
    low: { bg: "#e3f2e1", fg: "#1e5a24", dot: "#2e8b3a" },
    moderate: { bg: "#fff4d6", fg: "#6b4b00", dot: "#d4a000" },
    high: { bg: "#ffe3cf", fg: "#7a3300", dot: "#e06a12" },
    severe: { bg: "#fbdada", fg: "#7d1414", dot: "#c62828" },
  } as Record<Risk, { bg: string; fg: string; dot: string }>,
  banner: { mock: "#7d1414", offline: "#6b4b00", info: "#1d5e8c" },
};

const dark: typeof light = {
  bg: "#0f1611",
  card: "#18221b",
  cardAlt: "#1f2c23",
  text: "#e9f1e6",
  textMuted: "#a9b8ab",
  border: "#2d3b31",
  primary: "#7fc48a",
  primaryText: "#0f1611",
  accent: "#e3a15e",
  link: "#8cc4ef",
  bare: "#8a7148",
  chart: ["#7fc48a", "#8cc4ef", "#e3a15e", "#c39be6", "#f08a94"],
  risk: {
    low: { bg: "#1d3a20", fg: "#bfe8c2", dot: "#5cc46a" },
    moderate: { bg: "#3a3014", fg: "#f6dd94", dot: "#e8bd2c" },
    high: { bg: "#40240f", fg: "#ffc79e", dot: "#f08a3a" },
    severe: { bg: "#431818", fg: "#ffb3b3", dot: "#ef5350" },
  },
  banner: { mock: "#b3261e", offline: "#8a6400", info: "#245f8c" },
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? dark : light;
}

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 };
export const radius = { sm: 8, md: 12, lg: 18 };
export const MIN_TOUCH = 44;
