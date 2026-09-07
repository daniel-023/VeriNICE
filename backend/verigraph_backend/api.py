from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator, Deque, Dict
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .claim_decomposition import (
    DecompositionConfigurationError,
    DecompositionOutputError,
    DecompositionProviderError,
    decompose_claim,
)
from .demo_data import demo_case, demo_case_summaries, demo_store
from .embeddings import (
    is_available as embeddings_available,
    warm as warm_embeddings,
)
from .errors import (
    EvidenceRetrievalConfigurationError,
    EvidenceRetrievalError,
    EvidenceRetrievalOutputError,
)
from .evidence_retrieval import retrieve_evidence
from .grounded_evidence_audit import (
    GroundedEvidenceAuditConfigurationError,
    GroundedEvidenceAuditOutputError,
    GroundedEvidenceAuditProviderError,
    audit_grounded_evidence,
)
from .linguistic_analysis import (
    MODEL_ID as LINGUISTICS_MODEL_ID,
    LinguisticAnalysisConfigurationError,
    LinguisticAnalysisError,
    analyze_linguistics,
    is_available as linguistics_available,
    warm as warm_linguistics,
)
from .symbolic_reasoning import (
    SymbolicReasoningConfigurationError,
    SymbolicReasoningOutputError,
    SymbolicReasoningProviderError,
    reason_symbolically,
)
from .verdict_aggregation import aggregate_verdict
from .schemas import (
    DecompositionRequest,
    DecompositionResponse,
    DemoCase,
    DemoCaseSummary,
    EvidenceRetrievalResponse,
    HealthResponse,
    LinguisticAnalysisRequest,
    LinguisticAnalysisResponse,
    RetrievalDocument,
    RetrievalRequest,
    EvidenceAssessmentRequest,
    EvidenceAssessmentResponse,
    ReasoningRequest,
    ReasoningResponse,
    VerdictAggregationRequest,
    VerdictAggregationResult,
)
from .settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    demo_store()
    loop = asyncio.get_running_loop()
    # Keep heavyweight model imports sequential. spaCy, PyTorch, and
    # Transformers can contend for Python/native loader locks when warmed in
    # parallel, leaving Uvicorn apparently stuck before it serves health.
    try:
        linguistic_result = await loop.run_in_executor(
            _linguistics_worker, warm_linguistics
        )
    except Exception as error:  # optional sidecar must not block startup
        linguistic_result = error
    if isinstance(linguistic_result, Exception):
        logging.getLogger(__name__).warning(
            "Optional linguistic analysis is unavailable; run launcher setup to install it."
        )
    # Let the app become ready while the content-free BGE warm-up completes in
    # the background. Retrieval remains serialized and waits on the model lock
    # if a request arrives during this short window.
    retrieval_warmup = loop.run_in_executor(_retrieval_worker, warm_embeddings)

    def report_retrieval_warmup(result: asyncio.Future[None]) -> None:
        if result.cancelled():
            return
        if result.exception() is not None:
            logging.getLogger(__name__).warning(
                "Evidence retrieval is unavailable; run ./run-verigraph --prepare."
            )

    retrieval_warmup.add_done_callback(report_retrieval_warmup)
    yield


app = FastAPI(
    title="VeriTrace API",
    version="0.7.0",
    description="Claim decomposition, evidence retrieval, evidence assessment, symbolic reasoning, and linguistic inspection.",
    lifespan=lifespan,
)
if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


_llm_slots = asyncio.Semaphore(max(1, settings.max_llm_concurrency))
_retrieval_slots = asyncio.Semaphore(max(1, settings.max_retrieval_concurrency))
_retrieval_worker = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="verigraph-retrieval",
)
_linguistics_slots = asyncio.Semaphore(1)
_linguistics_worker = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="verigraph-linguistics",
)
_rate_windows: Dict[str, Deque[float]] = defaultdict(deque)


def ollama_model_ready() -> bool:
    """Confirm that the configured Ollama service and model are actually usable."""
    if not settings.ollama_url.strip() or not settings.ollama_model.strip():
        return False
    try:
        with urlopen(f"{settings.ollama_url.rstrip('/')}/api/tags", timeout=0.5) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False
    return any(
        isinstance(item, dict) and item.get("name") == settings.ollama_model
        for item in payload.get("models", [])
    )


