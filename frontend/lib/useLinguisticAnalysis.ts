"use client";

import { useCallback, useRef, useState } from "react";
import { api } from "./api";
import type { AtomLinguisticAnalysis, StageState } from "./types";

type AtomInput = Array<{ id: string; text: string }>;

export function useLinguisticAnalysis() {
  const [analyses, setAnalyses] = useState<AtomLinguisticAnalysis[]>([]);
  const [state, setState] = useState<StageState>("idle");
  const [error, setError] = useState<string | null>(null);
  const generationRef = useRef(0);
  const lastAtomsRef = useRef<AtomInput>([]);

  const clear = useCallback(() => {
    generationRef.current += 1;
    lastAtomsRef.current = [];
    setAnalyses([]);
    setState("idle");
    setError(null);
  }, []);

  const run = useCallback(async (atoms: AtomInput) => {
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    lastAtomsRef.current = atoms.map((atom) => ({ ...atom }));
    setAnalyses([]);
    setState("running");
    setError(null);
    try {
      const result = await api.analyzeLinguistics(atoms);
      if (generationRef.current !== generation) return;
      setAnalyses(result.analyses);
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
    if (!lastAtomsRef.current.length) return;
    await run(lastAtomsRef.current);
  }, [run]);

  const loadRecorded = useCallback((recorded: AtomLinguisticAnalysis[]) => {
    generationRef.current += 1;
    lastAtomsRef.current = [];
    setAnalyses(recorded);
    setState("complete");
    setError(null);
  }, []);

  return { analyses, state, error, run, retry, clear, loadRecorded };
}
