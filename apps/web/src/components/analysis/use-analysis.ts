"use client";

import { useCallback, useEffect } from "react";
import { type AnalysisData, api } from "@/lib/api";
import { useApi } from "@/lib/use-api";

/** Analysis data for a case; polls every 2 s while a run is in progress. */
export function useAnalysis(caseId: string) {
  const state = useApi<AnalysisData>(`/cases/${caseId}/analysis`);
  const { data, reload, setData } = state;

  useEffect(() => {
    if (!data?.running) return;
    const timer = setInterval(() => void reload(), 2000);
    return () => clearInterval(timer);
  }, [data?.running, reload]);

  const run = useCallback(async () => {
    setData(
      await api<AnalysisData>(`/cases/${caseId}/analysis/run`, {
        method: "POST",
      }),
    );
  }, [caseId, setData]);

  return { ...state, run };
}
