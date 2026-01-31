"""Tests for CIS WorkBench scraper with strategy pattern support.

Tests WorkbenchScraper HTTP operations, navigation tree parsing, and recommendation extraction.
Uses real HTML samples from actual CIS WorkBench pages.
"""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from cis_bench.fetcher.strategies.base import ScraperStrategy
from cis_bench.fetcher.workbench import WorkbenchScraper
from cis_bench.models.benchmark import Benchmark

# ============ Fixtures: Real HTML Samples ============


@pytest.fixture
def sample_recommendation_html():
    """Real HTML structure from CIS WorkBench recommendation page."""
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <wb-benchmark-title title="CIS Amazon EKS Benchmark v1.8.0"></wb-benchmark-title>

        <div id="description-recommendation-data">
            <p>If kubelet is running, and if it is configured by a kubeconfig file,
            ensure that the proxy kubeconfig file has permissions of 644 or more restrictive.</p>
        </div>

        <div id="rationale_statement-recommendation-data">
            <p>The <code>kubelet</code> kubeconfig file controls various parameters of the
            <code>kubelet</code> service in the worker node.</p>
        </div>

        <div id="impact_statement-recommendation-data">
            <p>Ensuring that the kubeconfig file permissions are set to 644 or more restrictive
            significantly strengthens the security posture.</p>
        </div>

        <div id="audit_procedure-recommendation-data">
            <p><strong>Method 1</strong></p>
            <p>SSH to the worker nodes</p>
            <pre><code>sudo systemctl status kubelet</code></pre>
        </div>

        <div id="remediation_procedure-recommendation-data">
            <p>Run the below command on each worker node:</p>
            <pre><code>chmod 644 &lt;kubeconfig file&gt;</code></pre>
        </div>

        <div id="default_value-recommendation-data">
            <p>See the AWS EKS documentation for the default value.</p>
        </div>

        <div id="automated_scoring-recommendation-data">
            <p>Automated</p>
        </div>

        <div id="references-recommendation-data">
            <p><a href="https://kubernetes.io/docs/admin/kube-proxy/">https://kubernetes.io/docs/admin/kube-proxy/</a></p>
            <p>NIST SP 800-53 Rev. 5: AC-3, CM-6</p>
        </div>

        <div id="mitre_mappings-recommendation-data">
            <table>
                <tr><th>Techniques</th></tr>
                <tr><td>T1068, T1203</td></tr>
                <tr><th>Tactics</th></tr>
                <tr><td>TA0001, TA0002</td></tr>
                <tr><th>Mitigations</th></tr>
                <tr><td>M1022</td></tr>
            </table>
        </div>

        <div id="artifact_equation-recommendation-data">
            <!-- Usually empty or complex artifact logic -->
        </div>

        <div id="notes-recommendation-data">
            <p>Additional information about this recommendation.</p>
        </div>

        <wb-recommendation-profiles profiles='[{"id":1,"title":"Level 1 - Server"}]'></wb-recommendation-profiles>

        <wb-recommendation-feature-controls json-controls='[
            {"version":8,"control":"4.1","title":"Establish and Maintain a Secure Configuration Process","ig1":true,"ig2":true,"ig3":true}
        ]'></wb-recommendation-feature-controls>

        <wb-recommendation-artifacts artifacts-json='[
            {"id":123,"view_level":"3.1.1.1","title":"Check kubeconfig permissions","status":"automated","artifact_type":{"name":"bash"}}
        ]'></wb-recommendation-artifacts>

        <a href="/sections/123/recommendations/456"><i class="fa-level-up"></i> PARENT : Ensure kubelet is configured securely</a>
    </body>
    </html>
    """


@pytest.fixture
def sample_benchmark_navtree():
    """Real navigation tree JSON from CIS WorkBench API."""
    return {
        "navtree": [
            {
                "id": 3511915,
                "title": "Worker Node Configuration Files",
                "view_level": "3.1",
                "subsections_for_nav_tree": [
                    {
                        "id": 3511916,
                        "title": "Kubelet Configuration",
                        "view_level": "3.1.1",
                        "subsections_for_nav_tree": None,
                        "recommendations_for_nav_tree": [
                            {
                                "id": 5772605,
                                "section_id": 3511915,
                                "title": "Ensure that the kubeconfig file permissions are set to 644 or more restrictive",
                                "view_level": "3.1.1",
                            },
                            {
                                "id": 5772606,
                                "section_id": 3511915,
                                "title": "Ensure that the kubelet kubeconfig file ownership is set to root:root",
                                "view_level": "3.1.2",
                            },
                        ],
                    }
                ],
            },
            {
                "id": 3511923,
                "title": "Kubelet",
                "view_level": "3.2",
                "subsections_for_nav_tree": None,
                "recommendations_for_nav_tree": [
                    {
                        "id": 5772614,
                        "section_id": 3511923,
                        "title": "Ensure that the Anonymous Auth is Not Enabled",
                        "view_level": "3.2.1",
                    }
                ],
            },
        ]
    }


@pytest.fixture
def sample_benchmark_title_html():
    """HTML containing benchmark title."""
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <wb-benchmark-title title="CIS Amazon Elastic Kubernetes Service (EKS) Benchmark v1.8.0"></wb-benchmark-title>
    </body>
    </html>
    """


