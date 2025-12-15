"""Tests for strategy pattern implementation.

Tests ScraperStrategy base class, StrategyDetector, and WorkbenchV1Strategy.
Demonstrates strategy pattern flexibility for handling HTML structure changes.
"""

import pytest
from bs4 import BeautifulSoup

from cis_bench.fetcher.strategies.base import ScraperStrategy
from cis_bench.fetcher.strategies.detector import StrategyDetector
from cis_bench.fetcher.strategies.v1_current import WorkbenchV1Strategy
from cis_bench.models.benchmark import Artifact, MITREMapping

# ============ Fixtures: Real HTML Samples ============


@pytest.fixture
def v1_complete_html():
    """Complete V1 HTML with all fields populated."""
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <div id="description-recommendation-data">
            <p>Ensure that the kubeconfig file permissions are set to 644 or more restrictive.</p>
        </div>

        <div id="rationale_statement-recommendation-data">
            <p>The <code>kubelet</code> kubeconfig file controls various parameters.</p>
        </div>

        <div id="impact_statement-recommendation-data">
            <p>This strengthens security posture by preventing unauthorized modifications.</p>
        </div>

        <div id="audit_procedure-recommendation-data">
            <p>SSH to the worker nodes and run:</p>
            <pre><code>stat -c %a /var/lib/kubelet/kubeconfig</code></pre>
        </div>

        <div id="remediation_procedure-recommendation-data">
            <p>Run the following command:</p>
            <pre><code>chmod 644 &lt;kubeconfig file&gt;</code></pre>
        </div>

        <div id="default_value-recommendation-data">
            <p>See the AWS EKS documentation for the default value.</p>
        </div>

        <div id="automated_scoring-recommendation-data">
            <p>Automated</p>
        </div>

        <div id="references-recommendation-data">
            <p><a href="https://kubernetes.io/docs/admin/kube-proxy/">Kubernetes Docs</a></p>
            <p>NIST SP 800-53 Rev. 5: AC-3, CM-6, SI-2 (1)</p>
        </div>

        <div id="mitre_mappings-recommendation-data">
            <table>
                <tr><th>Techniques</th></tr>
                <tr><td>T1068, T1203</td></tr>
                <tr><th>Tactics</th></tr>
                <tr><td>TA0001, TA0002</td></tr>
                <tr><th>Mitigations</th></tr>
                <tr><td>M1022, M1026</td></tr>
            </table>
        </div>

        <div id="artifact_equation-recommendation-data">
            <p>artifact_1 AND artifact_2</p>
        </div>

        <div id="notes-recommendation-data">
            <p>Additional information about this recommendation.</p>
        </div>

        <wb-recommendation-profiles profiles='[
            {"id":1,"title":"Level 1 - Server"},
            {"id":2,"title":"Level 2 - Server"}
        ]'></wb-recommendation-profiles>

        <wb-recommendation-feature-controls json-controls='[
            {"version":8,"control":"4.1","title":"Secure Configuration Process","ig1":true,"ig2":true,"ig3":true},
            {"version":7,"control":"5.2","title":"Malware Defenses","ig1":false,"ig2":true,"ig3":true}
        ]'></wb-recommendation-feature-controls>

        <wb-recommendation-artifacts artifacts-json='[
            {"id":123,"view_level":"3.1.1.1","title":"Check kubeconfig permissions","status":"automated","artifact_type":{"name":"bash"}},
            {"id":124,"view_level":"3.1.1.2","title":"Verify ownership","status":"automated","artifact_type":{"name":"bash"}}
        ]'></wb-recommendation-artifacts>

        <a href="https://workbench.cisecurity.org/sections/123/recommendations/456">
            <i class="fa-level-up"></i> PARENT : Ensure kubelet is configured securely
        </a>
    </body>
    </html>
    """


@pytest.fixture
def v1_minimal_html():
    """Minimal V1 HTML with only required fields."""
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <div id="description-recommendation-data">
            <p>Basic description</p>
        </div>

        <div id="rationale_statement-recommendation-data">
            <p>Basic rationale</p>
        </div>

        <div id="audit_procedure-recommendation-data">
            <p>Basic audit steps</p>
        </div>

        <div id="automated_scoring-recommendation-data">
            <p>Manual</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def v1_malformed_html():
    """Malformed HTML with missing closing tags and broken structure."""
    return """
    <html>
    <body>
        <div id="description-recommendation-data">
            <p>Description without closing tag
        </div>

        <div id="rationale_statement-recommendation-data">
            <p>Rationale
        <!-- missing closing div -->

        <div id="audit_procedure-recommendation-data">
            <p>Audit<span>nested</span>
        </div>

        <wb-recommendation-profiles profiles='INVALID_JSON'></wb-recommendation-profiles>
    </body>
    """


@pytest.fixture
def future_v2_html():
    """Hypothetical future HTML structure (V2) with different selectors."""
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <!-- Future CIS WorkBench might change their HTML structure -->
        <section class="recommendation-description">
            <p>Description in new structure</p>
        </section>

        <section class="recommendation-rationale">
            <p>Rationale in new structure</p>
        </section>

        <div data-field="audit">
            <p>New audit structure</p>
        </div>

        <!-- No wb- custom elements, just regular divs -->
        <div class="profiles-list">
            <span data-profile="Level 1">Level 1</span>
        </div>
    </body>
    </html>
    """


