"""Tests for WorkbenchV2Strategy (Vue.js SPA era, 2026+).

Covers the four failure modes that broke the scraper after the
CIS WorkBench Vue migration:

1. ``is_compatible`` must match the new ``wb-recommendation-data`` format.
2. ``\\uXXXX`` escapes in ``JSON.parse('...')`` payloads must be decoded.
3. ``:controls`` JSON can be either a list or a dict keyed by index, and
   ``ig1/ig2/ig3`` may be ``null``.
4. MITRE mappings now live on ``wb-recommendation-mitre-mappings`` with
   capitalized singular/plural keys (``Technique``/``Tactics``/``Mitigations``).
"""

import pytest

from cis_bench.fetcher.strategies.detector import StrategyDetector
from cis_bench.fetcher.strategies.v1_current import WorkbenchV1Strategy
from cis_bench.fetcher.strategies.v2_2026 import WorkbenchV2Strategy, _decode_vue_payload
from cis_bench.models.benchmark import CISControl, MITREMapping, Recommendation


def _js_escape(s: str) -> str:
    """Encode a string the way Vue does when serializing to an attribute value."""
    return "".join(f"\\u{ord(c):04x}" if c in ('"', "\\", "'") else c for c in s)


def _vue_json_attr(value: object) -> str:
    """Build a ``JSON.parse('...')`` wrapper with ``\\uXXXX``-escaped quotes."""
    import json as _json

    return f"JSON.parse('{_js_escape(_json.dumps(value))}')"


@pytest.fixture
def v2_full_html():
    """Complete V2 HTML with every field the scraper reads populated."""
    controls_payload = _vue_json_attr(
        {
            "0": {
                "title": "Collect Detailed Audit Logs",
                "control": "8.5",
                "version": 8,
                "ig1": False,
                "ig2": True,
                "ig3": True,
            },
            "1": {
                "title": "Establish Access Controls",
                "control": "6.8",
                "version": 8,
                # ig1 intentionally null — must be coerced to False.
                "ig1": None,
                "ig2": True,
                "ig3": True,
            },
        }
    )
    mitre_payload = _vue_json_attr(
        {
            "Technique": ["T1078.004"],
            "Tactics": ["TA0001", "TA0004"],
            "Mitigations": ["M1026"],
        }
    )
    return f"""
    <!DOCTYPE html>
    <html>
    <body>
      <wb-recommendation-data attribute="description"
        text="Audit /usr/bin/containerd-shim if applicable."></wb-recommendation-data>
      <wb-recommendation-data attribute="rationale_statement"
        text="Auditing the containerd shim is important."></wb-recommendation-data>
      <wb-recommendation-data attribute="impact_statement"
        text="Audit logs will grow quickly."></wb-recommendation-data>
      <wb-recommendation-data attribute="audit_procedure"
        text="Run auditctl -l and grep for the binary."></wb-recommendation-data>
      <wb-recommendation-data attribute="remediation_procedure"
        text="Add an audit rule for /usr/bin/containerd-shim."></wb-recommendation-data>
      <wb-recommendation-data attribute="default_value"
        text="Not audited by default."></wb-recommendation-data>
      <wb-recommendation-data attribute="artifact_equation"
        text="OR(1,2)"></wb-recommendation-data>
      <wb-recommendation-data attribute="references"
        text="NIST SP 800-53 Rev. 5: AU-2, SI-3"></wb-recommendation-data>
      <wb-recommendation-data attribute="notes"
        text="Applies only to Docker hosts."></wb-recommendation-data>
      <wb-recommendation-data attribute="automated_scoring"
        text="Automated"></wb-recommendation-data>
      <wb-recommendation-data attribute="profiles"
        text="Level 2 - Docker - Linux"></wb-recommendation-data>

      <wb-recommendation-feature-controls
        title="CIS Controls"
        :controls="{controls_payload}">
      </wb-recommendation-feature-controls>

      <wb-recommendation-mitre-mappings
        :mappings="{mitre_payload}">
      </wb-recommendation-mitre-mappings>

      <wb-recommendation-artifacts
        artifacts-json='[{{"id": 1, "view_level": "1.1.1", "title": "Artifact",
        "status": "published", "artifact_type": {{"id": 1, "name": "Command"}}}}]'>
      </wb-recommendation-artifacts>
    </body>
    </html>
    """