@pytest.fixture
def mock_session():
    """Mock requests.Session for HTTP calls."""
    session = Mock(spec=requests.Session)
    return session


@pytest.fixture
def mock_strategy():
    """Mock scraper strategy."""
    strategy = Mock(spec=ScraperStrategy)
    strategy.version = "v1_test"
    strategy.extract_recommendation.return_value = {
        "assessment_status": "Automated",
        "description": "Test description",
        "rationale": "Test rationale",
        "impact": "Test impact",
        "audit": "Test audit",
        "remediation": "Test remediation",
        "default_value": "Test default",
        "artifact_equation": None,
        "references": "Test references",
        "additional_info": "Test notes",
        "profiles": ["Level 1"],
        "cis_controls": [],
        "mitre_mapping": None,
        "nist_controls": [],
        "artifacts": [],
        "parent": None,
    }
    return strategy


# ============ Test WorkbenchScraper Basic Operations ============


class TestWorkbenchScraperBasicOperations:
    """Test basic HTTP operations and URL handling."""

    def test_fetch_html_success(self, mock_session):
        """Test successful HTML fetch."""
        # Setup
        mock_response = Mock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute
        html = scraper.fetch_html("https://workbench.cisecurity.org/test")

        # Verify
        assert html == "<html><body>Test</body></html>"
        # No longer passes verify=False - it's set on session.verify
        mock_session.get.assert_called_once_with("https://workbench.cisecurity.org/test")
        mock_response.raise_for_status.assert_called_once()

    def test_fetch_html_http_error(self, mock_session):
        """Test HTTP error handling."""
        # Setup - simulate 404 error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute and verify
        with pytest.raises(requests.HTTPError, match="404 Not Found"):
            scraper.fetch_html("https://workbench.cisecurity.org/nonexistent")

    def test_fetch_html_403_forbidden(self, mock_session):
        """Test 403 Forbidden error (auth failure)."""
        # Setup
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute and verify
        with pytest.raises(requests.HTTPError, match="403 Forbidden"):
            scraper.fetch_html("https://workbench.cisecurity.org/benchmarks/123")

    def test_fetch_html_timeout(self, mock_session):
        """Test timeout handling."""
        # Setup
        mock_session.get.side_effect = requests.Timeout("Request timed out")

        scraper = WorkbenchScraper(mock_session)

        # Execute and verify
        with pytest.raises(requests.Timeout):
            scraper.fetch_html("https://workbench.cisecurity.org/slow")

    def test_fetch_json_success(self, mock_session):
        """Test successful JSON fetch."""
        # Setup
        test_data = {"key": "value", "nested": {"data": 123}}
        mock_response = Mock()
        mock_response.json.return_value = test_data
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute
        data = scraper.fetch_json("https://workbench.cisecurity.org/api/test")

        # Verify
        assert data == test_data
        mock_session.get.assert_called_once_with("https://workbench.cisecurity.org/api/test")

    def test_fetch_json_invalid_response(self, mock_session):
        """Test handling of invalid JSON response."""
        # Setup
        mock_response = Mock()
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute and verify
        with pytest.raises(json.JSONDecodeError):
            scraper.fetch_json("https://workbench.cisecurity.org/api/bad")