# ============ Test ScraperStrategy Base Class ============


class TestScraperStrategyBase:
    """Test abstract base class behavior."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that ScraperStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ScraperStrategy()

    def test_subclass_must_implement_version(self):
        """Test that subclass must implement version property."""

        class IncompleteStrategy(ScraperStrategy):
            @property
            def selectors(self):
                return {}

            def extract_recommendation(self, html):
                return {}

        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_subclass_must_implement_selectors(self):
        """Test that subclass must implement selectors property."""

        class IncompleteStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v1_test"

            def extract_recommendation(self, html):
                return {}

        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_subclass_must_implement_extract_recommendation(self):
        """Test that subclass must implement extract_recommendation method."""

        class IncompleteStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v1_test"

            @property
            def selectors(self):
                return {}

        with pytest.raises(TypeError):
            IncompleteStrategy()

    def test_valid_strategy_implementation(self):
        """Test that properly implemented strategy can be instantiated."""

        class ValidStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v1_test"

            @property
            def selectors(self):
                return {"description": {"id": "desc"}}

            def extract_recommendation(self, html):
                return {"description": "test"}

        # Should not raise
        strategy = ValidStrategy()
        assert strategy.version == "v1_test"
        assert "description" in strategy.selectors


class TestScraperStrategyCompatibility:
    """Test default is_compatible implementation."""

    def test_is_compatible_with_matching_id(self):
        """Test compatibility check when selector ID exists."""

        class TestStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v1_test"

            @property
            def selectors(self):
                return {"description": {"id": "description-recommendation-data"}}

            def extract_recommendation(self, html):
                return {}

        strategy = TestStrategy()
        html = '<div id="description-recommendation-data">Test</div>'

        # Should be compatible
        assert strategy.is_compatible(html) is True

    def test_is_compatible_with_matching_class(self):
        """Test compatibility check when selector class exists."""

        class TestStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v1_test"

            @property
            def selectors(self):
                return {"description": {"class": "recommendation-desc"}}

            def extract_recommendation(self, html):
                return {}

        strategy = TestStrategy()
        html = '<div class="recommendation-desc">Test</div>'

        # Should be compatible
        assert strategy.is_compatible(html) is True

    def test_is_compatible_missing_selector(self):
        """Test compatibility check when selector doesn't exist."""

        class TestStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v1_test"

            @property
            def selectors(self):
                return {"description": {"id": "nonexistent-id"}}

            def extract_recommendation(self, html):
                return {}

        strategy = TestStrategy()
        html = '<div id="other-id">Test</div>'

        # Should not be compatible
        assert strategy.is_compatible(html) is False

    def test_is_compatible_empty_selectors(self):
        """Test compatibility check with empty selectors."""

        class TestStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v1_test"

            @property
            def selectors(self):
                return {}

            def extract_recommendation(self, html):
                return {}

        strategy = TestStrategy()
        html = "<div>Test</div>"

        # Should not be compatible
        assert strategy.is_compatible(html) is False


# ============ Test WorkbenchV1Strategy ============


