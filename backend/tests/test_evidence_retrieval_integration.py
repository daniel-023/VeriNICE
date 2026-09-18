from __future__ import annotations

import os

import pytest

from verinice_backend.demo_data import load_prepared_bundle
from verinice_backend.evidence_retrieval import retrieve_evidence
from verinice_backend.schemas import RetrievalAtom, RetrievalDocument
from verinice_backend.settings import ROOT


pytestmark = pytest.mark.skipif(
    os.getenv("VERINICE_RUN_EMBEDDING_INTEGRATION") != "1",
    reason="set VERINICE_RUN_EMBEDDING_INTEGRATION=1 to load the real embedding model",
)


@pytest.mark.parametrize(
    ("case_id", "expected_text"),
    [
        ("averitec-dev-0125", "gross domestic product"),
        ("averitec-dev-0044", "chickenpox parties"),
        ("averitec-dev-0015", "illegal crossings appear to have fallen"),
        ("averitec-dev-0060", "67%"),
    ],
)
async def test_real_bge_model_surfaces_representative_averitec_evidence(
    case_id: str, expected_text: str
) -> None:
    # The default app bundle is the curated showcase. Exercise retrieval against
    # the separately shipped AVeriTeC fixture bundle named by these test cases.
    case = load_prepared_bundle(ROOT / "data" / "demo" / "averitec").case(case_id)
    assert case is not None
    response = await retrieve_evidence(
        [RetrievalDocument(id=document.id, text=document.text) for document in case.documents],
        [RetrievalAtom(id="atom-1", text=case.claim)],
        prepared_cache_key=case.id,
    )
    texts = [span.text.lower() for span in response.evidence[0].spans]
    assert any(expected_text in text for text in texts)
