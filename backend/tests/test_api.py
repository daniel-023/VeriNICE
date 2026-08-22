from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from verigraph_backend import api
from verigraph_backend.errors import (
    EvidenceRetrievalConfigurationError,
    EvidenceRetrievalError,
    EvidenceRetrievalOutputError,
)
from verigraph_backend.schemas import (
    AtomEvidence,
    DecomposedAtom,
    DecompositionResponse,
    DemoCase,
    DemoDocument,
    EvidenceRetrievalResponse,
    EvidenceSpan,
    AtomLinguisticAnalysis,
    LinguisticAnalysisResponse,
    AtomSupportClassification,
    EvidenceRelation,
    NLIRelation,
    ObligationLinguisticSummary,
    ReferenceLabel,
    SupportClassificationResponse,
)


client = TestClient(api.app)
SAMPLE = DemoCase(
    id="sample-1",
    claim="A sample claim.",
    label=ReferenceLabel.supported,
    documents=[
        DemoDocument(
            id="doc-1",
            title="Sample source",
            url="https://example.test/source",
            text="A sample evidence sentence.",
        )
    ],
)


def linguistic_payload(atoms):
    return {
        "schemaVersion": 2,
        "claimText": " ".join(atom["text"] for atom in atoms),
        "composition": "SINGLE" if len(atoms) == 1 else "AND",
        "atoms": [
            {
                **atom,
                "sourceText": atom["text"],
                "start": 0,
                "end": len(atom["text"]),
                "role": "CORE",
            }
            for atom in atoms
        ],
    }


@pytest.fixture(autouse=True)
def stub_catalog(monkeypatch):
    monkeypatch.setattr(api, "demo_case_summaries", lambda: [SAMPLE.summary()])
    monkeypatch.setattr(
        api,
        "demo_case",
        lambda case_id: SAMPLE if case_id == SAMPLE.id else None,
    )


def test_health_summary_and_detail_contracts(monkeypatch) -> None:
    monkeypatch.setattr(api, "embeddings_available", lambda: True)
    monkeypatch.setattr(api, "nli_available", lambda: True)
    monkeypatch.setattr(api, "linguistics_available", lambda: True)
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "configured",
        "decompositionConfigured": True,
        "retrievalConfigured": True,
        "nliConfigured": True,
        "linguisticsConfigured": True,
        "decompositionModel": api.settings.ollama_model,
        "retrievalModel": api.settings.embedding_model,
        "nliModel": api.settings.nli_model,
        "linguisticsModel": api.LINGUISTICS_MODEL_ID,
    }

    summaries = client.get("/api/v1/demo-cases")
    assert summaries.status_code == 200
    assert "text" not in summaries.json()[0]["documents"][0]
    detail = client.get(f"/api/v1/demo-cases/{SAMPLE.id}")
    assert detail.status_code == 200
    assert detail.json()["documents"][0]["text"] == SAMPLE.documents[0].text
    assert client.get("/api/v1/demo-cases/missing").status_code == 404


def test_optional_linguistics_does_not_change_core_health(monkeypatch) -> None:
    monkeypatch.setattr(api, "embeddings_available", lambda: True)
    monkeypatch.setattr(api, "nli_available", lambda: True)
    monkeypatch.setattr(api, "linguistics_available", lambda: False)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "configured"
    assert response.json()["linguisticsConfigured"] is False


def test_nli_readiness_is_part_of_core_health(monkeypatch) -> None:
    monkeypatch.setattr(api, "embeddings_available", lambda: True)
    monkeypatch.setattr(api, "nli_available", lambda: False)
    monkeypatch.setattr(api, "linguistics_available", lambda: True)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "unconfigured"
    assert response.json()["nliConfigured"] is False


def test_decomposition_input_validation_returns_422() -> None:
    assert client.post("/api/v1/decompose", json={"claim": "   "}).status_code == 422
    assert client.post("/api/v1/decompose", json={"claim": "x" * 5001}).status_code == 422


