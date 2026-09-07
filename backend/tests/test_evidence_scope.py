from verigraph_backend.evidence_scope import check_evidence_scope, jurisdictions
from verigraph_backend.schemas import (
    AssessmentAtomEvidence, AssessmentInputSpan, DemoDocument, PipelineAtom,
)


def span(identifier: str, document_id: str, text: str):
    return AssessmentInputSpan(
        id=identifier, document_id=document_id, text=text, start=0, end=len(text)
    )


def test_aliases_countries_subdivisions_and_eu_are_offline_and_deterministic() -> None:
    assert jurisdictions("USA and the U.K.") >= {"US", "GB"}
    assert jurisdictions("New Zealand and the EU") >= {"NZ", "EU"}
    assert "AU" in jurisdictions("Australia")
    assert "CA" in jurisdictions("Ontario")
    assert "CZ" not in jurisdictions("Canberra was Australia's most populous capital city.")


def test_explicit_disjoint_jurisdiction_is_mismatch_but_missing_scope_is_unresolved() -> None:
    atom = PipelineAtom(id="a1", text="Australia has listed the NDF.")
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[
        span("us", "us-doc", "The United States list contains the following organizations."),
        span("unknown", "unknown-doc", "The official list contains the following organizations."),
    ])]
    documents = [
        DemoDocument(id="us-doc", title="United States list", url="https://state.gov/list", text="United States official list. " * 20),
        DemoDocument(id="unknown-doc", title="Official list", url="https://example.org/list", text="Official organization list. " * 20),
    ]
    checks = check_evidence_scope([atom], evidence, documents)["a1"]
    assert checks[0].status == "MISMATCH"
    assert checks[1].status == "UNRESOLVED"


def test_matching_scope_and_geography_free_claim() -> None:
    documents = [DemoDocument(
        id="au", title="Australian legislation", url="https://www.legislation.gov.au/list",
        text="Australia maintains this official list. " * 20,
    )]
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[span("s1", "au", "Australia published the list.")])]
    assert check_evidence_scope(
        [PipelineAtom(id="a1", text="Australia published the list.")], evidence, documents
    )["a1"][0].status == "MATCH"
    assert check_evidence_scope(
        [PipelineAtom(id="a1", text="The organization was listed.")], evidence, documents
    )["a1"][0].status == "NOT_APPLICABLE"


def test_country_heavy_list_without_authoritative_scope_is_unresolved() -> None:
    atom = PipelineAtom(id="a1", text="Australia lists the organization.")
    evidence = [AssessmentAtomEvidence(atom_id="a1", spans=[span("s1", "list", "The organization appears in the list.")])]
    document = DemoDocument(
        id="list", title="Organizations", url="https://example.org/list",
        text="Organizations from Angola, Botswana, Fiji, Ghana, Rwanda and Uganda are listed. " * 5,
    )
    assert check_evidence_scope([atom], evidence, [document])["a1"][0].status == "UNRESOLVED"


def test_location_value_is_not_filtered_as_source_scope() -> None:
    atom = PipelineAtom(id="a1", text="The monument is located in Germany.")
    evidence = [AssessmentAtomEvidence(
        atom_id="a1",
        spans=[span("s1", "fr", "The monument is in Paris, France.")],
    )]
    document = DemoDocument(
        id="fr", title="Official monument site", url="https://example.fr",
        text="The monument is in Paris, France.",
    )
    check = check_evidence_scope([atom], evidence, [document])["a1"][0]
    assert check.status == "NOT_APPLICABLE"
    assert "claimed value" in check.reason
