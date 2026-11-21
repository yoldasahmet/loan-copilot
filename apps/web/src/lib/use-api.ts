"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Load JSON from the API. `path = null` skips loading. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<Error | undefined>();
  const [loading, setLoading] = useState(path !== null);

  const reload = useCallback(async () => {
    if (path === null) return;
    try {
      setData(await api<T>(path));
      setError(undefined);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setLoading(path !== null);
    void reload();
  }, [reload, path]);

  return { data, error, loading, reload, setData };
}
