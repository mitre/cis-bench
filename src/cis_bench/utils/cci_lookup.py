"""CCI (Control Correlation Identifier) lookup service.

Maps CIS Controls to DoD CCIs using the official CIS-CCI mapping.
Provides NIST deduplication to avoid redundant control references.
"""

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


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

        logger.info(f"Initializing CCI lookup service with mapping file: {mapping_file}")

        with open(mapping_file) as f:
            self._mapping_data = json.load(f)

        logger.debug(f"Loaded {len(self._mapping_data)} CCI mapping entries")

        # Build reverse index: CCI → NIST control
        self._cci_to_nist: dict[str, str] = {}
        self._build_reverse_index()

    def _build_reverse_index(self):
        """Build CCI → NIST control reverse index."""
        logger.debug("Building CCI to NIST control reverse index")
        for entry in self._mapping_data:
            # Skip if not OFFICIAL (INFERRED has variable schema)
            if entry.get("mapping_status") != "OFFICIAL":
                continue

            # Primary CCI
            primary = entry.get("primary_cci", {})
            if primary.get("cci"):
                # NIST control might be in mapping or need extraction
                nist = entry.get("nist_control", "")
                self._cci_to_nist[primary["cci"]] = nist

            # Supporting CCIs
            for supp in entry.get("supporting_ccis", []):
                cci_id = supp.get("cci") or supp.get("cci_id")
                if cci_id:
                    # Try to extract NIST from reasoning if not explicit
                    nist = self._extract_nist_from_cci_entry(supp)
                    if nist:
                        self._cci_to_nist[cci_id] = nist

    def _extract_nist_from_cci_entry(self, cci_entry: dict) -> str | None:
        """Extract NIST control from CCI entry."""
        # Could be explicit or in reasoning
        # For now, use pattern matching in reasoning
        reasoning = cci_entry.get("reasoning", "")

        # Look for patterns like "CM-7.1", "AC-2(1)"
        pattern = r"([A-Z]{2}-\d+(?:\.\d+)?(?:\(\d+\))?)"
        matches = re.findall(pattern, reasoning)

        return matches[0] if matches else None

    def get_ccis_for_cis_control(
        self, cis_control_id: str, extract: str = "all"
    ) -> list[CCIMapping]:
        """Get CCIs for a CIS control.

        Args:
            cis_control_id: CIS control ID (e.g., "4.8", "10.3")
            extract: "primary" for primary CCI only, "all" for primary + supporting (default: "all")

        Returns:
            List of CCIMapping objects
        """
        logger.debug(f"Looking up CCIs for CIS control: {cis_control_id} (extract={extract})")
        # Find mapping entry
        for entry in self._mapping_data:
            if entry.get("cis_id") == cis_control_id:
                ccis = []

                # Add primary
                primary = entry.get("primary_cci", {})
                if primary.get("cci"):
                    ccis.append(
                        CCIMapping(
                            cci=primary["cci"],
                            nist_control=entry.get("nist_control"),
                            confidence=primary.get("confidence"),
                        )
                    )

                # Add supporting only if extract="all"
                if extract == "all":
                    for supp in entry.get("supporting_ccis", []):
                        cci_id = supp.get("cci") or supp.get("cci_id")
                        if cci_id:
                            nist = self._extract_nist_from_cci_entry(supp)
                            ccis.append(
                                CCIMapping(
                                    cci=cci_id,
                                    nist_control=nist,
                                    confidence=supp.get("confidence")
                                    or supp.get("confidence_score"),
                                )
                            )

                return ccis

        return []

    def get_nist_controls_covered_by_ccis(self, ccis: list[str]) -> set[str]:
        """Get all NIST controls covered by given CCIs.

        Args:
            ccis: List of CCI identifiers

        Returns:
            Set of base NIST control IDs covered by these CCIs
        """
        covered = set()

        for cci in ccis:
            nist_ctrl = self._cci_to_nist.get(cci)
            if nist_ctrl:
                # Extract base control: "CM-7.1" → "CM-7", "CM-7(5)" → "CM-7"
                base = self._get_base_nist_control(nist_ctrl)
                covered.add(base)

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
            - extra_nist_list: NIST controls NOT covered by CCIs (add as <reference>)
        """
        logger.debug(
            f"Deduplicating NIST controls: {len(cis_control_ids)} CIS controls, {len(cited_nist_controls)} cited NIST (extract={extract})"
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

        # Find extras (cited but not covered)
        extra_nist = []
        for cited in cited_nist_controls:
            cited_base = self._get_base_nist_control(cited)

            if cited_base not in covered_nist:
                extra_nist.append(cited)

        logger.info(
            f"Deduplication result: {len(all_ccis)} unique CCIs, {len(extra_nist)} extra NIST controls"
        )
        return all_ccis, extra_nist

    @staticmethod
    def _get_base_nist_control(nist_control: str) -> str:
        """Extract base NIST control.

        Examples:
            "CM-7" → "CM-7"
            "CM-7.1" → "CM-7"
            "CM-7(5)" → "CM-7"
            "CM-7.1(5)" → "CM-7"
        """
        # Remove enhancements and sub-controls
        base = nist_control.split("(")[0]  # Remove enhancements
        base = base.split(".")[0]  # Remove sub-controls
        return base.strip()


# Singleton instance for easy access
_service_instance = None


def get_cci_service() -> CCILookupService:
    """Get singleton CCI lookup service instance."""
    global _service_instance
    if _service_instance is None:
        logger.debug("Creating singleton CCI lookup service instance")
        _service_instance = CCILookupService()
    return _service_instance
