"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Activity, LoaderCircle, Play } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { candidateAssessments, reviseAssessment } from "@/lib/assessment";
import { buildArgumentationGraph } from "@/lib/argumentationGraph";
import { deploymentMode, type DeploymentMode } from "@/lib/deployment";
import { DEFAULT_EVIDENCE_PER_ATOM } from "@/lib/retrieval";
import { walkthroughApi } from "@/lib/walkthrough";
import type {
  AtomEvidence,
  AtomEvidenceAssessment,
  ClaimComposition,
  EvidenceNode,
  EvidenceSpan,
  DecomposedAtom,
  DemoCase,
  DemoCaseSummary,
  DemoCategory,
  DemoDocument,
  GroundedEvidenceAssessment,
  Health,
  MobilePanel,
  CandidateRelation,
  ReferenceLabel,
  RetrievalMethod,
  StageState,
  SymbolicExecution,
  SymbolicPremise,
  VerdictAggregationResult,
} from "@/lib/types";
import { AtomRail } from "./AtomRail";
import { ArgumentationGraph } from "./ArgumentationGraph";
import { DocumentPanel } from "./DocumentPanel";
import { PipelinePanel } from "./PipelinePanel";
import { SupportSummary } from "./SupportSummary";
import { SymbolicProofPanel } from "./SymbolicProofPanel";
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
    layout: "PROSE",
  };
}

type CategoryFilter = "" | DemoCategory | "AVERITEC";

const CATEGORIES: Array<{ value: CategoryFilter; label: string }> = [
  { value: "", label: "All" },
  { value: "SCIENCE", label: "Science" },
  { value: "HISTORY", label: "History" },
  { value: "GEOGRAPHY", label: "Geography" },
  { value: "TECHNOLOGY", label: "Technology" },
  { value: "CURRENT_AFFAIRS", label: "Current Affairs" },
  { value: "AVERITEC", label: "AVeriTeC" },
];

