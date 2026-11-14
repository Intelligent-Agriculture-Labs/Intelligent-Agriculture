import { useCallback, useEffect, useRef, useState } from "react";
import type { Origin, Result } from "@/api/client";

interface QueryState<T> {
  doneKey: string | null;
  data: T | null;
  origin: Origin | null;
  savedAt: string | null;
  error: string | null;
}

/**
 * Minimal data-fetching hook: refetches whenever `key` changes (or `refetch()` is called),
 * keeps the previous data while loading, and exposes the data origin (live / cache / mock).
 * Pass key = null to skip fetching.
 */
export function useQuery<T>(key: string | null, fetcher: () => Promise<Result<T>>) {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<QueryState<T>>({ doneKey: null, data: null, origin: null, savedAt: null, error: null });
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });
  const fullKey = key === null ? null : `${key}#${nonce}`;

  useEffect(() => {
    if (fullKey === null) return;
    let alive = true;
    fetcherRef
      .current()
      .then((r) => {
        if (alive) setState({ doneKey: fullKey, data: r.data, origin: r.origin, savedAt: r.savedAt, error: null });
      })
      .catch((e: unknown) => {
        if (alive) setState((s) => ({ ...s, doneKey: fullKey, error: e instanceof Error ? e.message : String(e) }));
      });
    return () => {
      alive = false;
    };
  }, [fullKey]);

  const refetch = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, loading: fullKey !== null && state.doneKey !== fullKey, refetch };
}