def test_retrieval_requires_one_mode_unique_ids_and_no_legacy_claim() -> None:
    atom = {"id": "atom-1", "text": "A fact."}
    document = {"id": "doc-1", "text": "A document."}
    assert client.post("/api/v1/retrieve", json={"atoms": [atom]}).status_code == 422
    assert client.post(
        "/api/v1/retrieve",
        json={"caseId": "case", "documents": [document], "atoms": [atom]},
    ).status_code == 422
    assert client.post(
        "/api/v1/retrieve", json={"documents": [document, document], "atoms": [atom]}
    ).status_code == 422
    assert client.post(
        "/api/v1/retrieve", json={"documents": [document], "atoms": [atom, atom]}
    ).status_code == 422
    assert client.post(
        "/api/v1/retrieve",
        json={"documents": [document], "atoms": [atom], "claim": "legacy"},
    ).status_code == 422


def test_decomposition_success_and_provider_failure(monkeypatch) -> None:
    async def success(claim: str):
        return DecompositionResponse(
            composition="SINGLE",
            atoms=[
                DecomposedAtom(
                    id="atom-1",
                    text=claim,
                    source_text=claim,
                    start=0,
                    end=len(claim),
                    role="CORE",
                )
            ],
            model="test-model",
        )

    monkeypatch.setattr(api, "decompose_claim", success)
    response = client.post("/api/v1/decompose", json={"claim": "A claim."})
    assert response.status_code == 200

    async def failure(_: str):
        raise api.DecompositionProviderError("Provider unavailable. Retry.")

    monkeypatch.setattr(api, "decompose_claim", failure)
    assert client.post("/api/v1/decompose", json={"claim": "A claim."}).status_code == 502


def test_custom_and_prepared_retrieval_contracts(monkeypatch) -> None:
    calls = []

    async def success(documents, atoms, prepared_cache_key=None):
        calls.append(prepared_cache_key)
        document = documents[0]
        return EvidenceRetrievalResponse(
            evidence=[
                AtomEvidence(
                    atom_id=atoms[0].id,
                    spans=[
                        EvidenceSpan(
                            id=f"{document.id}::sentence-1",
                            document_id=document.id,
                            text=document.text,
                            start=0,
                            end=len(document.text),
                        )
                    ],
                )
            ],
            model="test-embedding",
        )

    monkeypatch.setattr(api, "retrieve_evidence", success)
    atom = {"id": "atom-1", "text": "A fact."}
    custom = client.post(
        "/api/v1/retrieve",
        json={"documents": [{"id": "doc-custom", "text": "A document."}], "atoms": [atom]},
    )
    assert custom.status_code == 200
    assert custom.json()["provider"] == "sentence-transformers"
    assert calls[0] is None

    prepared = client.post("/api/v1/retrieve", json={"caseId": SAMPLE.id, "atoms": [atom]})
    assert prepared.status_code == 200
    assert calls[1] == SAMPLE.id
    assert client.post(
        "/api/v1/retrieve", json={"caseId": "missing", "atoms": [atom]}
    ).status_code == 404


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (EvidenceRetrievalConfigurationError("Prepare the model."), 503),
        (EvidenceRetrievalOutputError("Invalid document segmentation."), 422),
        (EvidenceRetrievalError("Inference failed."), 500),
    ],
)
def test_retrieval_error_contracts(monkeypatch, error, status) -> None:
    async def failure(documents, atoms, prepared_cache_key=None):
        raise error

    monkeypatch.setattr(api, "retrieve_evidence", failure)
    response = client.post(
        "/api/v1/retrieve",
        json={
            "documents": [{"id": "doc-1", "text": "A document."}],
            "atoms": [{"id": "atom-1", "text": "A fact."}],
        },
    )
    assert response.status_code == status


def test_nli_input_validation() -> None:
    endpoint = "/api/v1/classify-support"
    atom = {"id": "atom-1", "text": "A fact."}
    span = {"id": "sentence-1", "documentId": "doc-1", "text": "Evidence."}
    group = {"atomId": "atom-1", "spans": [span]}
    assert client.post(endpoint, json={"atoms": [], "evidence": []}).status_code == 422
    assert client.post(
        endpoint,
        json={"atoms": [atom, atom], "evidence": [group]},
    ).status_code == 422
    assert client.post(
        endpoint,
        json={"atoms": [atom], "evidence": [{"atomId": "unknown", "spans": [span]}]},
    ).status_code == 422
    assert client.post(
        endpoint,
        json={"atoms": [atom], "evidence": [group, group]},
    ).status_code == 422
    assert client.post(
        endpoint,
        json={
            "atoms": [atom],
            "evidence": [{"atomId": "atom-1", "spans": [span, span]}],
        },
    ).status_code == 422


