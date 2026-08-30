"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity, LoaderCircle, Play, Sparkles } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import { deploymentMode, type DeploymentMode } from "@/lib/deployment";
import { DEFAULT_EVIDENCE_PER_ATOM } from "@/lib/retrieval";
import { useLinguisticAnalysis } from "@/lib/useLinguisticAnalysis";
import { walkthroughApi } from "@/lib/walkthrough";
import type {
  AtomEvidence,
  AtomSupportClassification,
  ClaimComposition,
  EvidenceNode,
  EvidenceSpan,
  DecomposedAtom,
  DemoCase,
  DemoCaseSummary,
  DemoChallenge,
  DemoDocument,
  DemoTopic,
  GroundedEvidenceAuditResult,
  Health,
  MobilePanel,
  NLIRelation,
  ReferenceLabel,
  StageState,
  VerdictAggregationResult,
} from "@/lib/types";
import { AtomRail } from "./AtomRail";
import { ArgumentationGraph } from "./ArgumentationGraph";
import { DocumentPanel } from "./DocumentPanel";
import { LinguisticPanel } from "./LinguisticPanel";
import { PipelinePanel } from "./PipelinePanel";
import { SupportSummary } from "./SupportSummary";
import { VerdictPanel } from "./VerdictPanel";
import { VeriGraphLogo } from "./VeriGraphLogo";

const CUSTOM_CASE = "custom";

const ATOM_ROLE_LABELS: Partial<Record<DecomposedAtom["role"], string>> = {
  CORE: "Core fact",
  NUMERIC_CONSTRAINT: "Numeric constraint",
  TEMPORAL_CONSTRAINT: "Temporal constraint",
  ATTRIBUTION: "Attribution",
  LOCATION_CONSTRAINT: "Location constraint",
  CAUSAL_RELATION: "Causal relation",
  CONDITIONAL: "Conditional",
  MODALITY_CONSTRAINT: "Modality constraint",
};

function customDocument(index: number): DemoDocument {
  return {
    id: `custom-source-${index}`,
    title: `Source ${index}`,
    url: `urn:verigraph:custom:${index}`,
    text: "",
  };
}

const TOPIC_LABELS: Record<DemoTopic, string> = {
  POLITICS_ELECTIONS: "Politics & elections",
  PUBLIC_HEALTH: "Public health",
  CLIMATE_ENVIRONMENT: "Climate & environment",
  ECONOMY_BUSINESS: "Economy & business",
  SCIENCE_TECHNOLOGY: "Science & technology",
  LAW_PUBLIC_POLICY: "Law & public policy",
  CONFLICT_SECURITY: "Conflict & security",
  SOCIETY_CULTURE: "Society & culture",
};

const CHALLENGE_LABELS: Record<DemoChallenge, string> = {
  MULTI_PART: "Multi-part",
  NEGATION: "Negation",
  NUMBERS: "Numbers",
  TIME: "Time",
  ATTRIBUTION: "Attribution",
  CAUSALITY: "Causality",
  LIST_SET_REASONING: "List/set reasoning",
  CONFLICTING_SOURCES: "Conflicting sources",
  SPARSE_EVIDENCE: "Sparse evidence",
};

function optionLabel(item: DemoCaseSummary, index: number): string {
  const compact = (item.displayTitle || item.claim).replace(/\s+/g, " ").trim();
  const excerpt = compact.length > 72 ? `${compact.slice(0, 69)}…` : compact;
  return `${item.featured ? "★ " : ""}${String(index + 1).padStart(2, "0")} — ${excerpt}`;
}