@pytest.fixture
def v2_minimal_html():
    """Minimal V2 HTML — only the signature element is present."""
    return """
    <wb-recommendation-data attribute="description" text="Just a description."></wb-recommendation-data>
    """


@pytest.fixture
def v2_controls_as_list_html():
    """V2 HTML where :controls is serialized as a list (not a dict)."""
    payload = _vue_json_attr(
        [
            {
                "title": "Only Control",
                "control": "1.1",
                "version": 8,
                "ig1": True,
                "ig2": True,
                "ig3": True,
            }
        ]
    )
    return f"""
    <wb-recommendation-data attribute="description" text="x"></wb-recommendation-data>
    <wb-recommendation-feature-controls :controls="{payload}">
    </wb-recommendation-feature-controls>
    """


@pytest.fixture
def clear_detector():
    """Ensure each test starts with a clean detector registry."""
    original = list(StrategyDetector._strategies)
    StrategyDetector.clear_strategies()
    yield
    StrategyDetector.clear_strategies()
    for strategy in reversed(original):
        StrategyDetector.register_strategy(strategy, position=0)


# ============ Compatibility Detection ============


class TestV2IsCompatible:
    def test_matches_v2_signature(self, v2_minimal_html):
        assert WorkbenchV2Strategy().is_compatible(v2_minimal_html) is True

    def test_rejects_v1_html(self):
        html = '<div id="description-recommendation-data">x</div>'
        assert WorkbenchV2Strategy().is_compatible(html) is False

    def test_rejects_empty_html(self):
        assert WorkbenchV2Strategy().is_compatible("") is False

    def test_matches_on_audit_only(self):
        html = (
            '<wb-recommendation-data attribute="audit_procedure" text="x"></wb-recommendation-data>'
        )
        assert WorkbenchV2Strategy().is_compatible(html) is True


# ============ Vue Payload Decoding ============


class TestDecodeVuePayload:
    def test_unwraps_json_parse_and_decodes_escapes(self):
        raw = r"""JSON.parse('[{\u0022a\u0022:1}]')"""
        assert _decode_vue_payload(raw) == '[{"a":1}]'

    def test_returns_input_when_no_wrapper(self):
        assert _decode_vue_payload('{"a":1}') == '{"a":1}'

    def test_none_passthrough(self):
        assert _decode_vue_payload(None) is None

    def test_empty_string(self):
        assert _decode_vue_payload("") is None


# ============ Field Extraction ============


class TestV2ExtractRecommendation:
    def test_extracts_all_text_fields(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)

        assert data["description"] == "Audit /usr/bin/containerd-shim if applicable."
        assert data["rationale"] == "Auditing the containerd shim is important."
        assert data["impact"] == "Audit logs will grow quickly."
        assert data["audit"] == "Run auditctl -l and grep for the binary."
        assert data["remediation"] == "Add an audit rule for /usr/bin/containerd-shim."
        assert data["default_value"] == "Not audited by default."
        assert data["artifact_equation"] == "OR(1,2)"
        assert data["references"] == "NIST SP 800-53 Rev. 5: AU-2, SI-3"
        assert data["additional_info"] == "Applies only to Docker hosts."

    def test_extracts_assessment_status(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)
        assert data["assessment_status"] == "Automated"

    def test_extracts_profiles_as_list(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)
        assert data["profiles"] == ["Level 2 - Docker - Linux"]

    def test_parses_nist_from_references(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)
        assert "AU-2" in data["nist_controls"]
        assert "SI-3" in data["nist_controls"]

    def test_missing_fields_yield_none(self, v2_minimal_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_minimal_html)
        assert data["description"] == "Just a description."
        assert data["audit"] is None
        assert data["remediation"] is None
        assert data["assessment_status"] == "Unknown"
        assert data["profiles"] == []