@app.middleware("http")
async def protect_public_endpoints(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_request_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})

    if (
        settings.rate_limit_per_minute > 0
        and request.method == "POST"
        and request.url.path
        in {
            "/api/v1/decompose",
            "/api/v1/retrieve",
            "/api/v1/assess-evidence",
            "/api/v1/reason",
            "/api/v1/analyze-linguistics",
            "/api/v1/aggregate-verdict",
        }
    ):
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = _rate_windows[client]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many verification requests. Please wait and retry."},
            )
        window.append(now)
    return await call_next(request)


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    decomposition = bool(settings.ollama_url.strip() and settings.ollama_model.strip())
    decomposition_ready = ollama_model_ready()
    retrieval = embeddings_available()
    linguistics = linguistics_available()
    return HealthResponse(
        status=("ready" if decomposition_ready and retrieval
                else "degraded" if decomposition or retrieval
                else "unconfigured"),
        decomposition_configured=decomposition,
        decomposition_ready=decomposition_ready,
        retrieval_configured=retrieval,
        linguistics_configured=linguistics,
        decomposition_model=settings.ollama_model,
        retrieval_model=settings.embedding_model,
        linguistics_model=LINGUISTICS_MODEL_ID,
    )


@app.get("/api/v1/demo-cases", response_model=list[DemoCaseSummary])
def list_demo_cases() -> list[DemoCaseSummary]:
    return demo_case_summaries()


@app.get("/api/v1/demo-cases/{case_id}", response_model=DemoCase)
def get_demo_case(case_id: str) -> DemoCase:
    case = demo_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Demo case not found.")
    return case


@app.post("/api/v1/decompose", response_model=DecompositionResponse)
async def decompose(request: DecompositionRequest) -> DecompositionResponse:
    try:
        async with _llm_slots:
            return await decompose_claim(request.claim)
    except DecompositionConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (DecompositionProviderError, DecompositionOutputError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/v1/retrieve", response_model=EvidenceRetrievalResponse)
async def retrieve(request: RetrievalRequest) -> EvidenceRetrievalResponse:
    prepared_cache_key = None
    if request.case_id is not None:
        case = demo_case(request.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Demo case not found.")
        documents = [
            RetrievalDocument(id=document.id, text=document.text)
            for document in case.documents
        ]
        prepared_cache_key = case.id
    else:
        documents = request.documents or []
    try:
        async with _retrieval_slots:
            return await retrieve_evidence(
                documents,
                request.atoms,
                prepared_cache_key=prepared_cache_key,
                evidence_per_atom=request.evidence_per_atom,
                retrieval_method=request.retrieval_method,
            )
    except EvidenceRetrievalConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except EvidenceRetrievalOutputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except EvidenceRetrievalError as error:
        raise HTTPException(
            status_code=500,
            detail="Semantic evidence matching failed. Please retry.",
        ) from error


@app.post(
    "/api/v1/assess-evidence",
    response_model=EvidenceAssessmentResponse,
)
async def assess_candidate_evidence(
    request: EvidenceAssessmentRequest,
) -> EvidenceAssessmentResponse:
    if request.case_id is not None:
        case = demo_case(request.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Demo case not found.")
        documents = case.documents
    else:
        documents = request.documents or []
    try:
        async with _llm_slots:
            assessment = await audit_grounded_evidence(
                request.claim,
                request.atoms,
                request.evidence,
                documents,
            )
        return EvidenceAssessmentResponse(
            assessment=assessment,
            model=settings.ollama_model,
        )
    except GroundedEvidenceAuditConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (GroundedEvidenceAuditProviderError, GroundedEvidenceAuditOutputError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Evidence assessment failed. Please retry.",
        ) from error


@app.post("/api/v1/reason", response_model=ReasoningResponse)
async def compile_and_execute_reasoning(request: ReasoningRequest) -> ReasoningResponse:
    if request.case_id is not None:
        case = demo_case(request.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Demo case not found.")
        documents = [RetrievalDocument(id=item.id, text=item.text) for item in case.documents]
    else:
        documents = request.documents or []
    try:
        async with _llm_slots:
            return await reason_symbolically(
                request.atoms, request.evidence, documents, request.assessment
            )
    except SymbolicReasoningConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (SymbolicReasoningProviderError, SymbolicReasoningOutputError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Local symbolic execution failed. Please retry.",
        ) from error


@app.post("/api/v1/analyze-linguistics", response_model=LinguisticAnalysisResponse)
async def analyze_linguistic_structure(
    request: LinguisticAnalysisRequest,
) -> LinguisticAnalysisResponse:
    try:
        async with _linguistics_slots:
            return await asyncio.get_running_loop().run_in_executor(
                _linguistics_worker,
                analyze_linguistics,
                request.claim_text,
                request.composition,
                request.atoms,
            )
    except LinguisticAnalysisConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LinguisticAnalysisError as error:
        raise HTTPException(
            status_code=500,
            detail="Local linguistic analysis failed. Please retry.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Local linguistic analysis failed. Please retry.",
        ) from error


@app.post("/api/v1/aggregate-verdict", response_model=VerdictAggregationResult)
def aggregate_case_verdict(request: VerdictAggregationRequest) -> VerdictAggregationResult:
    try:
        return aggregate_verdict(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
