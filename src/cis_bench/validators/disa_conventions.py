"""DISA Conventions Validator for XCCDF exports.

Validates that XCCDF output follows DISA STIG conventions v1.10.0
"""

import logging
import re

from lxml import etree

logger = logging.getLogger(__name__)


class DISAConventionsValidator:
    """Validates XCCDF against DISA conventions v1.10.0."""

    def __init__(self, xccdf_file: str):
        """Initialize validator with XCCDF file."""
        logger.info(f"Initializing DISA conventions validator for: {xccdf_file}")
        self.tree = etree.parse(xccdf_file)
        self.root = self.tree.getroot()

        # Auto-detect XCCDF namespace from root element
        root_ns = self.root.tag.split("}")[0].strip("{") if "}" in self.root.tag else None
        self.xccdf_ns = root_ns if root_ns else "http://checklists.nist.gov/xccdf/1.1"
        logger.debug(f"Detected XCCDF namespace: {self.xccdf_ns}")

        self.dc_ns = "http://purl.org/dc/elements/1.1/"
        self.errors = []
        self.warnings = []

    def validate(self) -> tuple[bool, list[str], list[str]]:
        """Run all validation checks.

        Returns:
            (is_valid, errors, warnings)
        """
        logger.info("Starting DISA conventions validation")
        self.errors = []
        self.warnings = []

        # Run all checks
        logger.debug("Checking required benchmark elements")
        self._check_required_benchmark_elements()
        logger.debug("Checking plain-text elements")
        self._check_plain_text_elements()
        logger.debug("Checking reference element")
        self._check_reference_element()
        logger.debug("Checking groups")
        self._check_groups()
        logger.debug("Checking rules")
        self._check_rules()

        is_valid = len(self.errors) == 0
        logger.info(
            f"Validation complete: is_valid={is_valid}, errors={len(self.errors)}, warnings={len(self.warnings)}"
        )
        return is_valid, self.errors, self.warnings

    def _check_required_benchmark_elements(self):
        """Check required benchmark-level elements."""
        required = ["notice", "front-matter", "rear-matter", "reference", "plain-text", "version"]

        for elem_name in required:
            elem = self.root.find(f".//{{{self.xccdf_ns}}}{elem_name}")
            if elem is None:
                self.errors.append(f"Missing required element: {elem_name}")

    def _check_plain_text_elements(self):
        """Check plain-text elements follow DISA conventions."""
        plain_texts = self.root.findall(f".//{{{self.xccdf_ns}}}plain-text")

        required_ids = ["release-info", "generator", "conventionsVersion"]
        found_ids = [pt.get("id") for pt in plain_texts if pt.get("id")]

        for req_id in required_ids:
            if req_id not in found_ids:
                self.errors.append(f"Missing required plain-text element: id='{req_id}'")

        # Check conventionsVersion value
        for pt in plain_texts:
            if pt.get("id") == "conventionsVersion":
                if pt.text != "1.10.0":
                    self.warnings.append(f"conventionsVersion is '{pt.text}', expected '1.10.0'")

        # Check release-info format
        for pt in plain_texts:
            if pt.get("id") == "release-info":
                if not re.match(r"Release:\s+\d+\s+Benchmark Date:", pt.text or ""):
                    self.warnings.append("release-info format doesn't match DISA pattern")

    def _check_reference_element(self):
        """Check reference has Dublin Core elements."""
        ref = self.root.find(f".//{{{self.xccdf_ns}}}reference")

        if ref is None:
            self.errors.append("Missing required reference element")
            return

        # Check for dc:publisher and dc:source
        dc_publisher = ref.find(f"{{{self.dc_ns}}}publisher")
        dc_source = ref.find(f"{{{self.dc_ns}}}source")

        if dc_publisher is None:
            self.errors.append("reference missing required dc:publisher element")

        if dc_source is None:
            self.errors.append("reference missing required dc:source element")

    def _check_groups(self):
        """Check Group elements follow conventions."""
        groups = self.root.findall(f".//{{{self.xccdf_ns}}}Group")
        logger.debug(f"Found {len(groups)} Group elements")

        if not groups:
            self.warnings.append("No Group elements found (DISA STIGs use Groups)")

        for group in groups:
            # Check each Group has title, description, Rule
            if group.find(f"{{{self.xccdf_ns}}}title") is None:
                self.errors.append(f"Group {group.get('id')} missing title")

            if group.find(f"{{{self.xccdf_ns}}}description") is None:
                self.errors.append(f"Group {group.get('id')} missing description")

            rules = group.findall(f"{{{self.xccdf_ns}}}Rule")
            if len(rules) != 1:
                self.warnings.append(
                    f"Group {group.get('id')} has {len(rules)} Rules (DISA convention: exactly 1)"
                )

    def _check_rules(self):
        """Check Rule elements follow conventions."""
        rules = self.root.findall(f".//{{{self.xccdf_ns}}}Rule")
        logger.debug(f"Found {len(rules)} Rule elements")

        for rule in rules:
            rule_id = rule.get("id", "unknown")

            # Check required attributes
            if not rule.get("severity"):
                self.errors.append(f"Rule {rule_id} missing severity attribute")
            elif rule.get("severity") not in ["low", "medium", "high"]:
                self.errors.append(f"Rule {rule_id} invalid severity: {rule.get('severity')}")

            if not rule.get("weight"):
                self.errors.append(f"Rule {rule_id} missing weight attribute")
            elif rule.get("weight") != "10.0":
                self.warnings.append(
                    f"Rule {rule_id} weight is {rule.get('weight')}, DISA standard is 10.0"
                )

            # Check required elements
            required_rule_elements = ["version", "title", "description"]
            for elem_name in required_rule_elements:
                if rule.find(f"{{{self.xccdf_ns}}}{elem_name}") is None:
                    self.errors.append(f"Rule {rule_id} missing {elem_name} element")

            # Check description has VulnDiscussion
            desc = rule.find(f"{{{self.xccdf_ns}}}description")
            if desc is not None and desc.text:
                if (
                    "<VulnDiscussion>" not in desc.text
                    and "&lt;VulnDiscussion&gt;" not in desc.text
                ):
                    self.warnings.append(f"Rule {rule_id} description missing VulnDiscussion tag")

            # Check for fixtext and check
            if rule.find(f"{{{self.xccdf_ns}}}fixtext") is None:
                self.warnings.append(f"Rule {rule_id} missing fixtext element")

            if rule.find(f"{{{self.xccdf_ns}}}check") is None:
                self.warnings.append(f"Rule {rule_id} missing check element")

            # Check ident elements (CCIs)
            idents = rule.findall(f"{{{self.xccdf_ns}}}ident")
            for ident in idents:
                if ident.get("system") == "http://cyber.mil/cci":
                    if not re.match(r"CCI-\d{6}", ident.text or ""):
                        self.errors.append(f"Rule {rule_id} invalid CCI format: {ident.text}")


def validate_disa_conventions(xccdf_file: str) -> bool:
    """Validate XCCDF file against DISA conventions.

    Args:
        xccdf_file: Path to XCCDF XML file

    Returns:
        True if valid, False otherwise (prints errors/warnings)
    """
    logger.info(f"Validating DISA conventions for: {xccdf_file}")
    validator = DISAConventionsValidator(xccdf_file)
    is_valid, errors, warnings = validator.validate()

    if errors:
        logger.warning(f"Validation found {len(errors)} errors")
        print("ERRORS:")
        for error in errors:
            print(f"  ✗ {error}")
        print()

    if warnings:
        logger.info(f"Validation found {len(warnings)} warnings")
        print("WARNINGS:")
        for warning in warnings:
            print(f"  ⚠ {warning}")
        print()

    if is_valid and not warnings:
        logger.info("Validation passed: All DISA conventions v1.10.0 checks passed")
        print("✓ Passes all DISA conventions v1.10.0 checks")

    return is_valid
