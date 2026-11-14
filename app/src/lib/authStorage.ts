/**
 * Where the account session token lives: expo-secure-store (Keychain / Keystore) on iOS/Android,
 * localStorage on the web. The backend is injectable so the logic is unit-testable.
 */
import { Platform } from "react-native";

export interface KV {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  del(key: string): Promise<void>;
}

export const SESSION_KEY = "fieldshift.session.v1";

export interface Session {
  token: string;
  user: { id: string; email: string; name: string; created_at: string };
}

export function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const s = JSON.parse(raw) as Partial<Session>;
    if (typeof s.token !== "string" || !s.token || !s.user || typeof s.user.email !== "string") return null;
    return s as Session;
  } catch {
    return null;
  }
}

export function sessionStore(kv: KV) {
  return {
    load: async () => parseSession(await kv.get(SESSION_KEY)),
    save: (s: Session) => kv.set(SESSION_KEY, JSON.stringify(s)),
    clear: () => kv.del(SESSION_KEY),
  };
}

function webKV(): KV {
  const ls = () => (typeof window !== "undefined" ? window.localStorage : null);
  return {
    get: async (k) => ls()?.getItem(k) ?? null,
    set: async (k, v) => ls()?.setItem(k, v),
    del: async (k) => ls()?.removeItem(k),
  };
}

function nativeKV(): KV {
  // required lazily so the web bundle never touches the native module
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const SecureStore = require("expo-secure-store") as typeof import("expo-secure-store");
  return {
    get: (k) => SecureStore.getItemAsync(k),
    set: (k, v) => SecureStore.setItemAsync(k, v),
    del: (k) => SecureStore.deleteItemAsync(k),
  };
}

export const session = sessionStore(Platform.OS === "web" ? webKV() : nativeKV());

/** Client-side validation used by the sign-up / log-in forms (server validates again). */
export function validateCredentials(email: string, password: string, mode: "login" | "register"): "email" | "password" | null {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email.trim())) return "email";
  if (mode === "register" ? password.length < 8 : password.length < 1) return "password";
  return null;
}