# ============ CIS Controls Normalization ============


class TestV2ExtractCisControls:
    def test_dict_payload_becomes_list(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)
        assert len(data["cis_controls"]) == 2
        assert all(isinstance(c, CISControl) for c in data["cis_controls"])

    def test_list_payload_works(self, v2_controls_as_list_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_controls_as_list_html)
        assert len(data["cis_controls"]) == 1
        assert data["cis_controls"][0].control == "1.1"
        assert data["cis_controls"][0].ig1 is True

    def test_null_ig_coerced_to_false(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)
        # Second control has ig1=null in the fixture.
        second = next(c for c in data["cis_controls"] if c.control == "6.8")
        assert second.ig1 is False
        assert second.ig2 is True
        assert second.ig3 is True

    def test_missing_feature_controls_element(self, v2_minimal_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_minimal_html)
        assert data["cis_controls"] == []


# ============ MITRE Mapping ============


class TestV2ExtractMitre:
    def test_parses_mitre_keys(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)
        assert isinstance(data["mitre_mapping"], MITREMapping)
        assert data["mitre_mapping"].techniques == ["T1078.004"]
        assert data["mitre_mapping"].tactics == ["TA0001", "TA0004"]
        assert data["mitre_mapping"].mitigations == ["M1026"]

    def test_missing_mitre_element(self, v2_minimal_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_minimal_html)
        assert data["mitre_mapping"] is None

    def test_empty_mitre_returns_none(self):
        empty = _vue_json_attr({"Technique": [], "Tactics": [], "Mitigations": []})
        html = f"""
        <wb-recommendation-data attribute="description" text="x"></wb-recommendation-data>
        <wb-recommendation-mitre-mappings :mappings="{empty}">
        </wb-recommendation-mitre-mappings>
        """
        data = WorkbenchV2Strategy().extract_recommendation(html)
        assert data["mitre_mapping"] is None


# ============ End-to-End Model Validation ============


class TestV2RecommendationModelValidation:
    """The full dict from V2 must satisfy the Pydantic Recommendation model."""

    def test_builds_valid_recommendation(self, v2_full_html):
        data = WorkbenchV2Strategy().extract_recommendation(v2_full_html)
        rec = Recommendation(
            ref="1.1.15",
            title="Ensure auditing is configured for containerd-shim",
            url="https://workbench.cisecurity.org/sections/1/recommendations/2",
            **data,
        )
        assert rec.assessment_status == "Automated"
        assert len(rec.cis_controls) == 2
        assert rec.mitre_mapping is not None


# ============ Detector Integration ============


class TestV2DetectorIntegration:
    def test_detector_picks_v2_for_vue_html(self, clear_detector, v2_minimal_html):
        StrategyDetector.register_strategy(WorkbenchV1Strategy(), position=0)
        StrategyDetector.register_strategy(WorkbenchV2Strategy(), position=0)

        strategy = StrategyDetector.detect_strategy(v2_minimal_html)
        assert strategy.version == "v2_2026_01"

    def test_detector_still_picks_v1_for_legacy_html(self, clear_detector):
        StrategyDetector.register_strategy(WorkbenchV1Strategy(), position=0)
        StrategyDetector.register_strategy(WorkbenchV2Strategy(), position=0)

        legacy = """
        <div id="description-recommendation-data"><p>x</p></div>
        <div id="rationale_statement-recommendation-data"><p>y</p></div>
        <div id="audit_procedure-recommendation-data"><p>z</p></div>
        """
        strategy = StrategyDetector.detect_strategy(legacy)
        assert strategy.version == "v1_2025_10"