function optionLabel(item: DemoCaseSummary, index: number): string {
  const compact = (item.displayTitle || item.claim).replace(/\s+/g, " ").trim();
  const excerpt = compact.length > 72 ? `${compact.slice(0, 69)}…` : compact;
  return `${String(index + 1).padStart(2, "0")} — ${excerpt}`;
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
      && document.layout === comparison.layout
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
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>(() => {
    const requested = searchParams.get("category");
    return CATEGORIES.some(({ value }) => value === requested) ? requested as CategoryFilter : "";
  });
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState(CUSTOM_CASE);
  const [referenceCase, setReferenceCase] = useState<DemoCase | null>(null);
  const [claim, setClaim] = useState("");
  const [documents, setDocuments] = useState<DemoDocument[]>(() => [customDocument(1)]);
  const [activeDocumentId, setActiveDocumentId] = useState("custom-source-1");
  const [atoms, setAtoms] = useState<DecomposedAtom[]>([]);
  const [composition, setComposition] = useState<ClaimComposition>("SINGLE");
  const [evidence, setEvidence] = useState<AtomEvidence[]>([]);
  const [assessments, setAssessments] = useState<AtomEvidenceAssessment[]>([]);
  const [assessment, setAssessment] = useState<GroundedEvidenceAssessment | null>(null);
  const [reasoning, setReasoning] = useState<SymbolicExecution[]>([]);
  const [selectedAtomId, setSelectedAtomId] = useState<string | null>(null);
  const [focusedInferenceSpans, setFocusedInferenceSpans] = useState<Set<string> | null>(null);
  const [decompositionState, setDecompositionState] = useState<StageState>("idle");
  const [retrievalState, setRetrievalState] = useState<StageState>("idle");
  const [assessmentState, setAssessmentState] = useState<StageState>("idle");
  const [reasoningState, setReasoningState] = useState<StageState>("idle");
  const [decompositionError, setDecompositionError] = useState<string | null>(null);
  const [retrievalError, setRetrievalError] = useState<string | null>(null);
  const [assessmentError, setAssessmentError] = useState<string | null>(null);
  const [reasoningError, setReasoningError] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<VerdictAggregationResult | null>(null);
  const [verdictState, setVerdictState] = useState<StageState>("idle");
  const [recordedVerdict, setRecordedVerdict] = useState<VerdictAggregationResult | null>(null);
  const [evidencePerAtom, setEvidencePerAtom] = useState(DEFAULT_EVIDENCE_PER_ATOM);
  const [retrievalMethod, setRetrievalMethod] = useState<RetrievalMethod>("HYBRID");
  const [loading, setLoading] = useState(true);
  const [caseLoading, setCaseLoading] = useState(false);
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
  const catalogIndexById = useMemo(
    () => new Map(catalog.map((item, index) => [item.id, index])),
    [catalog],
  );
  const filteredCatalog = useMemo(() => {
    if (!categoryFilter) return catalog;
    if (categoryFilter === "AVERITEC") {
      return catalog.filter((item) => item.origin === "AVERITEC");
    }
    return catalog.filter(
      (item) => item.origin === "CONSTRUCTED" && item.category === categoryFilter,
    );
  }, [catalog, categoryFilter]);
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
    if (decompositionError || retrievalError || assessmentError || reasoningError) errorRef.current?.focus();
  }, [decompositionError, retrievalError, assessmentError, reasoningError]);

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
    setAssessments([]);
    setAssessment(null);
    setReasoning([]);
    setSelectedAtomId(null);
    setFocusedInferenceSpans(null);
    setDecompositionState("idle");
    setRetrievalState("idle");
    setAssessmentState("idle");
    setReasoningState("idle");
    setVerdictState("idle");
    setDecompositionError(null);
    setRetrievalError(null);
    setAssessmentError(null);
    setReasoningError(null);
  };

  const resetRetrieval = () => {
    requestVersionRef.current += 1;
    setEvidence([]);
    setAssessments([]);
    setAssessment(null);
    setReasoning([]);
    setRetrievalState("idle");
    setAssessmentState("idle");
    setReasoningState("idle");
    setVerdictState("idle");
    setRetrievalError(null);
    setAssessmentError(null);
    setReasoningError(null);
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
    method: RetrievalMethod,
  ) => {
    if (referenceMatches && referenceCase) {
      return api.retrieveCase(referenceCase.id, atomInputs, budget, method);
    }
    return api.retrieveDocuments(documents, atomInputs, budget, method);
  };

  const runReasoning = async (
    atomInputs: Array<{ id: string; text: string }>,
    retrievedEvidence: AtomEvidence[],
    groundedAssessment: GroundedEvidenceAssessment,
    requestVersion: number,
  ) => {
    setReasoningState("running");
    setReasoningError(null);
    setReasoning([]);
    try {
      const result = referenceMatches && referenceCase
        ? await api.reasonCase(referenceCase.id, claim, atomInputs, retrievedEvidence, groundedAssessment)
        : await api.reasonDocuments(documents, claim, atomInputs, retrievedEvidence, groundedAssessment);
      if (requestVersionRef.current !== requestVersion) return;
      setReasoning(result.executions);
      setReasoningState("complete");
    } catch (reason) {
      if (requestVersionRef.current !== requestVersion) return;
      setReasoningState("error");
      setReasoningError(reason instanceof Error ? reason.message : "Symbolic reasoning failed. Retry this step.");
    }
  };

  const assessEvidence = async (
    atomInputs: Array<{ id: string; text: string }>,
    retrievedEvidence: AtomEvidence[],
    requestVersion: number,
  ) => {
    setAssessments([]);
    setAssessment(null);
    setReasoning([]);
    setAssessmentState("running");
    setReasoningState("idle");
    setAssessmentError(null);
    setReasoningError(null);
    try {
      const result = referenceMatches && referenceCase
        ? await api.assessCaseEvidence(referenceCase.id, claim, atomInputs, retrievedEvidence)
        : await api.assessDocumentEvidence(documents, claim, atomInputs, retrievedEvidence);
      if (requestVersionRef.current !== requestVersion) return;
      setAssessment(result.assessment);
      setAssessments(candidateAssessments(retrievedEvidence, result.assessment));
      setAssessmentState("complete");
      await runReasoning(atomInputs, retrievedEvidence, result.assessment, requestVersion);
    } catch (reason) {
      if (requestVersionRef.current !== requestVersion) return;
      setAssessmentState("error");
      setAssessmentError(
        reason instanceof Error
          ? reason.message
          : "Evidence assessment failed. Check the API and retry.",
      );
    }
  };

  const decompose = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    setDecompositionState("running");
    setRetrievalState("idle");
    setAssessmentState("idle");
    setReasoningState("idle");
    setDecompositionError(null);
    setRetrievalError(null);
    setAssessmentError(null);
    setReasoningError(null);
    setAtoms([]);
    setComposition("SINGLE");
    setEvidence([]);
    setAssessments([]);
    setAssessment(null);
    setReasoning([]);
    setSelectedAtomId(null);
    setFocusedInferenceSpans(null);
    if (walkthrough) {
      if (!referenceCase || !referenceMatches) {
        setDecompositionState("error");
        setDecompositionError("Choose a recorded sample to inspect its saved pipeline run.");
        return;
      }
      setRetrievalState("running");
      setAssessmentState("running");
      setReasoningState("running");
      try {
        const recorded = await walkthroughApi.run(referenceCase.id);
        if (requestVersionRef.current !== requestVersion) return;
        setAtoms(recorded.atoms);
        setComposition(recorded.composition ?? (recorded.atoms.length > 1 ? "AND" : "SINGLE"));
        setEvidence(recorded.evidence);
        setAssessment(recorded.assessment);
        setAssessments(candidateAssessments(recorded.evidence, recorded.assessment));
        setReasoning(recorded.reasoning);
        setRetrievalMethod(recorded.recordedWith.retrievalMethod ?? "HYBRID");
        setRecordedVerdict(recorded.verdict ?? null);
        setDecompositionState("complete");
        setRetrievalState("complete");
        setAssessmentState("complete");
        setReasoningState("complete");
      } catch (reason) {
        if (requestVersionRef.current !== requestVersion) return;
        setDecompositionState("error");
        setRetrievalState("idle");
        setAssessmentState("idle");
        setReasoningState("idle");
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
      try {
        const retrieval = await retrieveAtoms(atomInputs, evidencePerAtom, retrievalMethod);
        if (requestVersionRef.current !== requestVersion) return;
        setEvidence(retrieval.evidence);
        setRetrievalState("complete");
        await assessEvidence(atomInputs, retrieval.evidence, requestVersion);
      } catch (reason) {
        if (requestVersionRef.current !== requestVersion) return;
        setRetrievalState("error");
        setAssessmentState("idle");
        setReasoningState("idle");
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

  const runRetrieval = async (budget: number, method: RetrievalMethod) => {
    if (!atoms.length || documents.some((document) => !document.text.trim())) return;
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    setRetrievalState("running");
    setAssessmentState("idle");
    setReasoningState("idle");
    setRetrievalError(null);
    setAssessmentError(null);
    setReasoningError(null);
    setEvidence([]);
    setAssessments([]);
    setAssessment(null);
    setReasoning([]);
    try {
      const result = await retrieveAtoms(atoms.map(({ id, text }) => ({ id, text })), budget, method);
      if (requestVersionRef.current !== requestVersion) return;
      setEvidence(result.evidence);
      setRetrievalState("complete");
      await assessEvidence(
        atoms.map(({ id, text }) => ({ id, text })),
        result.evidence,
        requestVersion,
      );
    } catch (reason) {
      if (requestVersionRef.current !== requestVersion) return;
      setRetrievalState("error");
      setAssessmentState("idle");
      setReasoningState("idle");
      setRetrievalError(
        reason instanceof Error
          ? reason.message
          : "Candidate evidence retrieval failed. Check the API and retry.",
      );
    }
  };

  const retryEvidence = () => void runRetrieval(evidencePerAtom, retrievalMethod);

  const changeEvidencePerAtom = (budget: number) => {
    if (walkthrough || budget === evidencePerAtom) return;
    setEvidencePerAtom(budget);
    if (atoms.length) void runRetrieval(budget, retrievalMethod);
  };

  const changeRetrievalMethod = (method: RetrievalMethod) => {
    if (walkthrough || method === retrievalMethod) return;
    setRetrievalMethod(method);
    if (atoms.length) void runRetrieval(evidencePerAtom, method);
  };

  const retryAssessment = async () => {
    if (!atoms.length || evidence.length !== atoms.length) return;
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    await assessEvidence(
      atoms.map(({ id, text }) => ({ id, text })),
      evidence,
      requestVersion,
    );
  };

  const retryReasoning = async () => {
    if (!atoms.length || !assessment || evidence.length !== atoms.length) return;
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    await runReasoning(
      atoms.map(({ id, text }) => ({ id, text })), evidence, assessment, requestVersion,
    );
  };

  const selectAtom = (atom: DecomposedAtom, focusClaim = true, preserveInference = false) => {
    setSelectedAtomId(atom.id);
    if (!preserveInference) setFocusedInferenceSpans(null);
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
    setFocusedInferenceSpans(new Set([
      `${node.documentId}:${node.start}:${node.end}`,
      ...(node.listItems ?? []).map((item) => `${item.documentId}:${item.start}:${item.end}`),
    ]));
    setActiveDocumentId(node.documentId);
    setParams({ panel: "document" });
    window.requestAnimationFrame(() => {
      document.getElementById("verification-workbench")?.scrollIntoView({ block: "start" });
    });
  };

  const selectGraphInference = (node: import("@/lib/types").InferenceNode, premises: EvidenceNode[]) => {
    const ownerAtom = atoms.find((atom) => atom.id === node.atomId);
    if (ownerAtom) selectAtom(ownerAtom, false, true);
    setFocusedInferenceSpans(new Set(premises.flatMap((premise) => [
      `${premise.documentId}:${premise.start}:${premise.end}`,
      ...(premise.listItems ?? []).map((item) => `${item.documentId}:${item.start}:${item.end}`),
    ])));
    if (premises[0]) setActiveDocumentId(premises[0].documentId);
    setParams({ panel: "document" });
    window.requestAnimationFrame(() => {
      document.getElementById("verification-workbench")?.scrollIntoView({ block: "start" });
    });
  };

  const selectSymbolicPremise = (premise: SymbolicPremise) => {
    setFocusedInferenceSpans(new Set([
      `${premise.documentId}:${premise.start}:${premise.end}`,
      ...(premise.listItems ?? []).map((item) => `${item.documentId}:${item.start}:${item.end}`),
    ]));
    setActiveDocumentId(premise.documentId);
    setParams({ panel: "document" });
    window.requestAnimationFrame(() => {
      document.getElementById("verification-workbench")?.scrollIntoView({ block: "start" });
    });
  };

  const selectedAtom = atoms.find((atom) => atom.id === selectedAtomId) ?? null;
  const selectedEvidenceForAtom = evidence.find((item) => item.atomId === selectedAtomId)?.spans ?? [];
  const selectedProofs = reasoning.filter((item) => item.atomId === selectedAtomId);
  const selectedPremiseSpans: EvidenceSpan[] = selectedProofs.flatMap((proof) => proof.premises.flatMap((premise) => ([{
      id: premise.id,
      documentId: premise.documentId,
      text: premise.text,
      start: premise.start,
      end: premise.end,
      contextSpans: [],
    }, ...(premise.listItems ?? []).map((item) => ({
      id: item.id,
      documentId: item.documentId,
      text: item.text,
      start: item.start,
      end: item.end,
      contextSpans: [],
    }))])));
  const inspectableSpans = [...selectedEvidenceForAtom, ...selectedPremiseSpans].filter((span, index, items) => (
    items.findIndex((candidate) => (
      candidate.documentId === span.documentId && candidate.start === span.start && candidate.end === span.end
    )) === index
  ));
  const selectedEvidence = focusedInferenceSpans
    ? inspectableSpans.filter((span) => focusedInferenceSpans.has(`${span.documentId}:${span.start}:${span.end}`))
    : selectedEvidenceForAtom;
  const selectedClassification =
    assessments.find((item) => item.atomId === selectedAtomId) ?? null;
  const selectedEvidenceAudit =
    assessment?.obligations.find((item) => item.atomId === selectedAtomId) ?? null;
  const selectedRelations = selectedClassification?.relations ?? [];
  const reviewEvidenceRelation = useCallback(
    (span: EvidenceSpan, relation: CandidateRelation) => {
      if (!selectedAtomId || !assessment) return;
      const revised = reviseAssessment(assessment, selectedAtomId, span.id, relation);
      setAssessment(revised);
      setAssessments(candidateAssessments(evidence, revised));
    },
    [assessment, evidence, selectedAtomId],
  );
  const argumentationGraph = useMemo(
    () => buildArgumentationGraph(
      selectedCaseId,
      claim,
      composition,
      atoms,
      evidence,
      assessments,
      documents,
      reasoning,
      verdict ? new Set(verdict.obligations.flatMap((item) => [
        ...item.supportEdgeIds,
        ...item.refuteEdgeIds,
      ])) : undefined,
    ),
    [selectedCaseId, claim, composition, atoms, evidence, assessments, documents, reasoning, verdict],
  );
  useEffect(() => {
    if (assessmentState !== "complete" || reasoningState !== "complete" || !assessment || !atoms.length || assessments.length !== atoms.length) {
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
      assessment,
      reasoning,
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
  }, [selectedCaseId, claim, composition, atoms, evidence, assessments, assessment, reasoning, assessmentState, reasoningState, walkthrough, recordedVerdict]);
  const relationsByAtomId = useMemo(
    () => new Map(assessments.map((item) => [item.atomId, item.relations])),
    [assessments],
  );
  const describeAtom = useCallback(
    (atom: DecomposedAtom): string | null => {
      const role = ATOM_ROLE_LABELS[atom.role] ?? atom.role.replaceAll("_", " ").toLowerCase();
      const relations = relationsByAtomId.get(atom.id);
      if (!relations) return role;
      const support = relations.filter((item) => item.relation === "SUPPORTS" && item.decisive).length;
      const refute = relations.filter((item) => item.relation === "REFUTES" && item.decisive).length;
      const provisional = relations.filter((item) =>
        (item.relation === "SUPPORTS" || item.relation === "REFUTES") && !item.decisive
      ).length;
      return `${role} · ${support} support · ${refute} refute${provisional ? ` · ${provisional} provisional` : ""}`;
    },
    [relationsByAtomId],
  );
  const obligationStates = useMemo(
    () => Object.fromEntries((verdict?.obligations ?? []).map((item) => [item.obligationId, item.state])),
    [verdict],
  );
  const evidenceCount = evidence.reduce((count, item) => count + item.spans.length, 0);
  const relationCounts = useMemo(
    () => assessments.reduce<Record<CandidateRelation, number>>(
      (counts, item) => {
        item.relations.forEach(({ relation }) => { counts[relation] += 1; });
        return counts;
      },
      { SUPPORTS: 0, REFUTES: 0, CONTEXT: 0, NOT_SELECTED: 0 },
    ),
    [assessments],
  );
  const activeError = decompositionError ?? retrievalError ?? assessmentError ?? reasoningError;
  const workflowRunning =
    decompositionState === "running" ||
    retrievalState === "running" ||
    assessmentState === "running" || reasoningState === "running";
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
          <span className="brand-copy">
            <span className="brand-name" aria-label="VeriNICE">
              <span className="brand-name-veri">Veri</span>
              <span className="brand-name-nice">NICE</span>
            </span>
            <small>Verification via Neuro-symbolic Inference with Compositional Evidence</small>
          </span>
        </div>
        <span className="header-context">Claim + Sources → Verdict</span>
        <div className="header-actions">
          <span
            className={`health-chip ${pipelineConfigured ? "health-ready" : "health-unconfigured"}`}
            title={
              health
                ? `Decomposition: ${health.decompositionReady ? "ready" : "unavailable"}; retrieval: ${health.retrievalConfigured ? "ready" : "unavailable"}; symbolic checks: local`
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
          <div className="category-filter" role="group" aria-label="Filter samples by category">
            {CATEGORIES.map((category) => (
              <button
                type="button"
                key={category.value || "all"}
                className={categoryFilter === category.value ? "active" : ""}
                aria-pressed={categoryFilter === category.value}
                onClick={() => {
                  setCategoryFilter(category.value);
                  setParams({ category: category.value || null });
                }}
              >{category.label}</button>
            ))}
          </div>
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
            {filteredCatalog.map((item) => (
              <option value={item.id} key={item.id}>
                {optionLabel(item, catalogIndexById.get(item.id) ?? 0)}
              </option>
            ))}
          </select>
          </label>
        </div>
        {referenceMatches && referenceCase ? (
          <div className="reference-meta">
            <span className={`reference-label ${referenceClass(referenceCase.label)}`}>
              Reference · {referenceCase.label.replaceAll("_", " ")}
            </span>
          </div>
        ) : (
          <span className="custom-label">
            {walkthrough ? "Recorded walkthrough" : "Custom Input"}
          </span>
        )}
      </section>

      {walkthrough ? (
        <p className="walkthrough-notice" role="status">
          Illustrative recorded run — no live inference on this website.
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
                : assessmentState === "running" || reasoningState === "running"
                  ? walkthrough
                    ? "Loading Recorded Run…"
                    : "Assessing Evidence…"
                  : walkthrough
                    ? "Inspect Recorded Run"
                    : "Decompose Claim"}
          </button>
        </form>
        <div className="claim-status" aria-live="polite">
          {walkthrough
            ? decompositionState === "complete"
              ? "Select an atomic claim to inspect its evidence."
              : "Choose a sample."
            : selectedAtomId
            ? "The selected atomic claim is highlighted above."
            : assessmentState === "running"
              ? "Assessing the retrieved evidence."
              : reasoningState === "running"
                ? "Checking applicable symbolic rules."
              : retrievalState === "running"
                ? "Searching the sources."
                : decompositionState === "complete"
                  ? "Select an atomic claim."
                  : "Break the claim into checkable facts."}
        </div>
        {activeError ? (
          <div className="inline-error" role="alert" tabIndex={-1} ref={errorRef}>
            <strong>
              {retrievalError
                ? "Claim ready; evidence retrieval failed."
                : assessmentError
                  ? "Evidence found; assessment failed."
                  : reasoningError
                    ? "Evidence assessed; symbolic reasoning failed."
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
                {selectedAtom.sourceText.trim() !== selectedAtom.text.trim() ? (
                  <p className="atom-rewrite-note">The highlighted phrase was rewritten as a standalone atomic claim.</p>
                ) : null}
                <SupportSummary
                  classification={selectedClassification}
                  audit={selectedEvidenceAudit}
                  state={assessmentState}
                />
                <SymbolicProofPanel
                  atomId={selectedAtom.id}
                  proofs={selectedProofs}
                  state={reasoningState}
                  documents={documents}
                  onSelectPremise={selectSymbolicPremise}
                />
              </div>
            ) : undefined}
          />
        </div>
        <div className="workbench-pane pipeline-pane" data-mobile-active={mobilePanel === "pipeline"}>
          <PipelinePanel
            decompositionState={decompositionState}
            retrievalState={retrievalState}
            assessmentState={assessmentState}
            reasoningState={reasoningState}
            verdictState={verdictState}
            verdict={verdict?.verdict ?? null}
            atomCount={atoms.length}
            evidenceCount={evidenceCount}
            relationCounts={relationCounts}
            symbolicExecutions={reasoning}
            onRetryEvidence={retryEvidence}
            evidencePerAtom={evidencePerAtom}
            onEvidencePerAtomChange={walkthrough ? undefined : changeEvidencePerAtom}
            retrievalMethod={retrievalMethod}
            onRetrievalMethodChange={walkthrough ? undefined : changeRetrievalMethod}
            onRetryAssessment={retryAssessment}
            onRetryReasoning={retryReasoning}
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
            readOnly={walkthrough}
          />
        </div>
      </section>

      {assessmentState === "complete" ? (
        <>
          <ArgumentationGraph
            graph={argumentationGraph}
            selectedAtomId={selectedAtomId}
            onSelectAtom={selectGraphAtom}
            onSelectEvidence={selectGraphEvidence}
            onSelectInference={selectGraphInference}
            obligationStates={obligationStates}
            verdict={verdict}
            verdictState={verdictState}
          />
        </>
      ) : null}

    </main>
  );
}
