import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { getLocales } from "expo-localization";
import en from "./locales/en.json";
import es from "./locales/es.json";
import fr from "./locales/fr.json";
import sw from "./locales/sw.json";
import hi from "./locales/hi.json";
import de from "./locales/de.json";
import type { Lang } from "@/api/types";

/** To add a language: drop a JSON file in ./locales, register it here and in LANGUAGES. */
export const resources = { en, es, fr, sw, hi, de } as const;
export const LANGUAGES: { code: Lang; label: string }[] = [
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "sw", label: "Kiswahili" },
  { code: "hi", label: "हिन्दी" },
  { code: "de", label: "Deutsch" },
];

export function deviceLanguage(): Lang {
  const tag = getLocales()[0]?.languageCode ?? "en";
  return (Object.keys(resources) as Lang[]).includes(tag as Lang) ? (tag as Lang) : "en";
}

if (!i18n.isInitialized) {
  // eslint-disable-next-line import/no-named-as-default-member
  i18n.use(initReactI18next).init({
    resources: Object.fromEntries(Object.entries(resources).map(([k, v]) => [k, { translation: v }])),
    lng: deviceLanguage(),
    fallbackLng: "en",
    interpolation: { escapeValue: false },
    returnNull: false,
  });
}

export default i18n;