def test_nli_success_preserves_atom_and_span_order(monkeypatch) -> None:
    def success(atoms, evidence):
        return SupportClassificationResponse(
            classifications=[
                AtomSupportClassification(
                    atom_id=atom.id,
                    relations=[
                        EvidenceRelation(
                            span_id=span.id,
                            document_id=span.document_id,
                            relation=NLIRelation.entailment,
                        )
                        for span in next(
                            item.spans for item in evidence if item.atom_id == atom.id
                        )
                    ],
                )
                for atom in atoms
            ],
            model="test-nli",
        )

    monkeypatch.setattr(api, "classify_support", success)
    response = client.post(
        "/api/v1/classify-support",
        json={
            "atoms": [
                {"id": "atom-2", "text": "Second."},
                {"id": "atom-1", "text": "First."},
            ],
            "evidence": [
                {
                    "atomId": "atom-1",
                    "spans": [
                        {"id": "s2", "documentId": "doc-b", "text": "Second evidence."}
                    ],
                },
                {
                    "atomId": "atom-2",
                    "spans": [
                        {"id": "s1", "documentId": "doc-a", "text": "First evidence."}
                    ],
                },
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "transformers"
    assert [item["atomId"] for item in payload["classifications"]] == [
        "atom-2",
        "atom-1",
    ]
    assert payload["classifications"][0]["relations"][0] == {
        "spanId": "s1",
        "documentId": "doc-a",
        "relation": "ENTAILMENT",
    }
    assert "score" not in response.text.lower()


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (api.NLIClassificationConfigurationError("Prepare the model."), 503),
        (api.NLIClassificationError("Inference failed."), 500),
    ],
)
def test_nli_error_contracts(monkeypatch, error, status) -> None:
    def failure(_atoms, _evidence):
        raise error

    monkeypatch.setattr(api, "classify_support", failure)
    response = client.post(
        "/api/v1/classify-support",
        json={
            "atoms": [{"id": "atom-1", "text": "A fact."}],
            "evidence": [{"atomId": "atom-1", "spans": []}],
        },
    )
    assert response.status_code == status


def test_linguistic_input_validation() -> None:
    endpoint = "/api/v1/analyze-linguistics"
    assert client.post(endpoint, json={"atoms": []}).status_code == 422
    atom = {"id": "atom-1", "text": "A fact."}
    assert client.post(endpoint, json=linguistic_payload([atom, atom])).status_code == 422
    assert client.post(endpoint, json=linguistic_payload([{"id": "x", "text": "   "}])).status_code == 422
    assert client.post(
        endpoint, json=linguistic_payload([{"id": f"atom-{index}", "text": "A fact."} for index in range(13)])
    ).status_code == 422


def test_linguistic_success_preserves_atom_order(monkeypatch) -> None:
    def success(claim_text, composition, atoms):
        analyses = [
            AtomLinguisticAnalysis(
                atom_id=atom.id,
                frames=[],
                cues=[],
                entities=[],
                tokens=[],
                status="partial",
                unresolved=["subject", "predicate"],
            )
            for atom in atoms
        ]
        return LinguisticAnalysisResponse(
            claim_analysis=analyses[0].model_copy(update={"atom_id": "claim"}),
            analyses=analyses,
            summaries=[
                ObligationLinguisticSummary(
                    atom_id=atom.id,
                    analysis_status="partial",
                    role_audit="INCONCLUSIVE",
                )
                for atom in atoms
            ],
            model="test-parser",
        )

    monkeypatch.setattr(api, "analyze_linguistics", success)
    response = client.post(
        "/api/v1/analyze-linguistics",
        json=linguistic_payload([{"id": "atom-2", "text": "Second."}, {"id": "atom-1", "text": "First."}]),
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "spacy"
    assert [item["atomId"] for item in response.json()["analyses"]] == ["atom-2", "atom-1"]


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (api.LinguisticAnalysisConfigurationError("Install the parser."), 503),
        (api.LinguisticAnalysisError("Inference failed."), 500),
    ],
)
def test_linguistic_error_contracts(monkeypatch, error, status) -> None:
    def failure(_claim_text, _composition, _atoms):
        raise error

    monkeypatch.setattr(api, "analyze_linguistics", failure)
    response = client.post(
        "/api/v1/analyze-linguistics",
        json=linguistic_payload([{"id": "atom-1", "text": "A fact."}]),
    )
    assert response.status_code == status
