from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from verigraph_backend import api
from verigraph_backend.errors import EvidenceRetrievalConfigurationError, EvidenceRetrievalError
from verigraph_backend.schemas import (
    AtomEvidence, DecomposedAtom, DecompositionResponse, DemoCase, DemoDocument,
    EvidenceRetrievalResponse, EvidenceSpan,
    GroundedEvidenceAssessment, GroundedObligationAudit,
    MaterialOmissionCertificate, ReasoningResponse, ReferenceLabel,
)


client = TestClient(api.app)
SAMPLE = DemoCase(
    id="sample-1", claim="A sample claim.", label=ReferenceLabel.supported,
    documents=[DemoDocument(id="doc-1", title="Sample source", url="https://example.test/source", text="A sample evidence sentence.")],
)


@pytest.fixture(autouse=True)
def stub_catalog(monkeypatch):
    monkeypatch.setattr(api, "demo_case_summaries", lambda: [SAMPLE.summary()])
    monkeypatch.setattr(api, "demo_case", lambda case_id: SAMPLE if case_id == SAMPLE.id else None)


def assessment(atom_id="atom-1", span_id="s1") -> GroundedEvidenceAssessment:
    return GroundedEvidenceAssessment(
        obligations=[GroundedObligationAudit(atom_id=atom_id, support_span_ids=[span_id], sufficiency="SUFFICIENT", reason="Grounded.")],
        material_omission=MaterialOmissionCertificate(),
    )


def evidence_payload():
    return [{"atomId": "atom-1", "spans": [{"id": "s1", "documentId": "doc-1", "text": "Evidence.", "start": 0, "end": 9}]}]


def test_health_and_demo_case_contracts(monkeypatch) -> None:
    monkeypatch.setattr(api, "ollama_model_ready", lambda: True)
    monkeypatch.setattr(api, "embeddings_available", lambda: True)
    monkeypatch.setattr(api, "linguistics_available", lambda: True)
    payload = client.get("/api/v1/health").json()
    assert payload["status"] == "ready"
    assert "nliConfigured" not in payload
    assert "nliModel" not in payload
    assert client.get("/api/v1/demo-cases").status_code == 200
    assert client.get("/api/v1/demo-cases/sample-1").json()["documents"][0]["text"]
    assert client.get("/api/v1/demo-cases/missing").status_code == 404


def test_old_support_route_is_removed() -> None:
    assert client.post("/api/v1/classify-support", json={}).status_code == 404
    assert "/api/v1/classify-support" not in client.get("/openapi.json").json()["paths"]


def test_decomposition_validation_and_success(monkeypatch) -> None:
    assert client.post("/api/v1/decompose", json={"claim": "   "}).status_code == 422

    async def success(claim: str):
        return DecompositionResponse(composition="SINGLE", atoms=[DecomposedAtom(id="atom-1", text=claim, source_text=claim, start=0, end=len(claim), role="CORE")], model="test")

    monkeypatch.setattr(api, "decompose_claim", success)
    assert client.post("/api/v1/decompose", json={"claim": "A claim."}).status_code == 200