function documentsMatch(left: DemoDocument[], right: DemoDocument[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((document, index) => {
    const comparison = right[index];
    return (
      comparison !== undefined &&
      document.id === comparison.id &&
      document.title === comparison.title &&
      document.url === comparison.url &&
      document.text === comparison.text
    );
  });
}

function referenceClass(label: ReferenceLabel): string {
  return `reference-${label.toLowerCase().replaceAll("_", "-")}`;
}

export function VeriGraphApp({ mode = deploymentMode }: { mode?: DeploymentMode }) {
  const walkthrough = mode === "walkthrough";
  const dataApi = walkthrough ? walkthroughApi : api;
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [catalog, setCatalog] = useState<DemoCaseSummary[]>([]);
  const [sampleQuery, setSampleQuery] = useState(() => searchParams.get("q") ?? "");
  const [topicFilter, setTopicFilter] = useState(() => searchParams.get("topic") ?? "");
  const [challengeFilter, setChallengeFilter] = useState(() => searchParams.get("challenge") ?? "");
  const [labelFilter, setLabelFilter] = useState(() => searchParams.get("label") ?? "");
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState(CUSTOM_CASE);
  const [referenceCase, setReferenceCase] = useState<DemoCase | null>(null);
  const [claim, setClaim] = useState("");
  const [documents, setDocuments] = useState<DemoDocument[]>(() => [customDocument(1)]);
  const [activeDocumentId, setActiveDocumentId] = useState("custom-source-1");
  const [atoms, setAtoms] = useState<DecomposedAtom[]>([]);
  const [composition, setComposition] = useState<ClaimComposition>("SINGLE");
  const [evidence, setEvidence] = useState<AtomEvidence[]>([]);
  const [classifications, setClassifications] = useState<AtomSupportClassification[]>([]);
  const [evidenceAudit, setEvidenceAudit] = useState<GroundedEvidenceAuditResult | null>(null);
  const [selectedAtomId, setSelectedAtomId] = useState<string | null>(null);
  const [decompositionState, setDecompositionState] = useState<StageState>("idle");
  const [retrievalState, setRetrievalState] = useState<StageState>("idle");
  const [nliState, setNliState] = useState<StageState>("idle");
  const [decompositionError, setDecompositionError] = useState<string | null>(null);
  const [retrievalError, setRetrievalError] = useState<string | null>(null);
  const [nliError, setNliError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<VerdictAggregationResult | null>(null);
  const [verdictState, setVerdictState] = useState<StageState>("idle");
  const [recordedVerdict, setRecordedVerdict] = useState<VerdictAggregationResult | null>(null);
  const [linguisticsOpen, setLinguisticsOpen] = useState(true);
  const [evidencePerAtom, setEvidencePerAtom] = useState(DEFAULT_EVIDENCE_PER_ATOM);
  const [loading, setLoading] = useState(true);
  const [caseLoading, setCaseLoading] = useState(false);
  const linguistics = useLinguisticAnalysis();
  const claimRef = useRef<HTMLTextAreaElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const requestVersionRef = useRef(0);
  const caseRequestVersionRef = useRef(0);
  const nextCustomDocumentRef = useRef(2);
  const caseCacheRef = useRef(new Map<string, DemoCase>());

  const catalogById = useMemo(
    () => new Map(catalog.map((item) => [item.id, item])),
    [catalog],
  );
  const topics = useMemo(
    () => [...new Set(catalog.flatMap((item) => item.topics ?? []))].sort(),
    [catalog],
  );
  const challenges = useMemo(
    () => [...new Set(catalog.flatMap((item) => item.challenges ?? []))].sort(),
    [catalog],
  );
  const filteredCatalog = useMemo(() => {
    const query = sampleQuery.trim().toLocaleLowerCase();
    return catalog
      .filter((item) => {
        const searchable = `${item.displayTitle ?? ""} ${item.claim}`.toLocaleLowerCase();
        return (
          (!query || searchable.includes(query)) &&
          (!topicFilter || item.topics?.includes(topicFilter as DemoTopic)) &&
          (!challengeFilter || item.challenges?.includes(challengeFilter as DemoChallenge)) &&
          (!labelFilter || item.label === labelFilter)
        );
      })
      .sort((left, right) => Number(Boolean(right.featured)) - Number(Boolean(left.featured)));
  }, [catalog, challengeFilter, labelFilter, sampleQuery, topicFilter]);
  const rawPanel = searchParams.get("panel");
  const mobilePanel: MobilePanel =
    rawPanel === "atoms" || rawPanel === "document" || rawPanel === "pipeline"
      ? rawPanel
      : "pipeline";

  const setParams = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      Object.entries(changes).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  useEffect(() => {
    let active = true;
    Promise.all([dataApi.cases(), dataApi.health()])
      .then(async ([cases, status]) => {
        if (!active) return;
        setCatalog(cases);
        setHealth(status);
        const requested = searchParams.get("case");
        const initial = cases.find((item) => item.id === requested) ?? cases[0];
        if (!initial) return;
        setSelectedCaseId(initial.id);
        setClaim(initial.claim);
        setCaseLoading(true);
        const detail = await dataApi.case(initial.id);
        if (!active) return;
        caseCacheRef.current.set(detail.id, detail);
        setReferenceCase(detail);
        setDocuments(detail.documents);
        setActiveDocumentId(detail.documents[0].id);
      })
      .catch((reason: Error) => {
        if (!active) return;
        setDecompositionError(reason.message);
      })
      .finally(() => {
        if (!active) return;
        setCaseLoading(false);
        setLoading(false);
      });
    return () => {
      active = false;
    };
    // The initial URL is consumed once. Later selections are handled explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (decompositionError || retrievalError || nliError) errorRef.current?.focus();
  }, [decompositionError, retrievalError, nliError]);

  const referenceMatches = Boolean(
    selectedCaseId !== CUSTOM_CASE &&
      referenceCase?.id === selectedCaseId &&
      referenceCase.claim === claim &&
      documentsMatch(referenceCase.documents, documents),
  );

  const resetDecomposition = () => {
    requestVersionRef.current += 1;
    setAtoms([]);
    setComposition("SINGLE");
    setEvidence([]);
    setClassifications([]);
    setEvidenceAudit(null);
    setSelectedAtomId(null);
    setDecompositionState("idle");
    setRetrievalState("idle");
    setNliState("idle");
    setVerdictState("idle");
    setDecompositionError(null);
    setRetrievalError(null);
    setNliError(null);
    linguistics.clear();
  };

  const resetRetrieval = () => {
    requestVersionRef.current += 1;
    setEvidence([]);
    setClassifications([]);
    setEvidenceAudit(null);
    setRetrievalState("idle");
    setNliState("idle");
    setVerdictState("idle");
    setRetrievalError(null);
    setNliError(null);
  };

  const detachSample = () => {
    setSelectedCaseId(CUSTOM_CASE);
    setParams({ case: null });
  };

  const chooseCase = async (id: string) => {
    resetDecomposition();
    setSelectedCaseId(id);
    const requestVersion = caseRequestVersionRef.current + 1;
    caseRequestVersionRef.current = requestVersion;
    if (id === CUSTOM_CASE) {
      const first = customDocument(1);
      nextCustomDocumentRef.current = 2;
      setReferenceCase(null);
      setClaim("");
      setDocuments([first]);
      setActiveDocumentId(first.id);
      setParams({ case: null });
      return;
    }
    const summary = catalogById.get(id);
    if (!summary) return;
    setClaim(summary.claim);
    setDocuments(summary.documents.map((document) => ({ ...document, text: "" })));
    setActiveDocumentId(summary.documents[0].id);
    setParams({ case: id });
    setCaseLoading(true);
    try {
      const detail = caseCacheRef.current.get(id) ?? (await dataApi.case(id));
      if (caseRequestVersionRef.current !== requestVersion) return;
      caseCacheRef.current.set(id, detail);
      setReferenceCase(detail);
      setClaim(detail.claim);
      setDocuments(detail.documents);
      setActiveDocumentId(detail.documents[0].id);
    } catch (reason) {
      if (caseRequestVersionRef.current !== requestVersion) return;
      setDecompositionError(
        reason instanceof Error ? reason.message : "Could not load this demo sample.",
      );
    } finally {
      if (caseRequestVersionRef.current === requestVersion) setCaseLoading(false);
    }
  };

  const editClaim = (value: string) => {
    if (walkthrough) return;
    setClaim(value);
    detachSample();
    resetDecomposition();
  };

  const editDocument = (documentId: string, value: string) => {
    if (walkthrough) return;
    setDocuments((current) =>
      current.map((document) =>
        document.id === documentId ? { ...document, text: value } : document,
      ),
    );
    detachSample();
    resetRetrieval();
  };

  const renameDocument = (documentId: string, title: string) => {
    if (walkthrough) return;
    setDocuments((current) =>
      current.map((document) =>
        document.id === documentId ? { ...document, title } : document,
      ),
    );
    detachSample();
    resetRetrieval();
  };

  const addDocument = () => {
    if (walkthrough) return;
    if (documents.length >= 8) return;
    const next = customDocument(nextCustomDocumentRef.current);
    nextCustomDocumentRef.current += 1;
    setDocuments((current) => [...current, next]);
    setActiveDocumentId(next.id);
    detachSample();
    resetRetrieval();
  };

  const removeDocument = (documentId: string) => {
    if (walkthrough) return;
    if (documents.length === 1) return;
    const index = documents.findIndex((document) => document.id === documentId);
    const nextDocuments = documents.filter((document) => document.id !== documentId);
    setDocuments(nextDocuments);
    if (activeDocumentId === documentId) {
      setActiveDocumentId(nextDocuments[Math.min(index, nextDocuments.length - 1)].id);
    }
    detachSample();
    resetRetrieval();
  };

  const retrieveAtoms = async (
    atomInputs: Array<{ id: string; text: string }>,
    budget: number,
  ) => {
    if (referenceMatches && referenceCase) {
      return api.retrieveCase(referenceCase.id, atomInputs, budget);
    }
    return api.retrieveDocuments(documents, atomInputs, budget);
  };

  const classifyEvidence = async (
    atomInputs: Array<{ id: string; text: string }>,
    retrievedEvidence: AtomEvidence[],
    requestVersion: number,
  ) => {
    setClassifications([]);
    setEvidenceAudit(null);
    setNliState("running");
    setNliError(null);
    try {
      const result = await api.classifySupport(
        claim,
        atomInputs,
        retrievedEvidence,
        Object.fromEntries(documents.map((document) => [document.id, document.title])),
      );
      if (requestVersionRef.current !== requestVersion) return;
      setClassifications(result.classifications);
      setEvidenceAudit(result.evidenceAudit ?? null);
      setNliState("complete");
    } catch (reason) {
      if (requestVersionRef.current !== requestVersion) return;
      setNliState("error");
      setNliError(
        reason instanceof Error
          ? reason.message
          : "Grounded evidence auditing failed. Check the API and retry.",
      );
    }
  };

  const decompose = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    setDecompositionState("running");
    setRetrievalState("idle");
    setNliState("idle");
    setDecompositionError(null);
    setRetrievalError(null);
    setNliError(null);
    setAtoms([]);
    setComposition("SINGLE");
    setEvidence([]);
    setClassifications([]);
    setEvidenceAudit(null);
    setSelectedAtomId(null);
    linguistics.clear();

    if (walkthrough) {
      if (!referenceCase || !referenceMatches) {
        setDecompositionState("error");
        setDecompositionError("Choose a recorded sample to inspect its saved pipeline run.");
        return;
      }
      setRetrievalState("running");
      setNliState("running");
      try {
        const recorded = await walkthroughApi.run(referenceCase.id);
        if (requestVersionRef.current !== requestVersion) return;
        setAtoms(recorded.atoms);
        setComposition(recorded.composition ?? (recorded.atoms.length > 1 ? "AND" : "SINGLE"));
        setEvidence(recorded.evidence);
        setClassifications(recorded.classifications);
        setEvidenceAudit(recorded.evidenceAudit ?? null);
        linguistics.loadRecorded(recorded.linguistics);
        setRecordedVerdict(recorded.verdict ?? null);
        setDecompositionState("complete");
        setRetrievalState("complete");
        setNliState("complete");
      } catch (reason) {
        if (requestVersionRef.current !== requestVersion) return;
        setDecompositionState("error");
        setRetrievalState("idle");
        setNliState("idle");
        setDecompositionError(
          reason instanceof Error
            ? reason.message
            : "Could not load the recorded pipeline run.",
        );
      }
      return;
    }
    try {
      const result = await api.decompose(claim);
      if (requestVersionRef.current !== requestVersion) return;
      setAtoms(result.atoms);
      setComposition(result.composition);
      setDecompositionState("complete");
      setRetrievalState("running");
      const atomInputs = result.atoms.map(({ id, text }) => ({ id, text }));
      void linguistics.run({
        schemaVersion: result.schemaVersion,
        claimText: claim,
        composition: result.composition,
        atoms: result.atoms,
      });
      try {
        const retrieval = await retrieveAtoms(atomInputs, evidencePerAtom);
        if (requestVersionRef.current !== requestVersion) return;
        setEvidence(retrieval.evidence);
        setRetrievalState("complete");
        await classifyEvidence(atomInputs, retrieval.evidence, requestVersion);
      } catch (reason) {
        if (requestVersionRef.current !== requestVersion) return;
        setRetrievalState("error");
        setNliState("idle");
        setRetrievalError(
          reason instanceof Error
            ? reason.message
            : "Candidate evidence retrieval failed. Check the API and retry.",
        );
      }
    } catch (reason) {
      if (requestVersionRef.current !== requestVersion) return;
      setDecompositionState("error");
      setDecompositionError(
        reason instanceof Error
          ? reason.message
          : "Claim decomposition failed. Check the API and retry.",
      );
    }
  };

  const runRetrieval = async (budget: number) => {
    if (!atoms.length || documents.some((document) => !document.text.trim())) return;
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    setRetrievalState("running");
    setNliState("idle");
    setRetrievalError(null);
    setNliError(null);
    setEvidence([]);
    setClassifications([]);
    setEvidenceAudit(null);
    try {
      const result = await retrieveAtoms(atoms.map(({ id, text }) => ({ id, text })), budget);
      if (requestVersionRef.current !== requestVersion) return;
      setEvidence(result.evidence);
      setRetrievalState("complete");
      await classifyEvidence(
        atoms.map(({ id, text }) => ({ id, text })),
        result.evidence,
        requestVersion,
      );
    } catch (reason) {
      if (requestVersionRef.current !== requestVersion) return;
      setRetrievalState("error");
      setNliState("idle");
      setRetrievalError(
        reason instanceof Error
          ? reason.message
          : "Candidate evidence retrieval failed. Check the API and retry.",
      );
    }
  };

  const retryEvidence = () => void runRetrieval(evidencePerAtom);

  const changeEvidencePerAtom = (budget: number) => {
    if (walkthrough || budget === evidencePerAtom) return;
    setEvidencePerAtom(budget);
    if (atoms.length) void runRetrieval(budget);
  };

  const retryNli = async () => {
    if (!atoms.length || evidence.length !== atoms.length) return;
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    await classifyEvidence(
      atoms.map(({ id, text }) => ({ id, text })),
      evidence,
      requestVersion,
    );
  };

  const selectAtom = (atom: DecomposedAtom, focusClaim = true) => {
    setSelectedAtomId(atom.id);
    const spans = evidence.find((item) => item.atomId === atom.id)?.spans ?? [];
    if (spans.length && !spans.some((span) => span.documentId === activeDocumentId)) {
      setActiveDocumentId(spans[0].documentId);
    }
    if (!focusClaim) return;
    const textarea = claimRef.current;
    if (!textarea) return;
    textarea.focus();
    textarea.setSelectionRange(atom.start, atom.end);
  };

  const selectGraphAtom = (atomId: string) => {
    const atom = atoms.find((item) => item.id === atomId);
    if (atom) selectAtom(atom, false);
  };

  const selectGraphEvidence = (node: EvidenceNode, atomId: string) => {
    const ownerAtom = atoms.find((atom) => atom.id === atomId);
    if (ownerAtom) selectAtom(ownerAtom, false);
    setActiveDocumentId(node.documentId);
    setParams({ panel: "document" });
    window.requestAnimationFrame(() => {
      document.getElementById("verification-workbench")?.scrollIntoView({ block: "start" });
    });
  };

  const selectedAtom = atoms.find((atom) => atom.id === selectedAtomId) ?? null;
  const selectedEvidence =
    evidence.find((item) => item.atomId === selectedAtomId)?.spans ?? [];
  const selectedLinguisticAnalysis =
    linguistics.analyses.find((item) => item.atomId === selectedAtomId) ?? null;
  const selectedLinguisticSummary =
    linguistics.summaries.find((item) => item.atomId === selectedAtomId) ?? null;
  const selectedClassification =
    classifications.find((item) => item.atomId === selectedAtomId) ?? null;
  const selectedEvidenceAudit =
    evidenceAudit?.obligations.find((item) => item.atomId === selectedAtomId) ?? null;
  const selectedRelations = selectedClassification?.relations ?? [];
  const reviewEvidenceRelation = useCallback(
    (span: EvidenceSpan, relation: NLIRelation) => {
      if (!selectedAtomId) return;
      setClassifications((current) =>
        current.map((classification) =>
          classification.atomId !== selectedAtomId
            ? classification
            : {
                ...classification,
                relations: classification.relations.map((item) =>
                  item.spanId === span.id && item.documentId === span.documentId
                    ? { ...item, relation, relevanceFiltered: false }
                    : item,
                ),
              },
        ),
      );
      // A reviewer edit deliberately leaves the model's overall position and
      // returns aggregation to the inspectable obligation-relation rules.
      setEvidenceAudit(null);
    },
    [selectedAtomId],
  );
  const argumentationGraph = useMemo(
    () => buildArgumentationGraph(
      selectedCaseId,
      claim,
      composition,
      atoms,
      evidence,
      classifications,
      documents,
      linguistics.summaries,
      verdict ? new Set(verdict.obligations.flatMap((item) => [
        ...item.supportEdgeIds,
        ...item.attackEdgeIds,
      ])) : undefined,
    ),
    [selectedCaseId, claim, composition, atoms, evidence, classifications, documents, linguistics.summaries, verdict],
  );
  useEffect(() => {
    if (nliState !== "complete" || !atoms.length || classifications.length !== atoms.length) {
      setVerdict(null);
      setVerdictState("idle");
      return;
    }
    // Vercel hosts no backend: a recorded run carries its own aggregation result.
    if (walkthrough) {
      setVerdict(recordedVerdict);
      setVerdictState(recordedVerdict ? "complete" : "idle");
      return;
    }
    // Older recorded/test adapters predate aggregation; they remain graph-only.
    const aggregateVerdict = (api as Partial<typeof api>).aggregateVerdict;
    if (!aggregateVerdict) {
      setVerdict(null);
      setVerdictState("idle");
      return;
    }
    let cancelled = false;
    setVerdictState("running");
    void aggregateVerdict({
      claimId: selectedCaseId,
      composition,
      atoms,
      evidence,
      classifications,
      linguisticSummaries: linguistics.summaries,
      materialOmission: evidenceAudit?.materialOmission,
      claimAudit: evidenceAudit?.claimPosition,
    }).then((result) => {
      if (cancelled) return;
      setVerdict(result);
      setVerdictState("complete");
    }).catch(() => {
      if (cancelled) return;
      setVerdict(null);
      setVerdictState("error");
    });
    return () => { cancelled = true; };
  }, [selectedCaseId, claim, composition, atoms, evidence, classifications, evidenceAudit, linguistics.summaries, nliState, walkthrough, recordedVerdict]);
  const graphLinkCount = argumentationGraph.stats.supportEdgeCount + argumentationGraph.stats.attackEdgeCount;
  const relationsByAtomId = useMemo(
    () => new Map(classifications.map((item) => [item.atomId, item.relations])),
    [classifications],
  );
  const describeAtom = useCallback(
    (atom: DecomposedAtom): string | null => {
      const role = ATOM_ROLE_LABELS[atom.role] ?? atom.role.replaceAll("_", " ").toLowerCase();
      const relations = relationsByAtomId.get(atom.id);
      if (!relations) return role;
      const support = relations.filter((item) => item.relation === "ENTAILMENT").length;
      const attack = relations.filter((item) => item.relation === "CONTRADICTION").length;
      return `${role} · ${support} support · ${attack} attack`;
    },
    [relationsByAtomId],
  );
  const obligationStates = useMemo(
    () => Object.fromEntries((verdict?.obligations ?? []).map((item) => [item.obligationId, item.state])),
    [verdict],
  );
  const graphState: StageState =
    nliState === "complete"
      ? "complete"
      : nliState === "running"
        ? "running"
        : nliState === "error"
          ? "error"
          : "idle";
  const evidenceCount = evidence.reduce((count, item) => count + item.spans.length, 0);
  const relationCount = classifications.reduce(
    (count, item) => count + item.relations.length,
    0,
  );
  const activeError = decompositionError ?? retrievalError ?? nliError;
  const workflowRunning =
    decompositionState === "running" ||
    retrievalState === "running" ||
    nliState === "running";
  const documentsReady = documents.length > 0 && documents.every((document) => document.text.trim());
  const pipelineConfigured = Boolean(
    health?.decompositionReady && health.retrievalConfigured,
  );

  return (
    <main className="app-shell">
      <a className="skip-link" href="#verification-workbench">
        Skip to Verification Workbench
      </a>

      <header className="site-header">
        <div className="brand" translate="no">
          <VeriGraphLogo />
          <span>
            VeriGraph
            <small>EVIDENCE AUDIT WORKBENCH</small>
          </span>
        </div>
        <span className="header-context">Claim + Sources → Draft status</span>
        <div className="header-actions">
          <span
            className={`health-chip ${pipelineConfigured ? "health-ready" : "health-unconfigured"}`}
            title={
              health
                ? `Decomposition and grounded audit: ${health.decompositionModel} (${health.decompositionReady ? "ready" : "unavailable"}); retrieval: ${health.retrievalModel}; linguistics: ${health.linguisticsModel} (${health.linguisticsConfigured ? "ready" : "not configured"}); compatibility NLI: ${health.nliConfigured ? health.nliModel : "not loaded"}`
                : undefined
            }
            aria-live="polite"
          >
            <Activity size={13} aria-hidden="true" />
            {walkthrough
              ? "Recorded walkthrough"
              : pipelineConfigured
                ? "Pipeline configured"
                : "Pipeline setup required"}
          </span>
        </div>
      </header>

      <section className="case-toolbar" aria-label="Demo sample selection">
        <div className="sample-browser">
          <label className="sample-search">
            <span>Find a sample</span>
            <input
              type="search"
              value={sampleQuery}
              placeholder="Search claims or titles"
              onChange={(event) => {
                setSampleQuery(event.target.value);
                setParams({ q: event.target.value || null });
              }}
            />
          </label>
          <label className="sample-filter">
            <span>Topic</span>
            <select value={topicFilter} onChange={(event) => {
              setTopicFilter(event.target.value);
              setParams({ topic: event.target.value || null });
            }}>
              <option value="">All topics</option>
              {topics.map((topic) => <option value={topic} key={topic}>{TOPIC_LABELS[topic]}</option>)}
            </select>
          </label>
          <label className="sample-filter">
            <span>Challenge</span>
            <select value={challengeFilter} onChange={(event) => {
              setChallengeFilter(event.target.value);
              setParams({ challenge: event.target.value || null });
            }}>
              <option value="">All challenges</option>
              {challenges.map((challenge) => (
                <option value={challenge} key={challenge}>{CHALLENGE_LABELS[challenge]}</option>
              ))}
            </select>
          </label>
          <label className="sample-filter">
            <span>Verdict filter</span>
            <select value={labelFilter} onChange={(event) => {
              setLabelFilter(event.target.value);
              setParams({ label: event.target.value || null });
            }}>
              <option value="">All labels</option>
              <option value="SUPPORTED">Supported</option>
              <option value="REFUTED">Refuted</option>
              <option value="NOT_ENOUGH_EVIDENCE">Not enough evidence</option>
              <option value="CONFLICTING_EVIDENCE">Conflicting evidence</option>
            </select>
          </label>
          <label className="sample-control">
            <span>{walkthrough ? "Recorded Sample" : "Demo Sample"}</span>
          <select
            name="demo-sample"
            value={
              selectedCaseId === CUSTOM_CASE || filteredCatalog.some((item) => item.id === selectedCaseId)
                ? selectedCaseId
                : ""
            }
            onChange={(event) => void chooseCase(event.target.value)}
            disabled={loading || caseLoading}
          >
            <option value="" disabled>Select a sample</option>
            {!walkthrough ? <option value={CUSTOM_CASE}>Custom Input</option> : null}
            {filteredCatalog.map((item, index) => (
              <option value={item.id} key={item.id}>
                {optionLabel(item, index)}
              </option>
            ))}
          </select>
          </label>
          {sampleQuery || topicFilter || challengeFilter || labelFilter ? (
            <button type="button" className="clear-filters" onClick={() => {
              setSampleQuery("");
              setTopicFilter("");
              setChallengeFilter("");
              setLabelFilter("");
              setParams({ q: null, topic: null, challenge: null, label: null });
            }}>Clear filters</button>
          ) : null}
        </div>
        <span className="sample-status">
          {loading
            ? "Loading samples…"
            : caseLoading
              ? "Loading sources…"
              : `${filteredCatalog.length} of ${catalog.length} ${walkthrough ? "recorded" : "live"} samples`}
        </span>
        <div className="toolbar-spacer" />
        {referenceMatches && referenceCase ? (
          <span className={`reference-label ${referenceClass(referenceCase.label)}`}>
            Reference Label · {referenceCase.label.replaceAll("_", " ")}
          </span>
        ) : (
          <span className="custom-label">
            {walkthrough ? "Recorded walkthrough" : "Custom Input"}
          </span>
        )}
      </section>

      {walkthrough ? (
        <p className="walkthrough-notice" role="status">
          Demo mode — results are precomputed. Live analysis is available locally.
        </p>
      ) : null}

      <section className="claim-hero" aria-labelledby="claim-heading">
        <h1 className="sr-only" id="claim-heading">
          Claim to Decompose
        </h1>
        <div className="claim-kicker">
          <span>CLAIM</span>
          <span>Stage 01 input</span>
        </div>
        <form onSubmit={decompose} className="claim-form">
          <label className="claim-editor">
            <span className="sr-only">Claim to decompose</span>
            <textarea
              ref={claimRef}
              required
              name="claim"
              autoComplete="off"
              maxLength={5000}
              rows={3}
              value={claim}
              onChange={(event) => editClaim(event.target.value)}
              readOnly={walkthrough}
              placeholder="Enter a factual claim…"
            />
          </label>
          <button
            type="submit"
            className="primary-button"
            disabled={workflowRunning || caseLoading || !claim.trim() || !documentsReady}
          >
            {workflowRunning ? (
              <LoaderCircle className="spin" size={17} aria-hidden="true" />
            ) : (
              <Play size={16} fill="currentColor" aria-hidden="true" />
            )}
            {decompositionState === "running"
              ? walkthrough
                ? "Loading Recorded Run…"
                : "Decomposing…"
              : retrievalState === "running"
                ? walkthrough
                  ? "Loading Recorded Run…"
                  : "Matching Evidence…"
                : nliState === "running"
                  ? walkthrough
                    ? "Loading Recorded Run…"
                    : "Auditing Evidence…"
                  : walkthrough
                    ? "Inspect Recorded Run"
                    : "Decompose Claim"}
          </button>
        </form>
        <div className="claim-status" aria-live="polite">
          {walkthrough
            ? decompositionState === "complete"
              ? "Recorded local outputs are displayed below. Select an atom to inspect them."
              : "Choose a sample and inspect its recorded local pipeline run."
            : selectedAtomId
            ? "The selected atom is highlighted in the claim editor."
            : nliState === "running"
              ? "Candidate retrieval complete. Auditing grounded relations for every obligation."
              : retrievalState === "running"
                ? "Decomposition complete. Semantically matching candidate sentences across sources."
                : decompositionState === "complete"
                  ? "Select an atom to locate its claim source and candidate evidence."
                  : "The claim is decomposed first; local embeddings then rank candidate source sentences."}
        </div>
        {activeError ? (
          <div className="inline-error" role="alert" tabIndex={-1} ref={errorRef}>
            <strong>
              {retrievalError
                ? "Claim decomposed; candidate retrieval failed."
                : nliError
                  ? "Evidence matched; grounded evidence audit failed."
                  : "Could not complete this request."}
            </strong>
            <span>{activeError}</span>
          </div>
        ) : null}
      </section>

      <div className="mobile-panel-tabs" aria-label="Workbench panel">
        {(["atoms", "pipeline", "document"] as const).map((panel) => (
          <button
            key={panel}
            type="button"
            aria-pressed={mobilePanel === panel}
            onClick={() => setParams({ panel })}
          >
            {panel}
          </button>
        ))}
      </div>

      <section className="workbench" id="verification-workbench">
        <div className="workbench-pane atoms-pane" data-mobile-active={mobilePanel === "atoms"}>
          <AtomRail
            atoms={atoms}
            state={decompositionState}
            selectedAtomId={selectedAtomId}
            onSelect={selectAtom}
            describeAtom={describeAtom}
            selectedDetail={selectedAtom ? (
              <div className="selected-atom-detail" key={selectedAtom.id}>
                <LinguisticPanel
                  atom={selectedAtom}
                  analysis={selectedLinguisticAnalysis}
                  summary={selectedLinguisticSummary}
                  state={linguistics.state}
                  error={linguistics.error}
                  onRetry={() => void linguistics.retry()}
                  open={linguisticsOpen}
                  onToggle={() => setLinguisticsOpen((current) => !current)}
                />
                <SupportSummary
                  classification={selectedClassification}
                  audit={selectedEvidenceAudit}
                  materialOmission={evidenceAudit?.materialOmission}
                  claimAudit={evidenceAudit?.claimPosition}
                  state={nliState}
                />
              </div>
            ) : undefined}
          />
        </div>
        <div className="workbench-pane pipeline-pane" data-mobile-active={mobilePanel === "pipeline"}>
          <PipelinePanel
            decompositionState={decompositionState}
            retrievalState={retrievalState}
            nliState={nliState}
            graphState={graphState}
            verdictState={verdictState}
            verdict={verdict?.verdict ?? null}
            graphLinkCount={graphLinkCount}
            atomCount={atoms.length}
            evidenceCount={evidenceCount}
            relationCount={relationCount}
            onRetryEvidence={retryEvidence}
            evidencePerAtom={evidencePerAtom}
            onEvidencePerAtomChange={walkthrough ? undefined : changeEvidencePerAtom}
            onRetryNli={retryNli}
            recorded={walkthrough}
          />
        </div>
        <div className="workbench-pane evidence-pane" data-mobile-active={mobilePanel === "document"}>
          <DocumentPanel
            documents={documents}
            activeDocumentId={activeDocumentId}
            onActivate={setActiveDocumentId}
            onTextChange={editDocument}
            onTitleChange={renameDocument}
            onAdd={addDocument}
            onRemove={removeDocument}
            onRelationChange={walkthrough ? undefined : reviewEvidenceRelation}
            spans={selectedEvidence}
            relations={selectedRelations}
            selectedAtomText={selectedAtom?.text ?? null}
            retrievalState={retrievalState}
            evidencePerAtom={evidencePerAtom}
            readOnly={walkthrough}
          />
        </div>
      </section>

      {nliState === "complete" ? (
        <>
          <ArgumentationGraph
            graph={argumentationGraph}
            selectedAtomId={selectedAtomId}
            onSelectAtom={selectGraphAtom}
            onSelectEvidence={selectGraphEvidence}
            obligationStates={obligationStates}
          />
          {verdict ? (
            <VerdictPanel
              result={verdict}
              atoms={atoms}
              referenceLabel={referenceMatches ? referenceCase?.label : undefined}
            />
          ) : null}
        </>
      ) : null}

      <footer className="provenance-strip">
        <span>
          <Sparkles size={13} aria-hidden="true" /> Linguistically grounded verification obligations
        </span>
        <span>
          {walkthrough
            ? "Recorded local pipeline · derived argumentation graph · deterministic four-way verdict"
            : "Live local models · derived argumentation graph · deterministic four-way verdict"}
        </span>
      </footer>
    </main>
  );
}