class TestWorkbenchV1StrategyExtraction:
    """Test V1 strategy field extraction."""

    def test_extract_all_fields_complete_html(self, v1_complete_html):
        """Test extraction of all fields from complete HTML."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        # Verify all HTML content fields
        assert "description" in data
        assert "kubeconfig file permissions" in data["description"]

        assert "rationale" in data
        assert "kubelet" in data["rationale"]

        assert "impact" in data
        assert "security posture" in data["impact"]

        assert "audit" in data
        assert "stat -c %a" in data["audit"]

        assert "remediation" in data
        assert "chmod 644" in data["remediation"]

        assert "default_value" in data
        assert "AWS EKS documentation" in data["default_value"]

        assert "references" in data
        assert "kubernetes.io" in data["references"]

        assert "artifact_equation" in data
        assert "artifact_1 AND artifact_2" in data["artifact_equation"]

        assert "additional_info" in data
        assert "Additional information" in data["additional_info"]

    def test_extract_assessment_status(self, v1_complete_html):
        """Test assessment status extraction."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        assert data["assessment_status"] == "Automated"

    def test_extract_profiles(self, v1_complete_html):
        """Test profiles extraction from wb-recommendation-profiles."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        assert "profiles" in data
        assert len(data["profiles"]) == 2
        assert "Level 1 - Server" in data["profiles"]
        assert "Level 2 - Server" in data["profiles"]

    def test_extract_cis_controls(self, v1_complete_html):
        """Test CIS Controls extraction."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        assert "cis_controls" in data
        assert len(data["cis_controls"]) == 2

        # Check V8 control
        v8_control = next(c for c in data["cis_controls"] if c.version == 8)
        assert v8_control.control == "4.1"
        assert v8_control.title == "Secure Configuration Process"
        assert v8_control.ig1 is True
        assert v8_control.ig2 is True
        assert v8_control.ig3 is True

        # Check V7 control
        v7_control = next(c for c in data["cis_controls"] if c.version == 7)
        assert v7_control.control == "5.2"
        assert v7_control.ig1 is False
        assert v7_control.ig2 is True

    def test_extract_mitre_mapping(self, v1_complete_html):
        """Test MITRE ATT&CK mapping extraction."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        assert "mitre_mapping" in data
        assert data["mitre_mapping"] is not None

        mitre = data["mitre_mapping"]
        assert isinstance(mitre, MITREMapping)
        assert "T1068" in mitre.techniques
        assert "T1203" in mitre.techniques
        assert "TA0001" in mitre.tactics
        assert "TA0002" in mitre.tactics
        assert "M1022" in mitre.mitigations
        assert "M1026" in mitre.mitigations

    def test_extract_nist_controls(self, v1_complete_html):
        """Test NIST SP 800-53 control extraction."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        assert "nist_controls" in data
        assert len(data["nist_controls"]) == 3
        assert "AC-3" in data["nist_controls"]
        assert "CM-6" in data["nist_controls"]
        assert "SI-2 (1)" in data["nist_controls"]

    def test_extract_artifacts(self, v1_complete_html):
        """Test artifact extraction."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        assert "artifacts" in data
        assert len(data["artifacts"]) == 2

        artifact1 = data["artifacts"][0]
        assert isinstance(artifact1, Artifact)
        assert artifact1.id == 123
        assert artifact1.view_level == "3.1.1.1"
        assert artifact1.title == "Check kubeconfig permissions"
        assert artifact1.status == "automated"

    def test_extract_parent_reference(self, v1_complete_html):
        """Test parent reference extraction."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_complete_html)

        assert "parent" in data
        assert data["parent"] is not None
        assert (
            str(data["parent"].url)
            == "https://workbench.cisecurity.org/sections/123/recommendations/456"
        )
        assert data["parent"].title == "Ensure kubelet is configured securely"


