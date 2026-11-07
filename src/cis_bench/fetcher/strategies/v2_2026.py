"""CIS WorkBench scraper strategy for Vue.js SPA HTML (2026+).

CIS WorkBench migrated recommendation pages to a Vue.js SPA in early 2026.
Content previously found in server-rendered ``<div id="...-recommendation-data">``
blocks now lives in attributes on Vue web components:

- ``<wb-recommendation-data attribute="description" text="...">`` — text fields
- ``<wb-recommendation-feature-controls :controls="JSON.parse('...')">`` — CIS Controls
- ``<wb-recommendation-mitre-mappings :mappings="JSON.parse('...')">`` — MITRE mapping
- ``<wb-recommendation-artifacts artifacts-json="[...]">`` — legacy attr still served

Two quirks of the new format are handled here:

1. Vue serializes attribute payloads as JavaScript-escaped strings
   (``\\u0022`` for ``"``). The browser's ``JSON.parse`` decodes those
   escapes first; Python's :func:`json.loads` does not decode them outside
   of JSON string contexts, so we decode them ourselves before parsing.
2. The ``:controls`` payload is sometimes serialized as a dict keyed by
   index (``{"0": {...}, "1": {...}}``) instead of a list, and ``ig1/ig2/ig3``
   can be ``null``. Both are normalized so the Pydantic model validates.
"""

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from cis_bench.fetcher.strategies.base import ExtractedRecommendation, ScraperStrategy
from cis_bench.models.benchmark import Artifact, CISControl, MITREMapping
from cis_bench.utils.html_parser import attribute_text
from cis_bench.utils.parsers import WorkbenchParser

_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_JSON_PARSE_RE = re.compile(r"^JSON\.parse\('(.+)'\)$", re.DOTALL)


def _decode_vue_payload(raw: str | None) -> str | None:
    """Unwrap ``JSON.parse('...')`` and decode ``\\uXXXX`` escapes.

    Args:
        raw: The raw attribute value captured from a Vue web component.

    Returns:
        A JSON string suitable for :func:`json.loads`, or ``None`` when
        the input is empty.
    """
    if not raw:
        return None
    stripped = raw.strip()
    match = _JSON_PARSE_RE.search(stripped)
    payload = match.group(1) if match else stripped
    return _UNICODE_ESCAPE_RE.sub(lambda h: chr(int(h.group(1), 16)), payload)