def test_retrieval_modes_budget_and_errors(monkeypatch) -> None:
    seen = {}

    async def success(documents, atoms, prepared_cache_key=None, evidence_per_atom=6, retrieval_method="HYBRID"):
        seen["method"] = retrieval_method
        return EvidenceRetrievalResponse(evidence=[AtomEvidence(atom_id=atoms[0].id, spans=[EvidenceSpan(id="s1", document_id=documents[0].id, text=documents[0].text, start=0, end=len(documents[0].text))])], model="test-bge", retrieval_method=retrieval_method)

    monkeypatch.setattr(api, "retrieve_evidence", success)
    atom = {"id": "atom-1", "text": "A fact."}
    assert client.post("/api/v1/retrieve", json={"atoms": [atom]}).status_code == 422
    assert client.post("/api/v1/retrieve", json={"caseId": SAMPLE.id, "atoms": [atom]}).status_code == 200
    response = client.post("/api/v1/retrieve", json={"caseId": SAMPLE.id, "atoms": [atom], "retrievalMethod": "SEMANTIC"})
    assert response.status_code == 200
    assert response.json()["retrievalMethod"] == "SEMANTIC"
    assert seen["method"] == "SEMANTIC"
    assert client.post("/api/v1/retrieve", json={"caseId": SAMPLE.id, "atoms": [atom], "retrievalMethod": "UNKNOWN"}).status_code == 422
    assert client.post("/api/v1/retrieve", json={"documents": [{"id": "d", "text": "Text."}], "atoms": [atom], "evidencePerAtom": 13}).status_code == 422

    async def unavailable(*_args, **_kwargs):
        raise EvidenceRetrievalConfigurationError("Prepare BGE.")

    monkeypatch.setattr(api, "retrieve_evidence", unavailable)
    assert client.post("/api/v1/retrieve", json={"caseId": SAMPLE.id, "atoms": [atom]}).status_code == 503


def test_assessment_requires_claim_and_exact_atom_coverage(monkeypatch) -> None:
    endpoint = "/api/v1/assess-evidence"
    atom = {"id": "atom-1", "text": "A fact."}
    assert client.post(endpoint, json={"atoms": [atom], "evidence": evidence_payload()}).status_code == 422
    assert client.post(endpoint, json={"claim": "Claim.", "atoms": [atom, atom], "evidence": evidence_payload()}).status_code == 422

    async def success(claim, atoms, evidence, documents):
        return assessment(atoms[0].id)

    monkeypatch.setattr(api, "audit_grounded_evidence", success)
    response = client.post(endpoint, json={"claim": "Claim.", "atoms": [atom], "evidence": evidence_payload(), "caseId": SAMPLE.id})
    assert response.status_code == 200
    assert response.json()["provider"] == "ollama"
    assert "claimPosition" not in response.json()["assessment"]


@pytest.mark.parametrize("error,status", [
    (api.GroundedEvidenceAuditConfigurationError("Configure Ollama."), 503),
    (api.GroundedEvidenceAuditProviderError("Provider failed."), 502),
    (api.GroundedEvidenceAuditOutputError("Malformed."), 502),
])
def test_assessment_error_contracts(monkeypatch, error, status) -> None:
    async def failure(*_args):
        raise error
    monkeypatch.setattr(api, "audit_grounded_evidence", failure)
    response = client.post("/api/v1/assess-evidence", json={"claim": "Claim.", "atoms": [{"id": "atom-1", "text": "A fact."}], "evidence": evidence_payload(), "caseId": SAMPLE.id})
    assert response.status_code == status


def test_reason_requires_one_source_mode_and_returns_executions(monkeypatch) -> None:
    atom = {"id": "atom-1", "text": "A fact."}
    base = {"claim": "Claim.", "atoms": [atom], "evidence": evidence_payload(), "assessment": assessment().model_dump(by_alias=True)}
    assert client.post("/api/v1/reason", json=base).status_code == 422
    assert client.post("/api/v1/reason", json={**base, "caseId": SAMPLE.id, "documents": [{"id": "d", "text": "x"}]}).status_code == 422

    async def success(atoms, evidence, documents, assessment):
        return ReasoningResponse(executions=[], model="test-qwen")

    monkeypatch.setattr(api, "reason_symbolically", success)
    response = client.post("/api/v1/reason", json={**base, "caseId": SAMPLE.id})
    assert response.status_code == 200
    assert response.json() == {"executions": [], "provider": "ollama+python", "model": "test-qwen"}
    assert client.post("/api/v1/reason", json={**base, "caseId": "missing"}).status_code == 404


def test_no_deberta_schema_or_route_remains() -> None:
    openapi = client.get("/openapi.json").text.lower()
    assert "deberta" not in openapi
    assert '"nli' not in openapi