class TestWorkbenchV1StrategyMissingFields:
    """Test V1 strategy graceful degradation when fields are missing."""

    def test_extract_minimal_html(self, v1_minimal_html):
        """Test extraction with minimal required fields only."""
        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(v1_minimal_html)

        # Present fields
        assert data["description"] is not None
        assert data["rationale"] is not None
        assert data["audit"] is not None
        assert data["assessment_status"] == "Manual"

        # Missing fields should be None or empty
        assert data["impact"] is None
        assert data["remediation"] is None
        assert data["default_value"] is None
        assert data["artifact_equation"] is None
        assert data["references"] is None
        assert data["additional_info"] is None
        assert data["mitre_mapping"] is None
        assert data["parent"] is None

        # Empty lists for missing wb- elements
        assert data["profiles"] == []
        assert data["cis_controls"] == []
        assert data["artifacts"] == []
        assert data["nist_controls"] == []

    def test_extract_missing_description(self):
        """Test extraction when description field is missing."""
        html = """
        <html>
        <body>
            <div id="audit_procedure-recommendation-data">Audit only</div>
        </body>
        </html>
        """

        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(html)

        assert data["description"] is None
        assert data["audit"] is not None

    def test_extract_empty_mitre_table(self):
        """Test MITRE mapping when table is empty."""
        html = """
        <html>
        <body>
            <div id="mitre_mappings-recommendation-data">
                <table>
                    <tr><th>Techniques</th></tr>
                    <tr><td></td></tr>
                </table>
            </div>
        </body>
        </html>
        """

        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(html)

        # Should return None for empty MITRE data
        assert data["mitre_mapping"] is None

    def test_extract_invalid_json_profiles(self):
        """Test profiles extraction with invalid JSON."""
        html = """
        <html>
        <body>
            <wb-recommendation-profiles profiles='INVALID JSON'></wb-recommendation-profiles>
        </body>
        </html>
        """

        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(html)

        # Should return empty list on JSON parse error
        assert data["profiles"] == []

    def test_extract_invalid_json_controls(self):
        """Test CIS Controls extraction with invalid JSON."""
        html = """
        <html>
        <body>
            <wb-recommendation-feature-controls json-controls='NOT_JSON'></wb-recommendation-feature-controls>
        </body>
        </html>
        """

        strategy = WorkbenchV1Strategy()
        data = strategy.extract_recommendation(html)

        # Should return empty list on JSON parse error
        assert data["cis_controls"] == []

    def test_extract_malformed_html(self, v1_malformed_html):
        """Test extraction with malformed HTML (BeautifulSoup should handle gracefully)."""
        strategy = WorkbenchV1Strategy()

        # Should not raise exception - BeautifulSoup is forgiving
        data = strategy.extract_recommendation(v1_malformed_html)

        # Should extract what it can
        assert data["description"] is not None
        assert data["audit"] is not None
        assert data["profiles"] == []  # Invalid JSON


class TestWorkbenchV1StrategyCompatibility:
    """Test V1 strategy compatibility detection."""

    def test_is_compatible_with_v1_html(self, v1_complete_html):
        """Test V1 strategy detects V1 HTML as compatible."""
        strategy = WorkbenchV1Strategy()
        assert strategy.is_compatible(v1_complete_html) is True

    def test_is_compatible_with_minimal_v1_html(self, v1_minimal_html):
        """Test V1 strategy detects minimal V1 HTML as compatible."""
        strategy = WorkbenchV1Strategy()
        assert strategy.is_compatible(v1_minimal_html) is True

    def test_is_compatible_with_wb_elements_only(self):
        """Test V1 strategy compatible with wb- elements even without divs."""
        html = """
        <html>
        <body>
            <wb-recommendation-profiles profiles='[]'></wb-recommendation-profiles>
        </body>
        </html>
        """

        strategy = WorkbenchV1Strategy()
        assert strategy.is_compatible(html) is True

    def test_is_not_compatible_with_future_html(self, future_v2_html):
        """Test V1 strategy rejects future V2 HTML structure."""
        strategy = WorkbenchV1Strategy()
        assert strategy.is_compatible(future_v2_html) is False

    def test_is_not_compatible_with_empty_html(self):
        """Test V1 strategy rejects empty HTML."""
        strategy = WorkbenchV1Strategy()
        assert strategy.is_compatible("<html><body></body></html>") is False

    def test_is_not_compatible_with_single_div(self):
        """Test V1 strategy requires at least 2 expected divs for compatibility."""
        # Only 1 expected div
        html = """
        <html>
        <body>
            <div id="description-recommendation-data">Only one field</div>
        </body>
        </html>
        """

        strategy = WorkbenchV1Strategy()
        assert strategy.is_compatible(html) is False


# ============ Test StrategyDetector ============


