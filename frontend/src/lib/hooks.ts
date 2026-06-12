"use client";

import { useState, useEffect, useRef, useCallback } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  options: {
    interval: number;
    enabled: boolean;
    onSuccess?: (data: T) => void;
  },
): { data: T | null; loading: boolean; error: Error | null } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const fetcherRef = useRef(fetcher);
  const onSuccessRef = useRef(options.onSuccess);

  fetcherRef.current = fetcher;
  onSuccessRef.current = options.onSuccess;

  const poll = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetcherRef.current();
      setData(result);
      setError(null);
      onSuccessRef.current?.(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!options.enabled) return;
    poll();
    const id = setInterval(poll, options.interval);
    return () => clearInterval(id);
  }, [options.enabled, options.interval, poll]);

  return { data, loading, error };
}
