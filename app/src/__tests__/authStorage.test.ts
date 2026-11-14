import { parseSession, SESSION_KEY, sessionStore, validateCredentials, type KV, type Session } from "@/lib/authStorage";

jest.mock("expo-secure-store", () => ({ getItemAsync: jest.fn(), setItemAsync: jest.fn(), deleteItemAsync: jest.fn() }));

const memKV = (): KV & { data: Map<string, string> } => {
  const data = new Map<string, string>();
  return {
    data,
    get: async (k) => data.get(k) ?? null,
    set: async (k, v) => void data.set(k, v),
    del: async (k) => void data.delete(k),
  };
};

const sample: Session = { token: "tok_123", user: { id: "u1", email: "ana@example.org", name: "Ana", created_at: "2026-01-02T03:04:05Z" } };

describe("sessionStore", () => {
  it("saves, loads and clears the session under one key", async () => {
    const kv = memKV();
    const s = sessionStore(kv);
    expect(await s.load()).toBeNull();
    await s.save(sample);
    expect([...kv.data.keys()]).toEqual([SESSION_KEY]);
    expect(await s.load()).toEqual(sample);
    await s.clear();
    expect(await s.load()).toBeNull();
    expect(kv.data.size).toBe(0);
  });
});

describe("parseSession", () => {
  it("rejects missing, broken or incomplete data", () => {
    expect(parseSession(null)).toBeNull();
    expect(parseSession("")).toBeNull();
    expect(parseSession("{not json")).toBeNull();
    expect(parseSession(JSON.stringify({ token: "", user: sample.user }))).toBeNull();
    expect(parseSession(JSON.stringify({ token: "x" }))).toBeNull();
    expect(parseSession(JSON.stringify({ token: "x", user: { id: "u" } }))).toBeNull();
  });
  it("accepts a well-formed session", () => {
    expect(parseSession(JSON.stringify(sample))).toEqual(sample);
  });
});

describe("validateCredentials", () => {
  it("checks the e-mail format", () => {
    expect(validateCredentials("ana", "secret123", "login")).toBe("email");
    expect(validateCredentials("ana@x", "secret123", "login")).toBe("email");
    expect(validateCredentials(" ana@example.org ", "secret123", "login")).toBeNull();
  });
  it("needs any password to log in and 8+ characters to register", () => {
    expect(validateCredentials("ana@example.org", "", "login")).toBe("password");
    expect(validateCredentials("ana@example.org", "short", "login")).toBeNull();
    expect(validateCredentials("ana@example.org", "short", "register")).toBe("password");
    expect(validateCredentials("ana@example.org", "longenough", "register")).toBeNull();
  });
});
