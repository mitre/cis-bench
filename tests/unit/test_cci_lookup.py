"""The CIS safeguard -> CCI lookup and its NIST coverage, read from the mapping file."""

import json

import pytest

from cis_bench.utils.cci_lookup import CCILookupService


def _cci(cci, nist):
    return {"cci": cci, "confidence": 0.9, "reasoning": "fits", "nist_control": nist}


# Our own entries in the mapping file's shape.
ENTRIES = [
    {
        "cis_id": "1.1",
        "cis_title": "Keep an inventory",
        "primary_cci": _cci("CCI-000001", "CM-8 a 1"),
        "supporting_ccis": [_cci("CCI-000002", "CM-8 (1)")],
        "nist_control": "CM-8 a 1",
        "mapping_status": "OFFICIAL",
    },
    {
        "cis_id": "18.3",
        "cis_title": "Fix test findings",
        "primary_cci": _cci("CCI-000003", "RA-5 d"),
        "supporting_ccis": [],
        "nist_control": "RA-5 d",
        "mapping_status": "INFERRED",
    },
    {
        "cis_id": "3.12",
        "cis_title": "Segment processing",
        "supporting_ccis": [],
        "nist_control": None,
        "mapping_status": "UNMAPPED",
    },
]


@pytest.fixture
def service(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(ENTRIES))
    return CCILookupService(path)


def test_an_official_safeguard_gives_its_primary_then_supporting_ccis(service):
    found = service.get_ccis_for_cis_control("1.1", extract="all")

    assert [(m.cci, m.nist_control) for m in found] == [
        ("CCI-000001", "CM-8 a 1"),
        ("CCI-000002", "CM-8 (1)"),
    ]
    assert [m.cci for m in service.get_ccis_for_cis_control("1.1", extract="primary")] == [
        "CCI-000001"
    ]


@pytest.mark.parametrize("cis_id", ["18.3", "3.12", "99.9"])
def test_an_inferred_unmapped_or_unknown_safeguard_gives_no_cci(service, cis_id):
    assert service.get_ccis_for_cis_control(cis_id, extract="all") == []


def test_only_official_ccis_cover_nist_controls(service):
    ccis, uncovered = service.deduplicate_nist_controls(
        ["1.1", "18.3"], ["CM-8", "CM-8(3)", "RA-5", "PM-5"], extract="all"
    )

    assert ccis == ["CCI-000001", "CCI-000002"]
    # CM-8 a 1 and CM-8 (1) cover the CM-8 family; the inferred RA-5 d covers nothing.
    assert uncovered == ["RA-5", "PM-5"]


@pytest.mark.parametrize(
    ("index", "base"),
    [
        ("CM-8 a 1", "CM-8"),
        ("CA-8 (1)", "CA-8"),
        ("SC-7 (4) (b)", "SC-7"),
        ("SR-1 a 1 (a)", "SR-1"),
        ("CM-7.1", "CM-7"),
        ("CM-7(5)", "CM-7"),
        ("CM-7.1(5)", "CM-7"),
        ("CM-7", "CM-7"),
        ("  ac-2 ", "AC-2"),
    ],
)
def test_the_base_control_of_any_nist_index(index, base):
    assert CCILookupService.base_nist_control(index) == base


def test_an_official_cci_without_its_nist_control_is_refused(tmp_path):
    broken = [{**ENTRIES[0], "supporting_ccis": [{"cci": "CCI-000002", "confidence": 0.9}]}]
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(broken))

    with pytest.raises(ValueError, match="1.1"):
        CCILookupService(path)


def test_an_unknown_extract_is_refused(service):
    with pytest.raises(ValueError, match="extract"):
        service.get_ccis_for_cis_control("1.1", extract="supporting")
