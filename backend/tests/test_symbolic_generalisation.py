import pytest

from verinice_backend.schemas import PipelineAtom, SymbolicPremise
from verinice_backend.symbolic_reasoning.operators import (
    execute_attribute_compare,
    execute_count_distinct,
    execute_extremum_compare,
    execute_numeric_compare,
    execute_set_membership,
    execute_temporal_compare,
)


def premise(text, kind="EVIDENCE", premise_id="p1", content_hash=None):
    return SymbolicPremise(
        id=premise_id,
        document_id="d1",
        text=text,
        start=0,
        end=len(text),
        kind=kind,
        content_hash=content_hash,
    )


@pytest.mark.parametrize(("claim", "premises", "status"), [
    ("Delta is included in the official register.", [premise("Delta", "LIST_ITEM")], "PROVED"),
    ("Delta is not included in the official register.", [premise("Delta", "LIST_ITEM")], "DISPROVED"),
    ("Delta is not included in the official register.", [premise("Complete register", "LIST_CERTIFICATE", content_hash="h")], "PROVED"),
    ("Delta is included in the official register.", [premise("Complete register", "LIST_CERTIFICATE", content_hash="h")], "DISPROVED"),
    ("Delta is included in the official register.", [premise("Delta Alliance", "LIST_ITEM")], "UNRESOLVED"),
    ("Delta is included in the official register.", [], "UNRESOLVED"),
])
def test_set_membership_cross_domain(claim, premises, status):
    assert execute_set_membership(PipelineAtom(id="a", text=claim), premises)["status"].value == status


@pytest.mark.parametrize(("claim", "evidence", "status"), [
    ("Orion served more than 20 percent of users.", "Orion served 25 percent of users.", "PROVED"),
    ("Orion raised at most $2 million.", "Orion raised $3 million.", "DISPROVED"),
    ("Orion served more than 20 percent of users.", "Orion served 25 percentage points of users.", "UNRESOLVED"),
    ("Orion served more than 20 users.", "Lyra served 25 users.", "UNRESOLVED"),
    ("The levy was more than 20 percent in 2020.", "The levy was 25 percent in 2021.", "UNRESOLVED"),
    ("Orion served more than 20 percent of users.", "Orion estimates were 15 percent and 25 percent.", "UNRESOLVED"),
])
def test_numeric_comparison_cross_domain(claim, evidence, status):
    result = execute_numeric_compare(PipelineAtom(id="a", text=claim), [premise(evidence)])
    assert result["status"].value == status


@pytest.mark.parametrize(("claim", "evidence", "status"), [
    ("The launch happened after March 3, 2020.", ["The launch happened on March 4, 2020."], "PROVED"),
    ("The launch happened before March 3, 2020.", ["The launch happened on March 4, 2020."], "DISPROVED"),
    ("The launch happened after March 2020.", ["The launch happened in 2020."], "UNRESOLVED"),
    ("The launch happened after last year.", ["The launch happened in 2020."], "UNRESOLVED"),
    ("Orion launched before Lyra.", ["Orion launched in 2020.", "Lyra launched in 2021."], "PROVED"),
    ("Orion launched before Lyra.", ["Orion was discussed in 2020.", "Lyra was discussed in 2021."], "UNRESOLVED"),
])
def test_temporal_comparison_cross_domain(claim, evidence, status):
    result = execute_temporal_compare(
        PipelineAtom(id="a", text=claim),
        [premise(text, premise_id=f"p{index}") for index, text in enumerate(evidence)],
    )
    assert result["status"].value == status


@pytest.mark.parametrize(("claim", "evidence", "status"), [
    ("The Meridian Award for 1979 was awarded to Abdus Salam.", "Abdus Salam was awarded the 1979 Meridian Award.", "PROVED"),
    ("Abdus Salam received the Meridian Award for chemistry.", "Abdus Salam received the Meridian Award for electroweak theory.", "DISPROVED"),
    ("The Atomium is located in Germany.", "The Atomium is located in Brussels, Belgium.", "DISPROVED"),
    ("Aurora was developed exclusively for civilian navigation.", "Aurora serves military and civilian users.", "UNRESOLVED"),
    ("Aurora was developed exclusively for civilian navigation.", "Aurora was developed for military navigation.", "DISPROVED"),
    ("Comet has a striped surface.", "Comet does not have a striped surface.", "DISPROVED"),
    ("Ada is a physician.", "Ada is a physician and is not a lawyer.", "UNRESOLVED"),
])
def test_attribute_comparison_cross_domain(claim, evidence, status):
    result = execute_attribute_compare(PipelineAtom(id="a", text=claim), [premise(evidence)])
    assert result["status"].value == status


@pytest.mark.parametrize(("claim", "evidence", "status"), [
    ("Archive Z contains at least two different file formats.", ["Archive Z file format: CSV.", "Archive Z file format: JSON."], "PROVED"),
    ("Archive Z contains at least two different file formats.", ["Archive Z file format: CSV."], "UNRESOLVED"),
    ("Archive Z contains two different file formats.", ["Archive Z file format: CSV.", "Archive Z file format: JSON."], "UNRESOLVED"),
    ("Archive Z contains at least two different file formats.", ["Archive Z file format: CSV.", "Archive Z file format: JSON."], "PROVED"),
    ("Device Q supports at least two distinct protocols.", ["Device Q supports MQTT.", "Device Q supports AMQP."], "PROVED"),
    ("Service R offers at least three distinct languages.", ["Service R language: English.", "Service R language: French.", "Service R language: Welsh."], "PROVED"),
    ("Service R offers at least three distinct languages.", ["Service R language: English.", "Service R language: French."], "UNRESOLVED"),
    ("Archive Z contains exactly two different file formats.", ["Archive Z file format: CSV.", "Archive Z file format: JSON."], "UNRESOLVED"),
    ("Archive Z contains at least two different file formats.", ["Archive Y file format: CSV.", "Archive Y file format: JSON."], "UNRESOLVED"),
    ("Package T includes at least two formats.", ["Package T includes XML and YAML."], "PROVED"),
    ("Package T includes at least two formats.", ["Package T includes XML."], "UNRESOLVED"),
])
def test_distinct_value_count_cross_domain(claim, evidence, status):
    result = execute_count_distinct(
        PipelineAtom(id="a", text=claim),
        [premise(text, premise_id=f"p{index}") for index, text in enumerate(evidence)],
    )
    assert result["status"].value == status


@pytest.mark.parametrize(("claim", "evidence", "status"), [
    ("Alpha is the largest city by population.", ["Alpha population 100.", "Beta population 200."], "DISPROVED"),
    ("Alpha is the smallest city by population.", ["Alpha population 100.", "Beta population 50."], "DISPROVED"),
    ("Alpha is the largest city by population.", ["Alpha population 200.", "Beta population 100."], "UNRESOLVED"),
    ("Peak Alpha is the tallest mountain.", ["Peak Alpha is 8,000 metres above sea level.", "Peak Beta is 9,000 metres base to summit."], "UNRESOLVED"),
    ("Alpha is the largest city by population.", ["Beta population 200."], "UNRESOLVED"),
    ("Alpha is the least populous city.", ["Alpha population 100.", "Beta population 90."], "DISPROVED"),
])
def test_extremum_comparison_cross_domain(claim, evidence, status):
    result = execute_extremum_compare(
        PipelineAtom(id="a", text=claim),
        [premise(text, premise_id=f"p{index}") for index, text in enumerate(evidence)],
    )
    assert result["status"].value == status