class TestStrategyDetector:
    """Test strategy detection and management."""

    def setup_method(self):
        """Clear registered strategies before each test."""
        StrategyDetector.clear_strategies()

    def test_register_strategy(self):
        """Test strategy registration."""
        strategy = WorkbenchV1Strategy()
        StrategyDetector.register_strategy(strategy)

        strategies = StrategyDetector.list_strategies()
        assert len(strategies) == 1
        assert "v1_2025_10" in strategies

    def test_register_multiple_strategies(self):
        """Test registering multiple strategies."""

        # Create mock V2 strategy
        class WorkbenchV2Strategy(ScraperStrategy):
            @property
            def version(self):
                return "v2_2026_01"

            @property
            def selectors(self):
                return {"description": {"class": "new-desc"}}

            def extract_recommendation(self, html):
                return {}

        v1 = WorkbenchV1Strategy()
        v2 = WorkbenchV2Strategy()

        StrategyDetector.register_strategy(v2, position=0)  # Newest first
        StrategyDetector.register_strategy(v1, position=1)  # Older second

        strategies = StrategyDetector.list_strategies()
        assert len(strategies) == 2
        assert strategies[0] == "v2_2026_01"  # Newest first
        assert strategies[1] == "v1_2025_10"

    def test_detect_strategy_v1(self, v1_complete_html):
        """Test auto-detection selects V1 strategy for V1 HTML."""
        # Register V1 strategy
        v1 = WorkbenchV1Strategy()
        StrategyDetector.register_strategy(v1)

        # Detect
        detected = StrategyDetector.detect_strategy(v1_complete_html)

        assert isinstance(detected, WorkbenchV1Strategy)
        assert detected.version == "v1_2025_10"

    def test_detect_strategy_priority_order(self):
        """Test that detection checks strategies in priority order (newest first)."""

        # Create V2 strategy that accepts everything
        class WorkbenchV2Strategy(ScraperStrategy):
            @property
            def version(self):
                return "v2_2026_01"

            @property
            def selectors(self):
                return {"description": {"class": "new-desc"}}

            def extract_recommendation(self, html):
                return {}

            def is_compatible(self, html):
                return True  # Always compatible

        # Create V1 strategy
        v1 = WorkbenchV1Strategy()
        v2 = WorkbenchV2Strategy()

        # Register V2 first (highest priority)
        StrategyDetector.register_strategy(v2, position=0)
        StrategyDetector.register_strategy(v1, position=1)

        # Any HTML should match V2 first (even V1 HTML)
        html = '<div id="description-recommendation-data">test</div>'
        detected = StrategyDetector.detect_strategy(html)

        assert detected.version == "v2_2026_01"  # V2 selected (higher priority)

    def test_detect_strategy_no_strategies_registered(self):
        """Test error when no strategies registered."""
        html = "<div>test</div>"

        with pytest.raises(ValueError, match="No scraper strategies registered"):
            StrategyDetector.detect_strategy(html)

    def test_detect_strategy_no_compatible_strategy(self, future_v2_html):
        """Test error when no compatible strategy found."""
        # Register only V1
        v1 = WorkbenchV1Strategy()
        StrategyDetector.register_strategy(v1)

        # Try to detect with V2 HTML
        with pytest.raises(ValueError, match="No compatible scraper strategy found"):
            StrategyDetector.detect_strategy(future_v2_html)

    def test_detect_strategy_handles_exceptions(self):
        """Test that detection continues if a strategy raises an exception."""

        # Create buggy strategy
        class BuggyStrategy(ScraperStrategy):
            @property
            def version(self):
                return "v_buggy"

            @property
            def selectors(self):
                return {}

            def extract_recommendation(self, html):
                return {}

            def is_compatible(self, html):
                raise Exception("Bug in compatibility check")

        # Register buggy strategy first, then working V1
        buggy = BuggyStrategy()
        v1 = WorkbenchV1Strategy()

        StrategyDetector.register_strategy(buggy, position=0)
        StrategyDetector.register_strategy(v1, position=1)

        # Should skip buggy strategy and use V1
        html = '<div id="description-recommendation-data">test</div><div id="rationale_statement-recommendation-data">test</div>'
        detected = StrategyDetector.detect_strategy(html)

        assert detected.version == "v1_2025_10"

    def test_get_strategy_by_version(self):
        """Test retrieving specific strategy by version."""
        v1 = WorkbenchV1Strategy()
        StrategyDetector.register_strategy(v1)

        # Get by version
        strategy = StrategyDetector.get_strategy("v1_2025_10")

        assert strategy is not None
        assert strategy.version == "v1_2025_10"

    def test_get_strategy_nonexistent_version(self):
        """Test retrieving nonexistent strategy returns None."""
        v1 = WorkbenchV1Strategy()
        StrategyDetector.register_strategy(v1)

        # Try to get nonexistent version
        strategy = StrategyDetector.get_strategy("v999_9999_99")

        assert strategy is None

    def test_list_strategies_empty(self):
        """Test listing strategies when none registered."""
        strategies = StrategyDetector.list_strategies()
        assert strategies == []

    def test_clear_strategies(self):
        """Test clearing all registered strategies."""
        v1 = WorkbenchV1Strategy()
        StrategyDetector.register_strategy(v1)

        assert len(StrategyDetector.list_strategies()) == 1

        StrategyDetector.clear_strategies()

        assert len(StrategyDetector.list_strategies()) == 0


