import AsyncStorage from "@react-native-async-storage/async-storage";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { AppState } from "react-native";
import i18n, { deviceLanguage } from "@/i18n";
import { api, ApiError, type Origin } from "@/api/client";
import type { AdviceResponse, Farm, FarmSettings, FieldInput, Lang } from "@/api/types";
import type { UnitSystem } from "@/lib/units";
import {
  type Field,
  type FieldDraft,
  hasChangesSince,
  mergeFields,
  migrateLegacyField,
  newId,
  normalizeSyncCode,
  nowIso,
  polygonAreaHa,
  toRecord,
} from "./farm";

export type { Field, FieldDraft } from "./farm";

export interface Settings {
  lang: Lang;
  units: UnitSystem;
  expert: boolean;
}

interface AdviceState {
  data: AdviceResponse | null;
  origin: Origin | null;
  savedAt: string | null;
  loading: boolean;
  error: string | null;
}

export type SyncStatus = "off" | "syncing" | "ok" | "offline" | "error";
export interface SyncState {
  enabled: boolean;
  status: SyncStatus;
  lastSync: string | null;
  error: string | null;
  syncCode: string | null;
}

interface FarmState {
  farm_id: string | null;
  sync_code: string | null;
  name: string;
  version: number;
  fields: Field[]; // includes tombstones
  active_field_id: string | null;
  last_sync: string | null;
  settings_dirty: boolean;
}

interface Store {
  ready: boolean;
  settings: Settings;
  setSettings: (s: Partial<Settings>) => void;
  /** active field (null if the farm has none) */
  field: Field | null;
  /** update the active field (adds one if there is none); null deletes the active field */
  setField: (f: FieldDraft | null) => void;
  /** all live fields (no tombstones) */
  fields: Field[];
  activeFieldId: string | null;
  setActiveField: (id: string) => void;
  addField: (f: FieldDraft) => string;
  updateField: (id: string, patch: Partial<FieldDraft>) => void;
  deleteField: (id: string) => void;
  farmName: string;
  setFarmName: (n: string) => void;
  sync: SyncState;
  enableSync: () => Promise<void>;
  joinFarm: (code: string) => Promise<void>;
  leaveSync: () => void;
  syncNow: () => Promise<void>;
  advice: AdviceState;
  refreshAdvice: () => Promise<void>;
}

const SETTINGS_KEY = "fieldshift:settings:v1";
const LEGACY_FIELD_KEY = "fieldshift:field:v1";
const FARM_KEY = "fieldshift:farm:v2";
const PUSH_DEBOUNCE_MS = 2000;
const PULL_INTERVAL_MS = 60000;
const Ctx = createContext<Store | null>(null);

export function toFieldInput(f: Field, lang: Lang): FieldInput {
  return {
    lat: f.lat,
    lon: f.lon,
    crop: f.crop,
    planting_date: f.planting_date,
    irrigation: f.irrigation,
    polygon: f.polygon && f.polygon.length >= 3 ? f.polygon : undefined,
    water_allocation_mm: f.water_allocation_mm ?? null,
    lang,
    as_of: f.as_of ?? null,
    last_irrigation_date: f.last_irrigation_date ?? null,
    last_irrigation_mm: f.last_irrigation_mm ?? null,
  };
}

const EMPTY_FARM: FarmState = {
  farm_id: null,
  sync_code: null,
  name: "My farm",
  version: 0,
  fields: [],
  active_field_id: null,
  last_sync: null,
  settings_dirty: false,
};

/** synced content of a field (everything except device-local view state and the timestamp) */
function contentKey(f: Field): string {
  const r: Partial<ReturnType<typeof toRecord>> = { ...toRecord(f) };
  delete r.updated_at;
  return JSON.stringify(r);
}

function fieldFromDraft(d: FieldDraft, id: string, prev?: Field): Field {
  const polygon = d.polygon && d.polygon.length >= 3 ? d.polygon : undefined;
  const f: Field = {
    ...prev,
    ...d,
    id,
    polygon,
    area_ha: polygon ? Math.round(polygonAreaHa(polygon) * 100) / 100 : (d.area_ha ?? prev?.area_ha ?? null),
    updated_at: prev?.updated_at ?? nowIso(),
    deleted: false,
  };
  // bump the timestamp only when synced content changed (switching replay mode is device-local)
  if (!prev || contentKey(prev) !== contentKey(f)) f.updated_at = nowIso();
  return f;
}

/** network failure / timeout, as opposed to an HTTP error status from the server */
const isOffline = (e: unknown) => !(e instanceof ApiError);
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