class TestWorkbenchScraperBenchmarkID:
    """Test benchmark ID extraction from URLs."""

    def test_get_benchmark_id_standard_url(self):
        """Test ID extraction from standard benchmark URL."""
        url = "https://workbench.cisecurity.org/benchmarks/18528"
        benchmark_id = WorkbenchScraper.get_benchmark_id(url)
        assert benchmark_id == "18528"

    def test_get_benchmark_id_with_trailing_slash(self):
        """Test ID extraction with trailing slash."""
        url = "https://workbench.cisecurity.org/benchmarks/18528/"
        benchmark_id = WorkbenchScraper.get_benchmark_id(url)
        assert benchmark_id == "18528"

    def test_get_benchmark_id_long_number(self):
        """Test ID extraction with longer numbers."""
        url = "https://workbench.cisecurity.org/benchmarks/1234567890"
        benchmark_id = WorkbenchScraper.get_benchmark_id(url)
        assert benchmark_id == "1234567890"

    def test_get_benchmark_id_invalid_url(self):
        """Test error on URL without numeric ID."""
        url = "https://workbench.cisecurity.org/benchmarks/invalid"

        with pytest.raises(ValueError, match="Cannot extract benchmark ID"):
            WorkbenchScraper.get_benchmark_id(url)

    def test_get_benchmark_id_no_trailing_number(self):
        """Test error on URL with no trailing number."""
        url = "https://workbench.cisecurity.org/benchmarks"

        with pytest.raises(ValueError, match="Cannot extract benchmark ID"):
            WorkbenchScraper.get_benchmark_id(url)


class TestWorkbenchScraperBenchmarkTitle:
    """Test benchmark title extraction."""

    def test_get_benchmark_title_success(self, mock_session, sample_benchmark_title_html):
        """Test successful title extraction."""
        # Setup
        mock_response = Mock()
        mock_response.text = sample_benchmark_title_html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute
        title = scraper.get_benchmark_title("https://workbench.cisecurity.org/benchmarks/18528")

        # Verify
        assert title == "CIS Amazon Elastic Kubernetes Service (EKS) Benchmark v1.8.0"

    def test_get_benchmark_title_missing_element(self, mock_session):
        """Test fallback when title element not found."""
        # Setup
        mock_response = Mock()
        mock_response.text = "<html><body>No title here</body></html>"
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute
        title = scraper.get_benchmark_title("https://workbench.cisecurity.org/benchmarks/123")

        # Verify fallback
        assert title == "Unknown Benchmark"

    def test_get_benchmark_title_empty_attribute(self, mock_session):
        """Test handling of empty title attribute."""
        # Setup
        html = '<html><body><wb-benchmark-title title=""></wb-benchmark-title></body></html>'
        mock_response = Mock()
        mock_response.text = html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute
        title = scraper.get_benchmark_title("https://workbench.cisecurity.org/benchmarks/123")

        # Verify - empty string is returned
        assert title == ""

    def test_get_benchmark_metadata_with_published_date(self, mock_session):
        """Test metadata extraction including published_date."""
        # HTML with published date
        html = """
        <html><body>
            <wb-benchmark-title title="CIS Ubuntu Linux 22.04 LTS Benchmark v2.0.0"></wb-benchmark-title>
            <span>Published 3 months ago on Aug 1st 2025</span>
            <h2>Overview</h2>
            <p>This benchmark covers security configuration for Ubuntu 22.04.</p>
        </body></html>
        """
        mock_response = Mock()
        mock_response.text = html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute
        metadata = scraper.get_benchmark_metadata("https://workbench.cisecurity.org/benchmarks/123")

        # Verify
        assert metadata["title"] == "CIS Ubuntu Linux 22.04 LTS Benchmark v2.0.0"
        assert metadata["published_date"] == "Aug 1st 2025"

    def test_get_benchmark_metadata_without_published_date(self, mock_session):
        """Test metadata extraction when published_date is missing."""
        html = """
        <html><body>
            <wb-benchmark-title title="Test Benchmark v1.0.0"></wb-benchmark-title>
        </body></html>
        """
        mock_response = Mock()
        mock_response.text = html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        metadata = scraper.get_benchmark_metadata("https://workbench.cisecurity.org/benchmarks/123")

        assert metadata["title"] == "Test Benchmark v1.0.0"
        assert metadata.get("published_date") is None

    def test_get_benchmark_title_uses_metadata(self, mock_session, sample_benchmark_title_html):
        """Test that get_benchmark_title delegates to get_benchmark_metadata."""
        mock_response = Mock()
        mock_response.text = sample_benchmark_title_html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # get_benchmark_title should return just the title
        title = scraper.get_benchmark_title("https://workbench.cisecurity.org/benchmarks/123")

        assert title == "CIS Amazon Elastic Kubernetes Service (EKS) Benchmark v1.8.0"


