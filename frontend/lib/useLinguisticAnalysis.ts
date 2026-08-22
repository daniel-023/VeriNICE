"use client";

import { useCallback, useRef, useState } from "react";
import { api } from "./api";
import type {
  AtomLinguisticAnalysis,
  ClaimComposition,
  DecomposedAtom,
  LinguisticAnalysisResponse,
  ObligationLinguisticSummary,
  StageState,
} from "./types";

export type LinguisticAnalysisInput = {
  schemaVersion: 2;
  claimText: string;
  composition: ClaimComposition;
  atoms: DecomposedAtom[];
};

export function useLinguisticAnalysis() {
  const [analyses, setAnalyses] = useState<AtomLinguisticAnalysis[]>([]);
  const [summaries, setSummaries] = useState<ObligationLinguisticSummary[]>([]);
  const [claimWarnings, setClaimWarnings] = useState<LinguisticAnalysisResponse["claimWarnings"]>([]);
  const [state, setState] = useState<StageState>("idle");
  const [error, setError] = useState<string | null>(null);
  const generationRef = useRef(0);
  const lastInputRef = useRef<LinguisticAnalysisInput | null>(null);

  const clear = useCallback(() => {
    generationRef.current += 1;
    lastInputRef.current = null;
    setAnalyses([]);
    setSummaries([]);
    setClaimWarnings([]);
    setState("idle");
    setError(null);
  }, []);

  const run = useCallback(async (input: LinguisticAnalysisInput) => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    lastInputRef.current = {
      ...input,
      atoms: input.atoms.map((atom) => ({ ...atom })),
    };
    setAnalyses([]);
    setSummaries([]);
    setClaimWarnings([]);
    setState("running");
    setError(null);
    try {
      const result = await api.analyzeLinguistics(input);
      if (generationRef.current !== generation) return;
      setAnalyses(result.analyses);
      setSummaries(result.summaries ?? []);
      setClaimWarnings(result.claimWarnings ?? []);
      setState("complete");
    } catch (reason) {
      if (generationRef.current !== generation) return;
      setState("error");
      setError(
        reason instanceof Error
          ? reason.message
          : "Linguistic analysis failed. Check the API and retry.",
      );
    }
  }, []);

  const retry = useCallback(async () => {
    if (!lastInputRef.current) return;
    await run(lastInputRef.current);
  }, [run]);

  const loadRecorded = useCallback((recorded: LinguisticAnalysisResponse | AtomLinguisticAnalysis[]) => {
    generationRef.current += 1;
    lastInputRef.current = null;
    if (Array.isArray(recorded)) {
      setAnalyses(recorded);
      setSummaries([]);
      setClaimWarnings([]);
    } else {
      setAnalyses(recorded.analyses);
      setSummaries(recorded.summaries ?? []);
      setClaimWarnings(recorded.claimWarnings ?? []);
    }
    setState("complete");
    setError(null);
  }, []);

  return { analyses, summaries, claimWarnings, state, error, run, retry, clear, loadRecorded };
}
