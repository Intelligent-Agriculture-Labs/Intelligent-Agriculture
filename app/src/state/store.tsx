import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import i18n, { deviceLanguage } from "@/i18n";
import { api, type Origin } from "@/api/client";
import type { AdviceResponse, FieldInput, IrrigationMethod, Lang } from "@/api/types";
import type { UnitSystem } from "@/lib/units";

export interface Settings {
  lang: Lang;
  units: UnitSystem;
  expert: boolean;
}

export interface Field {
  lat: number;
  lon: number;
  crop: string;
  planting_date: string;
  irrigation: IrrigationMethod;
  polygon?: [number, number][];
  name: string;
  presetId?: string | null;
  current_rotation: string[];
  /** replay date for demo farms (null = today) */
  as_of?: string | null;
  replay_date?: string | null;
}

interface AdviceState {
  data: AdviceResponse | null;
  origin: Origin | null;
  savedAt: string | null;
  loading: boolean;
  error: string | null;
}

interface Store {
  ready: boolean;
  settings: Settings;
  setSettings: (s: Partial<Settings>) => void;
  field: Field | null;
  setField: (f: Field | null) => void;
  advice: AdviceState;
  refreshAdvice: () => Promise<void>;
}

const SETTINGS_KEY = "fieldshift:settings:v1";
const FIELD_KEY = "fieldshift:field:v1";
const Ctx = createContext<Store | null>(null);

export function toFieldInput(f: Field, lang: Lang): FieldInput {
  return {
    lat: f.lat,
    lon: f.lon,
    crop: f.crop,
    planting_date: f.planting_date,
    irrigation: f.irrigation,
    polygon: f.polygon && f.polygon.length >= 3 ? f.polygon : undefined,
    lang,
    as_of: f.as_of ?? null,
  };
}

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [settings, setSettingsState] = useState<Settings>({ lang: deviceLanguage(), units: "metric", expert: false });
  const [field, setFieldState] = useState<Field | null>(null);
  const [advice, setAdvice] = useState<AdviceState>({ data: null, origin: null, savedAt: null, loading: false, error: null });

  useEffect(() => {
    (async () => {
      try {
        const [s, f] = await Promise.all([AsyncStorage.getItem(SETTINGS_KEY), AsyncStorage.getItem(FIELD_KEY)]);
        if (s) {
          const parsed = JSON.parse(s) as Settings;
          setSettingsState(parsed);
          i18n.changeLanguage(parsed.lang);
        }
        if (f) setFieldState(JSON.parse(f) as Field);
      } catch {
        // corrupted storage — start fresh
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const setSettings = useCallback((patch: Partial<Settings>) => {
    setSettingsState((prev) => {
      const next = { ...prev, ...patch };
      if (patch.lang) i18n.changeLanguage(patch.lang);
      AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(next)).catch(() => undefined);
      return next;
    });
  }, []);

  const setField = useCallback((f: Field | null) => {
    setFieldState(f);
    setAdvice({ data: null, origin: null, savedAt: null, loading: false, error: null });
    if (f) AsyncStorage.setItem(FIELD_KEY, JSON.stringify(f)).catch(() => undefined);
    else AsyncStorage.removeItem(FIELD_KEY).catch(() => undefined);
  }, []);

  const refreshAdvice = useCallback(async () => {
    if (!field) return;
    setAdvice((a) => ({ ...a, loading: true, error: null }));
    try {
      const r = await api.advice(toFieldInput(field, settings.lang));
      setAdvice({ data: r.data, origin: r.origin, savedAt: r.savedAt, loading: false, error: null });
    } catch (e) {
      setAdvice((a) => ({ ...a, loading: false, error: e instanceof Error ? e.message : String(e) }));
    }
  }, [field, settings.lang]);

  useEffect(() => {
    if (ready && field) refreshAdvice();
  }, [ready, field, settings.lang, refreshAdvice]);

  const value = useMemo(
    () => ({ ready, settings, setSettings, field, setField, advice, refreshAdvice }),
    [ready, settings, setSettings, field, setField, advice, refreshAdvice],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside StoreProvider");
  return s;
}
