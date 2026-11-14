"""CCI (Control Correlation Identifier) lookup service.

Maps CIS Controls safeguards to DoD CCIs through the bundled CIS-CCI mapping, and tells
which cited NIST controls a rule's CCIs already state, so only the others are written as
references.
"""

import json
import logging
import re
from dataclasses import dataclass
from gettext import ngettext
from pathlib import Path

logger = logging.getLogger(__name__)

# A NIST SP 800-53 control and its enhancement at the start of an index: "CM-8" and "(3)" in
# "CM-8 (3) (a)"; sub-parts ("a 1", "(b)") and assessment suffixes (".1") are not part of it
_CONTROL_KEY_RE = re.compile(r"([A-Z]{2}-\d+)\s*(?:\((\d+)\))?")


@dataclass
class CCIMapping:
    """A single CCI with its NIST control mapping."""

    cci: str
    nist_control: str | None = None
    confidence: float | None = None


class CCILookupService:
    """Service for looking up CCIs and managing NIST deduplication."""

    def __init__(self, mapping_file: Path | None = None):
        """Initialize CCI lookup service.

        Args:
            mapping_file: Path to cis-cci-mapping.json (defaults to bundled file)
        """
        if mapping_file is None:
            # Use bundled mapping file
            mapping_file = Path(__file__).parent.parent / "data" / "cis-cci-mapping.json"

        logger.debug(f"Initializing CCI lookup service with mapping file: {mapping_file}")

        with open(mapping_file) as f:
            mapping_data = json.load(f)

        logger.debug(
            ngettext(
                "Loaded {count} CCI mapping entry",
                "Loaded {count} CCI mapping entries",
                len(mapping_data),
            ).format(count=len(mapping_data))
        )

        # Each safeguard's CCIs, read once through the one entry reader: only OFFICIAL
        # entries give CCIs (INFERRED and UNMAPPED entries are kept in the file as
        # research data and give none).
        self._ccis_by_safeguard: dict[str, list[CCIMapping]] = {
            entry["cis_id"]: self._official_ccis(entry) for entry in mapping_data
        }
        # Reverse index: CCI -> the NIST control it implements (DISA's Rev 5 index)
        self._cci_to_nist: dict[str, str] = {
            mapping.cci: mapping.nist_control
            for ccis in self._ccis_by_safeguard.values()
            for mapping in ccis
            if mapping.nist_control
        }

    @staticmethod
    def _official_ccis(entry: dict) -> list[CCIMapping]:
        """An entry's CCIs, primary first, then its supporting CCIs; none unless the entry
        is OFFICIAL.

        Raises:
            ValueError: An OFFICIAL entry without a primary CCI, or a CCI without its CCI
                id or NIST control.
        """
        if entry.get("mapping_status") != "OFFICIAL":
            return []
        cis_id = entry.get("cis_id")
        primary = entry.get("primary_cci")
        if not primary:
            raise ValueError(f"safeguard {cis_id}: an OFFICIAL entry needs a primary_cci")
        ccis = []
        for item in [primary, *entry.get("supporting_ccis", [])]:
            if not item.get("cci") or not item.get("nist_control"):
                raise ValueError(
                    f"safeguard {cis_id}: every CCI needs its cci and nist_control: {item!r}"
                )
            ccis.append(
                CCIMapping(
                    cci=item["cci"],
                    nist_control=item["nist_control"],
                    confidence=item.get("confidence"),
                )
            )
        return ccis

    def get_ccis_for_cis_control(
        self, cis_control_id: str, extract: str = "all"
    ) -> list[CCIMapping]:
        """The CCIs of a CIS safeguard: the primary CCI only, or primary and supporting.

        Args:
            cis_control_id: CIS safeguard ID (e.g., "4.8", "10.3")
            extract: "primary" for the primary CCI only, "all" for primary + supporting

        Returns:
            List of CCIMapping objects; empty for a safeguard with no OFFICIAL mapping

        Raises:
            ValueError: extract is neither "primary" nor "all".
        """
        if extract not in ("primary", "all"):
            raise ValueError(f"extract must be 'primary' or 'all', not {extract!r}")
        ccis = self._ccis_by_safeguard.get(cis_control_id, [])
        return ccis[:1] if extract == "primary" else list(ccis)

    def get_nist_controls_covered_by_ccis(self, ccis: list[str]) -> set[str]:
        """The control keys (control and enhancement) the given CCIs sit under.

        Args:
            ccis: List of CCI identifiers

        Returns:
            Set of control keys, e.g. {"CM-7(1)", "SC-7(12)"}
        """
        covered = set()

        for cci in ccis:
            nist_ctrl = self._cci_to_nist.get(cci)
            if nist_ctrl:
                covered.add(self.control_key(nist_ctrl))

        return covered

    def deduplicate_nist_controls(
        self, cis_control_ids: list[str], cited_nist_controls: list[str], extract: str = "all"
    ) -> tuple[list[str], list[str]]:
        """Determine CCIs to add vs NIST references to add.

        Args:
            cis_control_ids: List of CIS control IDs (e.g., ["4.8", "10.3"])
            cited_nist_controls: NIST controls cited by CIS authors (e.g., ["CM-7", "SI-3"])
            extract: "primary" for primary CCIs only, "all" for primary + supporting (default: "all")

        Returns:
            Tuple of (cci_list, extra_nist_list)
            - cci_list: CCIs to add as <ident> elements (filtered by extract parameter)
            - extra_nist_list: the cited NIST controls to add as <reference>: every one
              except a control (and enhancement) a written CCI sits under exactly. A CCI
              under CM-7 (1) (b) restates CM-7(1); it does not stand for CM-7 or CM-7(2),
              so those stay.
        """
        logger.debug(
            f"Deduplicating NIST controls: cis_controls={len(cis_control_ids)}, "
            f"cited_nist={len(cited_nist_controls)}, extract={extract}"
        )
        seen_ccis = set()
        all_ccis = []

        # Get CCIs from CIS controls (filtered by extract parameter)
        # IMPORTANT: Deduplicate CCIs - multiple CIS controls can map to the same CCI
        for cis_id in cis_control_ids:
            ccis = self.get_ccis_for_cis_control(cis_id, extract=extract)
            for c in ccis:
                if c.cci not in seen_ccis:
                    seen_ccis.add(c.cci)
                    all_ccis.append(c.cci)

        # Determine which NIST controls are covered by these CCIs
        covered_nist = self.get_nist_controls_covered_by_ccis(all_ccis)

        # Keep every cited control no written CCI restates
        extra_nist = []
        for cited in cited_nist_controls:
            if self.control_key(cited) not in covered_nist:
                extra_nist.append(cited)

        logger.debug(
            f"Deduplication result: unique_ccis={len(all_ccis)}, extra_nist_controls={len(extra_nist)}"
        )
        return all_ccis, extra_nist

    @staticmethod
    def control_key(nist_control: str) -> str:
        """The control and its enhancement in any index form, without sub-parts, spacing
        or case: the unit that decides whether a CCI restates a cited control.

        Examples:
            "CM-8 a 1" -> "CM-8" (DISA's CCI index), "CA-8 (1)" -> "CA-8(1)",
            "SC-7 (4) (b)" -> "SC-7(4)", "CM-7.1" -> "CM-7" (assessment procedure)
        """
        text = nist_control.strip().upper()
        match = _CONTROL_KEY_RE.match(text)
        if not match:
            return text
        control, enhancement = match.groups()
        return f"{control}({enhancement})" if enhancement else control


# Singleton instance for easy access
_service_instance = None


def get_cci_service() -> CCILookupService:
    """Get singleton CCI lookup service instance."""
    global _service_instance
    if _service_instance is None:
        logger.debug("Creating singleton CCI lookup service instance")
        _service_instance = CCILookupService()
    return _service_instance