# ============ Test Navigation Tree Operations ============


class TestWorkbenchScraperNavtree:
    """Test navigation tree fetching and parsing."""

    def test_fetch_navtree_success(self, mock_session, sample_benchmark_navtree):
        """Test successful navtree fetch."""
        # Setup
        mock_response = Mock()
        mock_response.json.return_value = sample_benchmark_navtree
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute
        navtree = scraper.fetch_navtree("18528")

        # Verify
        assert navtree == sample_benchmark_navtree
        mock_session.get.assert_called_once_with(
            "https://workbench.cisecurity.org/api/v1/benchmarks/18528/navtree"
        )

    def test_parse_navtree_flat_structure(self, mock_session):
        """Test parsing navtree with recommendations at top level."""
        navtree_data = {
            "navtree": [
                {
                    "id": 1,
                    "subsections_for_nav_tree": None,
                    "recommendations_for_nav_tree": [
                        {
                            "id": 100,
                            "section_id": 1,
                            "title": "Test Recommendation",
                            "view_level": "1.1",
                        }
                    ],
                }
            ]
        }

        scraper = WorkbenchScraper(mock_session)

        # Execute
        parsed = scraper.parse_navtree(navtree_data)

        # Verify
        assert len(parsed) == 1
        assert parsed[0]["url"] == "https://workbench.cisecurity.org/sections/1/recommendations/100"
        assert parsed[0]["title"] == "Test Recommendation"
        assert parsed[0]["ref"] == "1.1"

    def test_parse_navtree_nested_structure(self, mock_session, sample_benchmark_navtree):
        """Test parsing navtree with nested subsections."""
        scraper = WorkbenchScraper(mock_session)

        # Execute
        parsed = scraper.parse_navtree(sample_benchmark_navtree)

        # Verify - should find all 3 recommendations
        assert len(parsed) == 3

        # Check first recommendation (from nested subsection)
        assert parsed[0]["ref"] == "3.1.1"
        assert (
            parsed[0]["url"]
            == "https://workbench.cisecurity.org/sections/3511915/recommendations/5772605"
        )

        # Check second recommendation (also from nested subsection)
        assert parsed[1]["ref"] == "3.1.2"

        # Check third recommendation (from top-level section)
        assert parsed[2]["ref"] == "3.2.1"
        assert (
            parsed[2]["url"]
            == "https://workbench.cisecurity.org/sections/3511923/recommendations/5772614"
        )

    def test_parse_navtree_deeply_nested(self, mock_session):
        """Test parsing deeply nested subsections."""
        navtree_data = {
            "navtree": [
                {
                    "id": 1,
                    "subsections_for_nav_tree": [
                        {
                            "id": 2,
                            "subsections_for_nav_tree": [
                                {
                                    "id": 3,
                                    "subsections_for_nav_tree": None,
                                    "recommendations_for_nav_tree": [
                                        {
                                            "id": 999,
                                            "section_id": 1,
                                            "title": "Deep Recommendation",
                                            "view_level": "1.1.1.1",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ]
        }

        scraper = WorkbenchScraper(mock_session)

        # Execute
        parsed = scraper.parse_navtree(navtree_data)

        # Verify deep nesting works
        assert len(parsed) == 1
        assert parsed[0]["ref"] == "1.1.1.1"

    def test_parse_navtree_empty_recommendations(self, mock_session):
        """Test parsing navtree with no recommendations."""
        navtree_data = {
            "navtree": [
                {"id": 1, "subsections_for_nav_tree": None, "recommendations_for_nav_tree": []}
            ]
        }

        scraper = WorkbenchScraper(mock_session)

        # Execute
        parsed = scraper.parse_navtree(navtree_data)

        # Verify
        assert parsed == []

    def test_parse_navtree_mixed_structure(self, mock_session):
        """Test parsing navtree with both subsections and recommendations at same level."""
        navtree_data = {
            "navtree": [
                {
                    "id": 1,
                    "subsections_for_nav_tree": [
                        {
                            "id": 2,
                            "subsections_for_nav_tree": None,
                            "recommendations_for_nav_tree": [
                                {
                                    "id": 100,
                                    "section_id": 1,
                                    "title": "Nested Rec",
                                    "view_level": "1.1",
                                }
                            ],
                        }
                    ],
                    "recommendations_for_nav_tree": [
                        {"id": 200, "section_id": 1, "title": "Top Level Rec", "view_level": "1.2"}
                    ],
                }
            ]
        }

        scraper = WorkbenchScraper(mock_session)

        # Execute
        parsed = scraper.parse_navtree(navtree_data)

        # Verify - gets nested first, then top-level
        assert len(parsed) == 2


# ============ Test Strategy Integration ============


class TestWorkbenchScraperStrategyIntegration:
    """Test strategy pattern integration."""

    def test_manual_strategy_override(
        self, mock_session, mock_strategy, sample_recommendation_html
    ):
        """Test using manually specified strategy."""
        # Setup
        mock_response = Mock()
        mock_response.text = sample_recommendation_html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        # Create scraper with manual strategy
        scraper = WorkbenchScraper(mock_session, strategy=mock_strategy)

        # Execute
        data = scraper.fetch_recommendation(
            "https://workbench.cisecurity.org/sections/1/recommendations/100"
        )

        # Verify manual strategy was used
        mock_strategy.extract_recommendation.assert_called_once_with(sample_recommendation_html)
        assert data["assessment_status"] == "Automated"

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_auto_detect_strategy(
        self, mock_detector, mock_session, mock_strategy, sample_recommendation_html
    ):
        """Test automatic strategy detection."""
        # Setup
        mock_detector.return_value = mock_strategy
        mock_response = Mock()
        mock_response.text = sample_recommendation_html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        # Create scraper without manual strategy
        scraper = WorkbenchScraper(mock_session)

        # Execute
        data = scraper.fetch_recommendation(
            "https://workbench.cisecurity.org/sections/1/recommendations/100"
        )

        # Verify auto-detection was called
        mock_detector.assert_called_once_with(sample_recommendation_html)
        mock_strategy.extract_recommendation.assert_called_once()

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_strategy_caching(
        self, mock_detector, mock_session, mock_strategy, sample_recommendation_html
    ):
        """Test that detected strategy is cached for subsequent calls."""
        # Setup
        mock_detector.return_value = mock_strategy
        mock_response = Mock()
        mock_response.text = sample_recommendation_html
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(mock_session)

        # Execute multiple fetches
        scraper.fetch_recommendation(
            "https://workbench.cisecurity.org/sections/1/recommendations/100"
        )
        scraper.fetch_recommendation(
            "https://workbench.cisecurity.org/sections/1/recommendations/101"
        )

        # Verify strategy detected only once (cached)
        assert mock_detector.call_count == 1


# ============ Test Full Benchmark Download ============


class TestWorkbenchScraperFullDownload:
    """Test complete benchmark download workflow."""

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_success(
        self,
        mock_detector,
        mock_session,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        sample_recommendation_html,
    ):
        """Test successful full benchmark download."""
        # Setup detector
        mock_detector.return_value = mock_strategy

        # Setup HTTP responses
        def mock_get(url, **kwargs):
            response = Mock()
            response.raise_for_status = Mock()

            if "navtree" in url:
                response.json.return_value = sample_benchmark_navtree
            elif "/benchmarks/" in url:
                response.text = sample_benchmark_title_html
            else:
                # Recommendation pages
                response.text = sample_recommendation_html

            return response

        mock_session.get.side_effect = mock_get

        scraper = WorkbenchScraper(mock_session)

        # Execute
        benchmark = scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        # Verify benchmark structure
        assert isinstance(benchmark, Benchmark)
        assert benchmark.benchmark_id == "18528"
        assert benchmark.title == "CIS Amazon Elastic Kubernetes Service (EKS) Benchmark v1.8.0"
        assert benchmark.version == "v1.8.0"
        assert benchmark.scraper_version == "v1_test"
        assert len(benchmark.recommendations) == 3
        assert benchmark.total_recommendations == 3

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_with_progress_callback(
        self,
        mock_detector,
        mock_session,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        sample_recommendation_html,
    ):
        """Test benchmark download with progress callback."""
        # Setup
        mock_detector.return_value = mock_strategy
        progress_messages = []

        def progress_callback(msg):
            progress_messages.append(msg)

        def mock_get(url, **kwargs):
            response = Mock()
            response.raise_for_status = Mock()

            if "navtree" in url:
                response.json.return_value = sample_benchmark_navtree
            elif "/benchmarks/" in url:
                response.text = sample_benchmark_title_html
            else:
                response.text = sample_recommendation_html

            return response

        mock_session.get.side_effect = mock_get

        scraper = WorkbenchScraper(mock_session)

        # Execute
        benchmark = scraper.download_benchmark(
            "https://workbench.cisecurity.org/benchmarks/18528", progress_callback=progress_callback
        )

        # Verify progress messages
        assert len(progress_messages) > 0
        assert any("Fetching benchmark" in msg for msg in progress_messages)
        assert any("Found 3 recommendations" in msg for msg in progress_messages)
        assert any("Successfully downloaded" in msg for msg in progress_messages)

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_handles_failed_recommendations(
        self,
        mock_detector,
        mock_session,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
    ):
        """Test that benchmark download continues when individual recommendations fail."""
        # Setup
        mock_detector.return_value = mock_strategy

        # Make strategy fail for some recommendations
        # Save the original mock's return_value before replacing with function
        successful_extraction = mock_strategy.extract_recommendation.return_value
        call_count = [0]

        def mock_extract(html):
            call_count[0] += 1
            if call_count[0] == 2:
                # Fail the second recommendation
                raise Exception("Extraction failed")
            return successful_extraction

        mock_strategy.extract_recommendation = Mock(side_effect=mock_extract)

        def mock_get(url, **kwargs):
            response = Mock()
            response.raise_for_status = Mock()

            if "navtree" in url:
                response.json.return_value = sample_benchmark_navtree
            elif "/benchmarks/" in url:
                response.text = sample_benchmark_title_html
            else:
                response.text = "<html>recommendation</html>"

            return response

        mock_session.get.side_effect = mock_get

        scraper = WorkbenchScraper(mock_session)

        # Execute
        benchmark = scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        # Verify - should have 2 recommendations (skipped the failed one)
        assert len(benchmark.recommendations) == 2
        assert benchmark.total_recommendations == 2

    def test_download_benchmark_version_extraction(self, mock_session):
        """Test version extraction from benchmark title."""
        # Setup various title formats
        test_cases = [
            ("CIS Benchmark v1.2.3", "v1.2.3"),
            ("CIS Benchmark v2.0", "v2.0"),
            ("CIS Benchmark vNEXT", "vNEXT"),
            ("CIS Benchmark (no version)", "v1.0.0"),  # fallback
        ]

        for title, expected_version in test_cases:
            html = f'<wb-benchmark-title title="{title}"></wb-benchmark-title>'
            navtree = {"navtree": []}

            def mock_get(url, **kwargs):
                response = Mock()
                response.raise_for_status = Mock()

                if "navtree" in url:
                    response.json.return_value = navtree
                else:
                    response.text = html

                return response

            mock_session.get.side_effect = mock_get

            scraper = WorkbenchScraper(mock_session)

            # Execute
            benchmark = scraper.download_benchmark(
                "https://workbench.cisecurity.org/benchmarks/123"
            )

            # Verify
            assert benchmark.version == expected_version


class TestExtendedMetadataExtraction:
    """Test extraction of extended metadata from benchmark detail pages."""

    def test_get_benchmark_metadata_all_fields(self, mock_session):
        """Test get_benchmark_metadata extracts all available fields."""
        html = """
        <html>
        <body>
            <wb-benchmark-title title="CIS AlmaLinux OS 9 Benchmark v2.0.0"></wb-benchmark-title>

            <h1>
                CIS AlmaLinux OS 9 Benchmark v2.0.0
                <a href="/benchmarks/16763">CIS Fedora 34 Benchmark</a>
            </h1>

            <p><a href="/communities/139">CIS AlmaLinux OS Benchmarks</a></p>
            <p><a href="/milestones/956">CIS AlmaLinux 9 v2.0.0</a></p>

            <p>Published 1 year ago on Jun 24th 2024</p>
            <p><strong>Release Type:</strong> Planned Update</p>

            <h3>Overview</h3>
            <p>Security guidance for AlmaLinux 9 systems.</p>

            <h3>Intended Audience</h3>
            <p>System administrators and security specialists.</p>

            <h3>Acknowledgements</h3>
            <p>Thanks to all Linux benchmark contributors.</p>

            <h3>Contributors</h3>
            <p>Eric Pinnell, Thomas Sjögren, James Trigg</p>

            <h3>Assets</h3>
            <table>
                <thead><tr><th>Title</th><th>CPE-ID</th></tr></thead>
                <tbody>
                    <tr>
                        <td>AlmaLinux OS 9</td>
                        <td>cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*</td>
                    </tr>
                </tbody>
            </table>

            <h3>Revision History</h3>
            <table>
                <tbody>
                    <tr>
                        <td>1 year ago</td>
                        <td>Eric</td>
                        <td>5 modifications</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        mock_session.get.return_value.text = html
        scraper = WorkbenchScraper(mock_session)

        metadata = scraper.get_benchmark_metadata(
            "https://workbench.cisecurity.org/benchmarks/18208"
        )

        # Verify all fields extracted
        assert metadata["title"] == "CIS AlmaLinux OS 9 Benchmark v2.0.0"
        assert metadata["published_date"] == "Jun 24th 2024"
        assert metadata["published_relative"] == "Published 1 year ago on Jun 24th 2024"
        assert metadata["release_type"] == "Planned Update"
        assert len(metadata["contributors"]) == 3
        assert "Eric Pinnell" in metadata["contributors"]
        assert "parent_benchmark_url" in metadata
        assert "community_url" in metadata
        assert metadata["intended_audience"] == "System administrators and security specialists."
        assert metadata["acknowledgements"] == "Thanks to all Linux benchmark contributors."
        assert len(metadata["assets"]) == 1
        assert metadata["assets"][0]["cpe_id"] == "cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"
        assert len(metadata["revision_history"]) == 1
        assert metadata["revision_history"][0]["author"] == "Eric"

    def test_download_benchmark_populates_extended_pydantic_fields(self, mock_session):
        """Test that download_benchmark populates all extended Pydantic model fields."""
        html = """
        <html>
        <body>
            <wb-benchmark-title title="CIS Test Benchmark v1.0.0"></wb-benchmark-title>
            <p>Published 3 months ago on Sep 1st 2024</p>
            <p><strong>Release Type:</strong> Bug Fix</p>
            <h3>Contributors</h3>
            <p>Developer One, Developer Two</p>
            <h3>Assets</h3>
            <table>
                <thead><tr><th>Title</th><th>CPE-ID</th></tr></thead>
                <tbody>
                    <tr><td>Test OS</td><td>cpe:2.3:o:test:test:1:*:*:*:*:*:*:*</td></tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        navtree = {"navtree": []}  # No recommendations for simplicity

        def mock_get(url, **kwargs):
            response = Mock()
            response.raise_for_status = Mock()

            if "navtree" in url:
                response.json.return_value = navtree
            else:
                response.text = html

            return response

        mock_session.get.side_effect = mock_get

        scraper = WorkbenchScraper(mock_session)
        benchmark = scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/99999")

        # Verify extended Pydantic fields populated
        assert benchmark.published_date == "Sep 1st 2024"
        assert benchmark.release_type == "Bug Fix"
        assert len(benchmark.contributors) == 2
        assert "Developer One" in benchmark.contributors
        assert len(benchmark.assets) == 1
        assert benchmark.assets[0].cpe_id == "cpe:2.3:o:test:test:1:*:*:*:*:*:*:*"
        assert benchmark.assets[0].title == "Test OS"