# ============ Test Future Strategy Migration ============


class TestFutureStrategyMigration:
    """Test how strategy pattern handles future HTML changes."""

    def setup_method(self):
        """Clear registered strategies before each test."""
        StrategyDetector.clear_strategies()

    def test_v2_strategy_alongside_v1(self, v1_complete_html, future_v2_html):
        """Test that V1 and V2 strategies can coexist and auto-select correctly."""

        # Create hypothetical V2 strategy
        class WorkbenchV2Strategy(ScraperStrategy):
            @property
            def version(self):
                return "v2_2026_01"

            @property
            def selectors(self):
                return {"description": {"class": "recommendation-description"}}

            def extract_recommendation(self, html):
                soup = BeautifulSoup(html, "html.parser")
                desc = soup.find("section", class_="recommendation-description")
                return {
                    "description": desc.get_text() if desc else None,
                    "assessment_status": "Unknown",
                    "profiles": [],
                    "cis_controls": [],
                    "mitre_mapping": None,
                    "nist_controls": [],
                    "artifacts": [],
                    "parent": None,
                    "rationale": None,
                    "impact": None,
                    "audit": None,
                    "remediation": None,
                    "default_value": None,
                    "artifact_equation": None,
                    "references": None,
                    "additional_info": None,
                }

            def is_compatible(self, html):
                soup = BeautifulSoup(html, "html.parser")
                # V2 uses section tags instead of div#id
                return soup.find("section", class_="recommendation-description") is not None

        # Register both (V2 first for priority)
        v2 = WorkbenchV2Strategy()
        v1 = WorkbenchV1Strategy()

        StrategyDetector.register_strategy(v2, position=0)
        StrategyDetector.register_strategy(v1, position=1)

        # Test V1 HTML → should select V1
        detected_v1 = StrategyDetector.detect_strategy(v1_complete_html)
        assert detected_v1.version == "v1_2025_10"

        # Test V2 HTML → should select V2
        detected_v2 = StrategyDetector.detect_strategy(future_v2_html)
        assert detected_v2.version == "v2_2026_01"

    def test_backward_compatibility_preserved(self, v1_complete_html):
        """Test that adding new strategies doesn't break old HTML parsing."""
        # Register V1
        v1 = WorkbenchV1Strategy()
        StrategyDetector.register_strategy(v1)

        # Extract with V1
        data_before = v1.extract_recommendation(v1_complete_html)

        # Now add V2 (simulating future update)
        class WorkbenchV2Strategy(ScraperStrategy):
            @property
            def version(self):
                return "v2_2026_01"

            @property
            def selectors(self):
                return {"description": {"class": "new-class"}}

            def extract_recommendation(self, html):
                return {}

            def is_compatible(self, html):
                return False  # Won't match V1 HTML

        v2 = WorkbenchV2Strategy()
        StrategyDetector.register_strategy(v2, position=0)

        # V1 HTML should still work
        detected = StrategyDetector.detect_strategy(v1_complete_html)
        data_after = detected.extract_recommendation(v1_complete_html)

        # Data extraction should be identical
        assert data_after["description"] == data_before["description"]
        assert data_after["assessment_status"] == data_before["assessment_status"]