export function StoreProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [settings, setSettingsState] = useState<Settings>({ lang: deviceLanguage(), units: "metric", expert: false });
  const [farm, setFarm] = useState<FarmState>(EMPTY_FARM);
  const [syncStatus, setSyncStatus] = useState<{ status: SyncStatus; error: string | null }>({ status: "off", error: null });
  const [advice, setAdvice] = useState<AdviceState>({ data: null, origin: null, savedAt: null, loading: false, error: null });
  const resetAdvice = () => setAdvice({ data: null, origin: null, savedAt: null, loading: false, error: null });

  const farmRef = useRef(farm);
  const settingsRef = useRef(settings);

  // ---------- load + migrate the v1 single field
  useEffect(() => {
    (async () => {
      try {
        const [s, f, legacy] = await Promise.all([AsyncStorage.getItem(SETTINGS_KEY), AsyncStorage.getItem(FARM_KEY), AsyncStorage.getItem(LEGACY_FIELD_KEY)]);
        if (s) {
          const parsed = JSON.parse(s) as Settings;
          settingsRef.current = parsed;
          setSettingsState(parsed);
          i18n.changeLanguage(parsed.lang);
        }
        if (f) {
          const loaded = { ...EMPTY_FARM, ...(JSON.parse(f) as Partial<FarmState>) };
          farmRef.current = loaded;
          setFarm(loaded);
        } else if (legacy) {
          const migrated = migrateLegacyField(JSON.parse(legacy) as Record<string, unknown>);
          if (migrated) {
            const next = { ...EMPTY_FARM, fields: [migrated], active_field_id: migrated.id };
            farmRef.current = next;
            setFarm(next);
            await AsyncStorage.setItem(FARM_KEY, JSON.stringify(next));
          }
        }
      } catch {
        // corrupted storage — start fresh
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const persist = useCallback((next: FarmState) => {
    farmRef.current = next;
    setFarm(next);
    AsyncStorage.setItem(FARM_KEY, JSON.stringify(next)).catch(() => undefined);
  }, []);

  // ---------- sync engine
  const pushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const busy = useRef(false);
  const pushRef = useRef<() => Promise<void>>(async () => undefined);

  const adopt = useCallback(
    (remote: Farm, syncedAt: string | null) => {
      const cur = farmRef.current;
      const merged = mergeFields(cur.fields, remote.fields);
      const live = merged.filter((x) => !x.deleted);
      const active = live.some((x) => x.id === cur.active_field_id) ? cur.active_field_id : (live[0]?.id ?? null);
      // remote settings win unless the user changed settings on this device since the last successful sync
      if (!cur.settings_dirty && remote.settings) {
        const rs = remote.settings;
        const patch: Partial<Settings> = {};
        if (rs.lang && rs.lang !== settingsRef.current.lang) patch.lang = rs.lang;
        if (rs.units && rs.units !== settingsRef.current.units) patch.units = rs.units;
        if (typeof rs.expert === "boolean" && rs.expert !== settingsRef.current.expert) patch.expert = rs.expert;
        if (Object.keys(patch).length) {
          const ns = { ...settingsRef.current, ...patch };
          settingsRef.current = ns;
          setSettingsState(ns);
          if (patch.lang) i18n.changeLanguage(patch.lang);
          AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(ns)).catch(() => undefined);
        }
      }
      const next: FarmState = {
        ...cur,
        farm_id: remote.farm_id,
        sync_code: remote.sync_code,
        name: remote.name || cur.name,
        version: remote.version,
        fields: merged,
        active_field_id: active,
        last_sync: syncedAt ?? nowIso(),
        settings_dirty: false,
      };
      persist(next);
      if (active !== cur.active_field_id) resetAdvice();
      return next;
    },
    [persist],
  );

  const farmSettings = (): FarmSettings => ({ lang: settingsRef.current.lang, units: settingsRef.current.units, expert: settingsRef.current.expert });

  const schedulePush = useCallback(() => {
    if (!farmRef.current.farm_id) return;
    if (pushTimer.current) clearTimeout(pushTimer.current);
    pushTimer.current = setTimeout(() => {
      pushTimer.current = null;
      pushRef.current();
    }, PUSH_DEBOUNCE_MS);
  }, []);

  const push = useCallback(async () => {
    const cur = farmRef.current;
    if (!cur.farm_id || busy.current) return;
    busy.current = true;
    setSyncStatus({ status: "syncing", error: null });
    const startedAt = nowIso();
    try {
      const remote = await api.farms.put(cur.farm_id, {
        name: cur.name,
        fields: cur.fields.map(toRecord),
        settings: cur.settings_dirty ? farmSettings() : undefined,
      });
      const next = adopt(remote, startedAt);
      setSyncStatus({ status: "ok", error: null });
      if (hasChangesSince(next.fields, startedAt)) schedulePush(); // edits made while the request was in flight
    } catch (e) {
      setSyncStatus({ status: isOffline(e) ? "offline" : "error", error: errMsg(e) });
    } finally {
      busy.current = false;
    }
  }, [adopt, schedulePush]);
  useEffect(() => {
    pushRef.current = push;
  }, [push]);

  const pull = useCallback(async () => {
    const cur = farmRef.current;
    if (!cur.farm_id || busy.current) return;
    // local edits pending → push instead (the server merges and returns the whole farm)
    if (hasChangesSince(cur.fields, cur.last_sync) || cur.settings_dirty) return push();
    busy.current = true;
    setSyncStatus({ status: "syncing", error: null });
    try {
      adopt(await api.farms.get(cur.farm_id), null);
      setSyncStatus({ status: "ok", error: null });
    } catch (e) {
      setSyncStatus({ status: isOffline(e) ? "offline" : "error", error: errMsg(e) });
    } finally {
      busy.current = false;
    }
  }, [adopt, push]);

  // pull on start, every 60 s, and whenever the app returns to the foreground
  const syncEnabled = !!farm.farm_id;
  useEffect(() => {
    if (!ready || !syncEnabled) return;
    pull();
    const iv = setInterval(pull, PULL_INTERVAL_MS);
    const sub = AppState.addEventListener("change", (st) => {
      if (st === "active") pull();
    });
    return () => {
      clearInterval(iv);
      sub.remove();
    };
  }, [ready, syncEnabled, pull]);

  const enableSync = useCallback(async () => {
    setSyncStatus({ status: "syncing", error: null });
    try {
      const cur = farmRef.current;
      const remote = await api.farms.create({ name: cur.name, fields: cur.fields.map(toRecord), settings: farmSettings() });
      adopt(remote, nowIso());
      setSyncStatus({ status: "ok", error: null });
    } catch (e) {
      setSyncStatus({ status: isOffline(e) ? "offline" : "error", error: errMsg(e) });
      throw e;
    }
  }, [adopt]);

  const joinFarm = useCallback(
    async (code: string) => {
      setSyncStatus({ status: "syncing", error: null });
      try {
        const localFields = farmRef.current.fields;
        const remote = await api.farms.join(normalizeSyncCode(code));
        const next = adopt(remote, null);
        // this device had fields the farm doesn't know yet: push the union
        if (localFields.some((f) => !remote.fields.some((r) => r.id === f.id))) {
          persist({ ...next, last_sync: null });
          await push();
        } else setSyncStatus({ status: "ok", error: null });
      } catch (e) {
        setSyncStatus({ status: isOffline(e) ? "offline" : "error", error: errMsg(e) });
        throw e;
      }
    },
    [adopt, persist, push],
  );

  const leaveSync = useCallback(() => {
    persist({ ...farmRef.current, farm_id: null, sync_code: null, version: 0, last_sync: null });
    setSyncStatus({ status: "off", error: null });
  }, [persist]);

  const syncNow = useCallback(async () => {
    const cur = farmRef.current;
    if (hasChangesSince(cur.fields, cur.last_sync) || cur.settings_dirty) await push();
    else await pull();
  }, [pull, push]);

  // ---------- settings (synced via farm.settings)
  const setSettings = useCallback(
    (patch: Partial<Settings>) => {
      const next = { ...settingsRef.current, ...patch };
      settingsRef.current = next;
      setSettingsState(next);
      if (patch.lang) i18n.changeLanguage(patch.lang);
      AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(next)).catch(() => undefined);
      if (farmRef.current.farm_id) {
        persist({ ...farmRef.current, settings_dirty: true });
        schedulePush();
      }
    },
    [persist, schedulePush],
  );

  // ---------- fields
  const writeFields = useCallback(
    (fields: Field[], active: string | null) => {
      persist({ ...farmRef.current, fields, active_field_id: active });
      schedulePush();
    },
    [persist, schedulePush],
  );

  const addField = useCallback(
    (d: FieldDraft) => {
      const id = d.id && !farmRef.current.fields.some((x) => x.id === d.id) ? d.id : newId();
      const f = fieldFromDraft(d, id);
      writeFields([...farmRef.current.fields, f], id);
      resetAdvice();
      return id;
    },
    [writeFields],
  );

  const updateField = useCallback(
    (id: string, patch: Partial<FieldDraft>) => {
      const cur = farmRef.current;
      const prev = cur.fields.find((x) => x.id === id);
      if (!prev) return;
      const f = fieldFromDraft({ ...prev, ...patch } as FieldDraft, id, prev);
      writeFields(
        cur.fields.map((x) => (x.id === id ? f : x)),
        cur.active_field_id,
      );
    },
    [writeFields],
  );

  const deleteField = useCallback(
    (id: string) => {
      const cur = farmRef.current;
      const fields = cur.fields.map((x) => (x.id === id ? { ...x, deleted: true, updated_at: nowIso() } : x));
      const live = fields.filter((x) => !x.deleted);
      const active = cur.active_field_id === id ? (live[0]?.id ?? null) : cur.active_field_id;
      writeFields(fields, active);
      if (cur.active_field_id === id) resetAdvice();
    },
    [writeFields],
  );

  const setActiveField = useCallback(
    (id: string) => {
      if (farmRef.current.active_field_id === id) return;
      persist({ ...farmRef.current, active_field_id: id });
      resetAdvice();
    },
    [persist],
  );

  const setField = useCallback(
    (d: FieldDraft | null) => {
      const cur = farmRef.current;
      if (d === null) {
        if (cur.active_field_id) deleteField(cur.active_field_id);
        return;
      }
      const live = cur.fields.filter((x) => !x.deleted);
      const activeId = live.some((x) => x.id === cur.active_field_id) ? cur.active_field_id : (live[0]?.id ?? null);
      // demo farms (presetId) become their own field: re-use the field already created for that preset, else add one
      const presetTarget = !d.id && d.presetId ? live.find((x) => x.presetId === d.presetId) : undefined;
      if (!d.id && d.presetId && !presetTarget && live.length > 0) {
        addField(d);
        return;
      }
      const targetId = d.id && live.some((x) => x.id === d.id) ? d.id : (presetTarget?.id ?? activeId);
      if (!targetId) {
        addField(d);
        return;
      }
      const prev = cur.fields.find((x) => x.id === targetId);
      const f = fieldFromDraft(d, targetId, prev);
      writeFields(
        cur.fields.map((x) => (x.id === targetId ? f : x)),
        targetId,
      );
    },
    [addField, deleteField, writeFields],
  );

  const setFarmName = useCallback(
    (n: string) => {
      // the name travels with the next push; touching a field timestamp is not needed (PUT always sends the name)
      persist({ ...farmRef.current, name: n, settings_dirty: true });
      schedulePush();
    },
    [persist, schedulePush],
  );

  const fields = useMemo(() => farm.fields.filter((f) => !f.deleted), [farm.fields]);
  const field = useMemo(() => fields.find((f) => f.id === farm.active_field_id) ?? fields[0] ?? null, [fields, farm.active_field_id]);

  // ---------- advice for the active field (refetches when any input that affects it changes)
  const adviceInput = field ? toFieldInput(field, settings.lang) : null;
  const adviceKey = adviceInput ? JSON.stringify(adviceInput) : null;
  const refreshAdvice = useCallback(async () => {
    if (!adviceKey) return;
    const input = JSON.parse(adviceKey) as FieldInput;
    setAdvice((a) => ({ ...a, loading: true, error: null }));
    try {
      const r = await api.advice(input);
      setAdvice({ data: r.data, origin: r.origin, savedAt: r.savedAt, loading: false, error: null });
    } catch (e) {
      setAdvice((a) => ({ ...a, loading: false, error: errMsg(e) }));
    }
  }, [adviceKey]);

  useEffect(() => {
    if (ready && adviceKey) refreshAdvice();
  }, [ready, adviceKey, refreshAdvice]);

  const sync: SyncState = useMemo(
    () => ({
      enabled: syncEnabled,
      status: syncEnabled ? syncStatus.status : "off",
      lastSync: farm.last_sync,
      error: syncStatus.error,
      syncCode: farm.sync_code,
    }),
    [syncEnabled, syncStatus, farm.last_sync, farm.sync_code],
  );

  const value = useMemo(
    () => ({
      ready,
      settings,
      setSettings,
      field,
      setField,
      fields,
      activeFieldId: field?.id ?? null,
      setActiveField,
      addField,
      updateField,
      deleteField,
      farmName: farm.name,
      setFarmName,
      sync,
      enableSync,
      joinFarm,
      leaveSync,
      syncNow,
      advice,
      refreshAdvice,
    }),
    [
      ready,
      settings,
      setSettings,
      field,
      setField,
      fields,
      setActiveField,
      addField,
      updateField,
      deleteField,
      farm.name,
      setFarmName,
      sync,
      enableSync,
      joinFarm,
      leaveSync,
      syncNow,
      advice,
      refreshAdvice,
    ],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore outside StoreProvider");
  return s;
}
