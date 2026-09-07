import type { DemoCase, DemoCaseSummary, Health, WalkthroughRun } from "./types";

const ROOT = "/walkthrough";
const jsonCache = new Map<string, Promise<unknown>>();

async function loadJson<T>(path: string): Promise<T> {
  let pending = jsonCache.get(path);
  if (!pending) {
    pending = fetch(path, { cache: "force-cache" }).then(async (response) => {
      if (!response.ok) {
        throw new Error(
          "This recorded sample is not available yet. Regenerate the walkthrough snapshot locally.",
        );
      }
      return response.json();
    });
    jsonCache.set(path, pending);
  }
  return pending as Promise<T>;
}

const walkthroughHealth: Health = {
  status: "ready",
  decompositionConfigured: true,
  decompositionReady: true,
  retrievalConfigured: true,
  linguisticsConfigured: true,
  decompositionModel: "Qwen2.5 via Ollama (recorded)",
  retrievalModel: "BAAI/bge-small-en-v1.5 + lexical anchors (recorded)",
  linguisticsModel: "en_core_web_sm@3.8.0 (recorded)",
};

export const walkthroughApi = {
  health: async (): Promise<Health> => walkthroughHealth,
  cases: async () => {
    const [catalog, metadata] = await Promise.all([
      loadJson<DemoCaseSummary[]>(`${ROOT}/catalog.json`),
      loadJson<Record<string, Partial<DemoCaseSummary>>>(`${ROOT}/metadata.json`),
    ]);
    return catalog.map((item) => ({ ...item, ...(metadata[item.id] ?? {}) }));
  },
  case: (id: string) => loadJson<DemoCase>(`${ROOT}/cases/${encodeURIComponent(id)}.json`),
  run: (id: string) => loadJson<WalkthroughRun>(`${ROOT}/runs/${encodeURIComponent(id)}.json`),
};
