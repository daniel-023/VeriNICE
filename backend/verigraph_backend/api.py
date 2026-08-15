from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator, Deque, Dict

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
from .linguistic_analysis import (
    MODEL_ID as LINGUISTICS_MODEL_ID,
    LinguisticAnalysisConfigurationError,
    LinguisticAnalysisError,
    analyze_linguistics,
    is_available as linguistics_available,
    warm as warm_linguistics,
)
from .nli_classification import (
    NLIClassificationConfigurationError,
    NLIClassificationError,
    classify_support,
    is_available as nli_available,
    warm as warm_nli,
)
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
    SupportClassificationRequest,
    SupportClassificationResponse,
)
from .settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    demo_store()
    loop = asyncio.get_running_loop()
    linguistic_result, nli_result = await asyncio.gather(
        loop.run_in_executor(_linguistics_worker, warm_linguistics),
        loop.run_in_executor(_nli_worker, warm_nli),
        return_exceptions=True,
    )
    if isinstance(linguistic_result, Exception):
        logging.getLogger(__name__).warning(
            "Optional linguistic analysis is unavailable; run launcher setup to install it."
        )
    if isinstance(nli_result, Exception):
        logging.getLogger(__name__).warning(
            "NLI support classification is unavailable; run ./run-verigraph --prepare."
        )
    # sentence-transformers and transformers share a lazy import surface. Start
    # BGE only after NLI has finished importing transformers, then let the app
    # become ready while the content-free BGE warm-up completes in the
    # background. Retrieval itself remains serialized and waits on the model
    # lock if a request arrives during this short window.
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
    title="VeriGraph API",
    version="0.7.0",
    description="Live claim decomposition, semantic retrieval, local NLI, and linguistic inspection.",
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
_nli_slots = asyncio.Semaphore(1)
_nli_worker = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="verigraph-nli",
)
_rate_windows: Dict[str, Deque[float]] = defaultdict(deque)


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
            "/api/v1/classify-support",
            "/api/v1/analyze-linguistics",
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
    retrieval = embeddings_available()
    nli = nli_available()
    linguistics = linguistics_available()
    return HealthResponse(
        status="configured" if decomposition and retrieval and nli else "unconfigured",
        decomposition_configured=decomposition,
        retrieval_configured=retrieval,
        nli_configured=nli,
        linguistics_configured=linguistics,
        decomposition_model=settings.ollama_model,
        retrieval_model=settings.embedding_model,
        nli_model=settings.nli_model,
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
    "/api/v1/classify-support",
    response_model=SupportClassificationResponse,
)
async def classify_candidate_support(
    request: SupportClassificationRequest,
) -> SupportClassificationResponse:
    try:
        async with _nli_slots:
            return await asyncio.get_running_loop().run_in_executor(
                _nli_worker,
                classify_support,
                request.atoms,
                request.evidence,
            )
    except NLIClassificationConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NLIClassificationError as error:
        raise HTTPException(
            status_code=500,
            detail="Local NLI support classification failed. Please retry.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="Local NLI support classification failed. Please retry.",
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