class WorkbenchV2Strategy(ScraperStrategy):
    """Scraper for Vue.js SPA CIS WorkBench HTML (2026+)."""

    # Pydantic field name → wb-recommendation-data ``attribute=`` value.
    _DATA_ATTRIBUTES = {
        "description": "description",
        "rationale": "rationale_statement",
        "impact": "impact_statement",
        "audit": "audit_procedure",
        "remediation": "remediation_procedure",
        "default_value": "default_value",
        "artifact_equation": "artifact_equation",
        "references": "references",
        "additional_info": "notes",
    }

    @property
    def version(self) -> str:
        return "v2_2026_01"

    @property
    def selectors(self) -> dict[str, dict[str, str]]:
        return {
            field: {"tag": "wb-recommendation-data", "attribute": attr}
            for field, attr in self._DATA_ATTRIBUTES.items()
        }

    def is_compatible(self, html: str) -> bool:
        """Detect the Vue SPA signature.

        A page is considered compatible if it contains at least one
        ``wb-recommendation-data`` element for one of the core content
        attributes. Checking multiple attributes makes detection tolerant
        of minor upstream variations.
        """
        soup = BeautifulSoup(html, "html.parser")
        for signature_attr in ("description", "audit_procedure", "rationale_statement"):
            if soup.find("wb-recommendation-data", attrs={"attribute": signature_attr}):
                return True
        return False

    def extract_recommendation(self, html: str) -> ExtractedRecommendation:
        """Extract every field the Pydantic ``Recommendation`` model needs."""
        soup = BeautifulSoup(html, "html.parser")

        text = {
            field: self._data_text(soup, attr_value)
            for field, attr_value in self._DATA_ATTRIBUTES.items()
        }
        profiles_text = self._data_text(soup, "profiles")
        return ExtractedRecommendation(
            assessment_status=self._normalize_status(
                self._data_text(soup, "automated_scoring") or ""
            ),
            profiles=[profiles_text] if profiles_text else [],
            cis_controls=self._extract_cis_controls(soup),
            mitre_mapping=self._extract_mitre(soup),
            nist_controls=WorkbenchParser.parse_nist_controls(text["references"]),
            parent=WorkbenchParser.parse_parent_link(html),
            artifacts=self._extract_artifacts(soup),
            description=text["description"],
            rationale=text["rationale"],
            impact=text["impact"],
            audit=text["audit"],
            remediation=text["remediation"],
            additional_info=text["additional_info"],
            default_value=text["default_value"],
            artifact_equation=text["artifact_equation"],
            references=text["references"],
        )

    def _data_text(self, soup: BeautifulSoup, attribute: str) -> str | None:
        """The text of the ``wb-recommendation-data`` element for one attribute, cleaned."""
        el = soup.find("wb-recommendation-data", attrs={"attribute": attribute})
        return self._clean_text(attribute_text(el, "text") if el else None)

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _normalize_status(text: str) -> str:
        lowered = text.lower()
        if "automated" in lowered:
            return "Automated"
        if "manual" in lowered:
            return "Manual"
        return text if text else "Unknown"

    @staticmethod
    def _parse_vue_json(raw: str | None) -> Any | None:
        decoded = _decode_vue_payload(raw)
        if decoded is None:
            return None
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            return None

    def _extract_cis_controls(self, soup: BeautifulSoup) -> list[CISControl]:
        el = soup.find("wb-recommendation-feature-controls")
        if not el:
            return []

        # Prefer the Vue ``:controls`` attribute; fall back to the pre-2026
        # ``json-controls`` attr so cached HTML still parses.
        parsed = self._parse_vue_json(
            attribute_text(el, ":controls") or attribute_text(el, "controls")
        )
        if parsed is None:
            legacy = attribute_text(el, "json-controls")
            if legacy:
                try:
                    parsed = json.loads(legacy)
                except json.JSONDecodeError:
                    parsed = None

        if isinstance(parsed, dict):
            items: list[Any] = list(parsed.values())
        elif isinstance(parsed, list):
            items = parsed
        else:
            return []

        controls: list[CISControl] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                controls.append(
                    CISControl(
                        version=item["version"],
                        control=item["control"],
                        title=item.get("title", ""),
                        # ig1/ig2/ig3 may be null in WorkBench data; Pydantic requires bool.
                        ig1=bool(item.get("ig1")),
                        ig2=bool(item.get("ig2")),
                        ig3=bool(item.get("ig3")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return controls

    def _extract_mitre(self, soup: BeautifulSoup) -> MITREMapping | None:
        el = soup.find("wb-recommendation-mitre-mappings")
        if not el:
            return None
        parsed = self._parse_vue_json(
            attribute_text(el, ":mappings") or attribute_text(el, "mappings")
        )
        if not isinstance(parsed, dict):
            return None

        # WorkBench uses singular/capitalized keys (``Technique``, ``Tactics``,
        # ``Mitigations``); accept lowercase plural variants too for resilience.
        techniques = parsed.get("Technique") or parsed.get("techniques") or []
        tactics = parsed.get("Tactics") or parsed.get("tactics") or []
        mitigations = parsed.get("Mitigations") or parsed.get("mitigations") or []

        if not (techniques or tactics or mitigations):
            return None
        return MITREMapping(
            techniques=list(techniques),
            tactics=list(tactics),
            mitigations=list(mitigations),
        )

    def _extract_artifacts(self, soup: BeautifulSoup) -> list[Artifact]:
        el = soup.find("wb-recommendation-artifacts")
        if not el:
            return []

        # The legacy ``artifacts-json`` attribute is still served alongside
        # the Vue ``:artifacts`` attribute; prefer it when present.
        legacy = attribute_text(el, "artifacts-json")
        if legacy:
            return WorkbenchParser.parse_artifacts_json(legacy)

        decoded = _decode_vue_payload(attribute_text(el, ":artifacts"))
        if decoded:
            return WorkbenchParser.parse_artifacts_json(decoded)

        return []
