"""Tests for CIS WorkBench scraper with strategy pattern support.

Tests WorkbenchScraper HTTP operations, navigation tree parsing, and recommendation extraction.
Uses real HTML samples from actual CIS WorkBench pages.
"""

import itertools
import json
import logging
import threading
import time
from unittest.mock import Mock, patch

import pytest
import requests
from requests.adapters import HTTPAdapter

from cis_bench.fetcher.http import session_for_worker
from cis_bench.fetcher.strategies.base import ScraperStrategy
from cis_bench.fetcher.workbench import WorkbenchScraper
from cis_bench.models.benchmark import Benchmark
from cis_bench.utils.parallel import parallel_execute
from cis_bench.utils.workbench_urls import navtree_url
from tests.conftest import LocalHTTPServer

BASE = "https://workbench.cisecurity.org"
TIMEOUT = (10.0, 30.0)
WORKERS = 5
BATCH = 10
LOGIN_PAGE = (
    '<html><body><div class="index-signin-wrapper"><form action="/login">'
    '<input name="login"><input name="password"></form></div></body></html>'
)

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute
        html = scraper.fetch_html("https://workbench.cisecurity.org/test")

        # Verify
        assert html == "<html><body>Test</body></html>"
        # Every request carries the configured (connect, read) timeout; verify comes from session.verify
        mock_session.get.assert_called_once_with(
            "https://workbench.cisecurity.org/test", timeout=(10.0, 30.0)
        )
        mock_response.raise_for_status.assert_called_once()

    def test_fetch_html_http_error(self, mock_session):
        """Test HTTP error handling."""
        # Setup - simulate 404 error
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute and verify
        with pytest.raises(requests.HTTPError, match="404 Not Found"):
            scraper.fetch_html("https://workbench.cisecurity.org/nonexistent")

    def test_fetch_html_403_forbidden(self, mock_session):
        """Test 403 Forbidden error (auth failure)."""
        # Setup
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("403 Forbidden")
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute and verify
        with pytest.raises(requests.HTTPError, match="403 Forbidden"):
            scraper.fetch_html("https://workbench.cisecurity.org/benchmarks/123")

    def test_fetch_html_times_out_instead_of_hanging(self, mock_session):
        """Every request carries the configured timeout, and a timeout fails loudly.

        Before this, fetch_html called session.get with no timeout at all, so one
        stalled connection hung a 322-recommendation download for over an hour. The
        retries happen in the session's adapter (tests/integration/test_fetcher_http.py).
        """
        from cis_bench.exceptions import FetchError

        mock_session.get.side_effect = requests.Timeout("Request timed out")
        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(FetchError, match="https://workbench.cisecurity.org/slow") as exc_info:
            scraper.fetch_html("https://workbench.cisecurity.org/slow")

        assert mock_session.get.call_args.kwargs["timeout"] == (10.0, 30.0)
        assert isinstance(exc_info.value.__cause__, requests.Timeout)
        assert exc_info.value.url == "https://workbench.cisecurity.org/slow"

    def test_a_transient_status_left_after_the_retries_is_a_typed_error(self):
        """Through the real WorkBench adapter: the retries run, then FetchError counts them."""
        from cis_bench.config import RequestPolicy
        from cis_bench.exceptions import FetchError
        from cis_bench.fetcher.http import new_workbench_session
        from tests.conftest import LocalHTTPServer

        arrivals = []

        def always_503(handler):
            arrivals.append(handler.path)
            handler.send_response(503)
            handler.send_header("Content-Length", "0")
            handler.end_headers()

        policy = RequestPolicy(
            requests_per_second=50.0, retries=2, backoff_factor=0.0, jitter_seconds=0.0
        )
        with LocalHTTPServer(always_503) as server:
            scraper = WorkbenchScraper(
                new_workbench_session(policy),
                base_url=server.base_url,
                timeout=TIMEOUT,
                max_workers=WORKERS,
                batch_size=BATCH,
            )
            with pytest.raises(FetchError, match="HTTP 503 after 3 attempts"):
                scraper.fetch_html(server.base_url + "/down")

        assert len(arrivals) == 3

    def test_a_login_page_is_an_authentication_error_not_a_retry(self, mock_session):
        """WorkBench answers an expired session with a 200 login page; that is final, not transient."""
        from cis_bench.exceptions import AuthenticationError

        login = Mock()
        login.status_code = 200
        login.raise_for_status = Mock()
        login.text = (
            '<html><body><div class="index-signin-wrapper"><form action="/login">'
            '<input name="login"><input name="password"></form></div></body></html>'
        )
        mock_session.get.return_value = login
        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(AuthenticationError):
                scraper.fetch_html("https://workbench.cisecurity.org/sections/1/recommendations/1")
        assert mock_session.get.call_count == 1
        mock_sleep.assert_not_called()

    def test_fetch_html_does_not_retry_client_errors(self, mock_session):
        """A 404 or 403 is final: one request, the HTTPError propagates unchanged."""
        not_found = Mock()
        not_found.status_code = 404
        not_found.raise_for_status.side_effect = requests.HTTPError(
            "404 Not Found", response=not_found
        )
        mock_session.get.return_value = not_found
        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(requests.HTTPError, match="404"):
                scraper.fetch_html("https://workbench.cisecurity.org/missing")

        assert mock_session.get.call_count == 1
        mock_sleep.assert_not_called()

    def test_fetch_html_connection_error_is_typed(self, mock_session):
        from cis_bench.exceptions import FetchError

        mock_session.get.side_effect = requests.ConnectionError("connection reset")
        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(FetchError, match="https://workbench.cisecurity.org/reset"):
            scraper.fetch_html("https://workbench.cisecurity.org/reset")

    def test_every_request_uses_the_timeout_the_scraper_is_given(self, mock_session):
        mock_session.get.return_value = Mock(text="<html></html>", raise_for_status=Mock())
        WorkbenchScraper(
            mock_session, base_url=BASE, timeout=(2.0, 7.0), max_workers=WORKERS, batch_size=BATCH
        ).fetch_html(f"{BASE}/x")
        assert mock_session.get.call_args.kwargs["timeout"] == (2.0, 7.0)

    def test_fetch_json_uses_the_same_timeout(self, mock_session):
        from cis_bench.exceptions import FetchError

        mock_session.get.side_effect = requests.Timeout("Request timed out")
        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(FetchError):
            scraper.fetch_json("https://workbench.cisecurity.org/api/v1/benchmarks/1/navtree")
        assert mock_session.get.call_args.kwargs["timeout"] == (10.0, 30.0)

    def test_fetch_json_success(self, mock_session):
        """Test successful JSON fetch."""
        # Setup
        test_data = {"key": "value", "nested": {"data": 123}}
        mock_response = Mock()
        mock_response.json.return_value = test_data
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute
        data = scraper.fetch_json("https://workbench.cisecurity.org/api/test")

        # Verify
        assert data == test_data
        mock_session.get.assert_called_once_with(
            "https://workbench.cisecurity.org/api/test", timeout=(10.0, 30.0)
        )

    def test_fetch_json_invalid_response(self, mock_session):
        """Test handling of invalid JSON response."""
        # Setup
        mock_response = Mock()
        # What a real Response raises for a body that is not JSON
        mock_response.json.side_effect = requests.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.text = "not json"
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute and verify
        with pytest.raises(
            ValueError, match="^Expected JSON from https://workbench.cisecurity.org/api/bad"
        ):
            scraper.fetch_json("https://workbench.cisecurity.org/api/bad")

    def test_fetch_json_non_object_raises_value_error(self, mock_session):
        """fetch_json rejects non-dict JSON payloads instead of silently returning lists or scalars."""
        mock_response = Mock()
        mock_response.json.return_value = ["unexpected", "list"]
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(ValueError, match="Expected JSON object"):
            scraper.fetch_json("https://workbench.cisecurity.org/api/list")


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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute
        title = scraper.get_benchmark_title("https://workbench.cisecurity.org/benchmarks/123")

        # Verify - empty string is returned
        assert title == ""


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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute
        navtree = scraper.fetch_navtree("18528")

        # Verify
        assert navtree == sample_benchmark_navtree
        mock_session.get.assert_called_once_with(
            "https://workbench.cisecurity.org/api/v1/benchmarks/18528/navtree", timeout=(10.0, 30.0)
        )

    def test_a_login_page_at_the_navtree_is_an_authentication_error(self, stub_session):
        """An expired session gets the login page (HTML, status 200) where the navtree JSON is due."""
        from cis_bench.exceptions import AuthenticationError

        session, _ = stub_session(lambda url: LOGIN_PAGE)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )
        url = navtree_url("23598", base_url=BASE)

        with pytest.raises(AuthenticationError) as raised:
            scraper.fetch_navtree("23598")

        assert str(raised.value) == (
            f"WorkBench returned the login page for {url}; the saved session has expired"
        )

    def test_a_navtree_answer_that_is_not_json_is_an_error_naming_the_url(self, stub_session):
        session, _ = stub_session(lambda url: "<html><body>Down for maintenance</body></html>")
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )
        url = navtree_url("23598", base_url=BASE)

        with pytest.raises(ValueError) as raised:
            scraper.fetch_navtree("23598")

        assert str(raised.value).startswith(f"Expected JSON from {url}, ")
        assert not isinstance(raised.value, json.JSONDecodeError)

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute
        parsed = scraper.parse_navtree(navtree_data)

        # Verify
        assert len(parsed) == 1
        assert parsed[0]["url"] == "https://workbench.cisecurity.org/sections/1/recommendations/100"
        assert parsed[0]["title"] == "Test Recommendation"
        assert parsed[0]["ref"] == "1.1"

    def test_parse_navtree_nested_structure(self, mock_session, sample_benchmark_navtree):
        """Test parsing navtree with nested subsections."""
        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        # Execute
        parsed = scraper.parse_navtree(navtree_data)

        # Verify - gets nested first, then top-level
        assert len(parsed) == 2

    def test_navtree_urls_use_the_given_origin(self, mock_session, sample_benchmark_navtree):
        """fetch_navtree and parse_navtree build URLs on the origin the scraper is given."""
        mock_response = Mock()
        mock_response.json.return_value = sample_benchmark_navtree
        mock_response.raise_for_status = Mock()
        mock_session.get.return_value = mock_response

        scraper = WorkbenchScraper(
            mock_session,
            base_url="https://workbench-staging.cisecurity.org",
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )
        navtree = scraper.fetch_navtree("61")
        parsed = scraper.parse_navtree(navtree)

        mock_session.get.assert_called_once_with(
            "https://workbench-staging.cisecurity.org/api/v1/benchmarks/61/navtree",
            timeout=(10.0, 30.0),
        )
        assert (
            parsed[0]["url"]
            == "https://workbench-staging.cisecurity.org/sections/3511915/recommendations/5772605"
        )


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
        scraper = WorkbenchScraper(
            mock_session,
            strategy=mock_strategy,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

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
        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

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

        scraper = WorkbenchScraper(
            mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

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


def _navtree_with(count):
    """A flat navtree with count recommendations, refs 1.1 .. 1.<count>."""
    return {
        "navtree": [
            {
                "id": 1,
                "title": "Section 1",
                "view_level": "1",
                "subsections_for_nav_tree": None,
                "recommendations_for_nav_tree": [
                    {"id": 1000 + n, "section_id": 1, "title": f"Rec {n}", "view_level": f"1.{n}"}
                    for n in range(1, count + 1)
                ],
            }
        ]
    }


# The status block of a published benchmark's page, in the shape WorkBench renders it: the
# label in its own <p>, the date as a bare text node after it.
PUBLISHED_STATUS_HTML = """
<div class="object-status" data-cy="benchmark-status-label">
    <p class="label label-published">Published</p>
        1 year ago on Aug 28th 2025
</div>
"""


class TestTheReleasePublishDate:
    """A download reads the release's publish date from the page it fetches for the title."""

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_records_the_publish_date_from_the_one_page_fetch(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        sample_recommendation_html,
        stub_session,
    ):
        from datetime import date

        mock_detector.return_value = mock_strategy
        page = sample_benchmark_title_html.replace(
            "</body>", PUBLISHED_STATUS_HTML + OVERVIEW_COMPONENT_HTML + "</body>"
        )
        url = "https://workbench.cisecurity.org/benchmarks/18528"

        def handler(requested):
            if "navtree" in requested:
                return sample_benchmark_navtree
            if requested == url:
                return page
            return sample_recommendation_html

        session, transport = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        benchmark = scraper.download_benchmark(url)

        assert benchmark.published_date == date(2025, 8, 28)
        assert benchmark.title == "CIS Amazon Elastic Kubernetes Service (EKS) Benchmark v1.8.0"
        assert transport.urls.count(url) == 1
        assert '"published_date":"2025-08-28"' in benchmark.model_dump_json()
        assert benchmark.description.startswith("This document provides prescriptive guidance")

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_a_page_without_a_publish_date_records_none(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        sample_recommendation_html,
        stub_session,
    ):
        mock_detector.return_value = mock_strategy

        def handler(requested):
            if "navtree" in requested:
                return sample_benchmark_navtree
            if "/benchmarks/" in requested:
                return sample_benchmark_title_html
            return sample_recommendation_html

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        benchmark = scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        assert benchmark.published_date is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 year ago on Aug 28th 2025", "2025-08-28"),
        ("4 years ago on Jun 21st 2022", "2022-06-21"),
        ("2 months ago on September 9th 2025", "2025-09-09"),
        ("3 days ago on Feb 3rd 2026", "2026-02-03"),
        ("1 day ago on Mar 2nd 2026", "2026-03-02"),
        ("1 year ago on Aug 1st 2025", "2025-08-01"),
        ("1 year ago on Dec 22nd 2024", "2024-12-22"),
        ("3 years ago on Mar 3rd 2023", "2023-03-03"),
        ("Published 1 day ago on Jan 1st 2026", "2026-01-01"),
        ("Published 2 months ago on Feb 22nd 2025", "2025-02-22"),
        ("Published 1 year ago on Mar 3rd 2024", "2024-03-03"),
        ("Published just now ago on Apr 4th 2025", "2025-04-04"),
        ("ago on Feb 30th 2025", None),
        ("ago on Aug 32nd 2025", None),
        ("ago on Smarch 1st 2025", None),
        ("yesterday", None),
        ("2 weeks ago", None),
        ("Published 2 weeks ago", None),
        ("Published", None),
    ],
)
def test_the_publish_date_is_read_from_the_status_text(text, expected):
    from cis_bench.fetcher.workbench import parse_benchmark_page

    page = parse_benchmark_page(
        f'<div data-cy="benchmark-status-label"><p>Published</p>{text}</div>'
    )

    assert (page.published_date.isoformat() if page.published_date else None) == expected


def test_a_draft_label_with_a_date_and_an_empty_page():
    import warnings

    from cis_bench.fetcher.workbench import parse_benchmark_page

    draft = PUBLISHED_STATUS_HTML.replace("label-published", "label-draft").replace(
        ">Published<", ">Draft<"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert parse_benchmark_page(draft).published_date.isoformat() == "2025-08-28"
        empty = parse_benchmark_page("")
    assert (empty.title, empty.published_date, empty.description) == (
        "Unknown Benchmark",
        None,
        None,
    )


# The overview as WorkBench renders it: a web component whose text attribute holds it
OVERVIEW_COMPONENT_HTML = """
<wb-recommendation-data attribute="intended_audience" text="Administrators."></wb-recommendation-data>
<wb-recommendation-data
        attribute="overview"
        :can-see-warning="false"
        text="This document provides prescriptive guidance for establishing a secure
configuration posture for AlmaLinux OS 8 Linux systems.

The guidance &lt;strong&gt;assumes&lt;/strong&gt; root &amp;amp; bash."></wb-recommendation-data>
"""


class TestTheBenchmarkDescription:
    """The description is the benchmark page's overview, as plain text."""

    def test_the_overview_component_is_the_description(self):
        from cis_bench.fetcher.workbench import parse_benchmark_page

        page = parse_benchmark_page(PUBLISHED_STATUS_HTML + OVERVIEW_COMPONENT_HTML)

        assert page.description == (
            "This document provides prescriptive guidance for establishing a secure\n"
            "configuration posture for AlmaLinux OS 8 Linux systems.\n\n"
            "The guidance assumes root & bash."
        )
        assert page.published_date.isoformat() == "2025-08-28"

    def test_the_component_wins_over_an_overview_heading(self):
        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = OVERVIEW_COMPONENT_HTML + "<h2>Overview</h2><p>Heading text.</p>"

        assert parse_benchmark_page(html).description.startswith("This document provides")

    def test_parse_benchmark_detail_basic(self):
        """Test basic benchmark detail page parsing."""
        from datetime import date

        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <h1>CIS Ubuntu 22.04 Benchmark</h1>
            <p>Published 3 months ago on Aug 1st 2025</p>
            <h2>Overview</h2>
            <p>This benchmark provides security guidance.</p>
            <p>It covers essential hardening steps.</p>
            <p>Use this for compliance.</p>
            <h2>Recommendations</h2>
            <p>Different section content.</p>
        </body>
        </html>
        """
        page = parse_benchmark_page(html)

        assert page.published_date == date(2025, 8, 1)
        assert "security guidance" in page.description
        assert "hardening steps" in page.description

    def test_parse_benchmark_detail_no_published_date(self):
        """Test parsing when no published date is present."""
        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <h2>Overview</h2>
            <p>Some description text.</p>
        </body>
        </html>
        """
        page = parse_benchmark_page(html)

        assert page.published_date is None
        assert page.description == "Some description text."

    def test_parse_benchmark_detail_no_overview(self):
        """Test parsing when no Overview section is present."""
        from datetime import date

        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <p>Published 1 month ago on Dec 15th 2025</p>
            <h2>Recommendations</h2>
            <p>Some recommendations.</p>
        </body>
        </html>
        """
        page = parse_benchmark_page(html)

        assert page.published_date == date(2025, 12, 15)
        assert page.description is None

    def test_parse_benchmark_detail_empty_overview_section(self):
        """Test parsing when Overview heading exists but no content follows."""
        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <h2>Overview</h2>
            <h2>Next Section</h2>
            <p>Content in next section.</p>
        </body>
        </html>
        """

        assert parse_benchmark_page(html).description is None

    def test_parse_benchmark_detail_published_without_specific_date(self):
        """Published text without an "on DATE" part gives no date; the description is still read."""
        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <p>Published 2 weeks ago</p>
            <h2>Overview</h2>
            <p>Description text.</p>
        </body>
        </html>
        """
        page = parse_benchmark_page(html)

        assert page.published_date is None
        assert page.description == "Description text."

    def test_parse_benchmark_detail_multiple_paragraphs_limited(self):
        """Test description is limited to first 3 paragraphs."""
        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <h2>Overview</h2>
            <p>First paragraph.</p>
            <p>Second paragraph.</p>
            <p>Third paragraph.</p>
            <p>Fourth paragraph should not be included.</p>
            <p>Fifth paragraph should not be included.</p>
        </body>
        </html>
        """
        description = parse_benchmark_page(html).description

        assert "First paragraph" in description
        assert "Second paragraph" in description
        assert "Third paragraph" in description
        assert "Fourth paragraph" not in description
        assert "Fifth paragraph" not in description

    def test_parse_benchmark_detail_stops_at_next_heading(self):
        """Test description stops at next heading."""
        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <h2>Overview</h2>
            <p>First overview paragraph.</p>
            <h3>Subsection</h3>
            <p>Should not be included.</p>
            <h2>Recommendations</h2>
            <p>Different section.</p>
        </body>
        </html>
        """
        description = parse_benchmark_page(html).description

        assert "First overview paragraph" in description
        assert "Should not be included" not in description

    def test_parse_benchmark_detail_overview_with_empty_paragraphs(self):
        """Test description handles empty paragraph elements."""
        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <h2>Overview</h2>
            <p></p>
            <p>   </p>
            <p>Actual content.</p>
            <p>More content.</p>
        </body>
        </html>
        """

        assert parse_benchmark_page(html).description == "Actual content. More content."

    def test_parse_benchmark_detail_emits_no_deprecation_warnings(self):
        """Detail page parsing reads the published date and overview without deprecations."""
        import warnings
        from datetime import date

        from cis_bench.fetcher.workbench import parse_benchmark_page

        html = """
        <html>
        <body>
            <p>Published 3 months ago on Aug 1st 2025</p>
            <h2>Overview</h2>
            <p>Hardening guidance for servers.</p>
        </body>
        </html>
        """
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            page = parse_benchmark_page(html)

        assert (page.published_date, page.description) == (
            date(2025, 8, 1),
            "Hardening guidance for servers.",
        )


class TestCloudflareAddressesOnWorkBenchPages:
    """Pages read through the scraper carry real addresses, whatever Cloudflare did to them."""

    CF_INFO = "9df4f3fbf2ddf8e5fcf0edf1f8b3fef2f0"  # info@example.com

    def test_fetch_html_returns_the_page_with_addresses_decoded(self, stub_session):
        page = f'<p>Mail <a class="__cf_email__" data-cfemail="{self.CF_INFO}">[email&#160;protected]</a></p>'
        session, _ = stub_session(lambda url: page)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        html = scraper.fetch_html("https://workbench.cisecurity.org/sections/1/recommendations/2")

        assert html == "<p>Mail info@example.com</p>"


class TestCloudflareAddressesInADownload:
    """A download stores real addresses in the benchmark and its recommendations."""

    CF_INFO = "9df4f3fbf2ddf8e5fcf0edf1f8b3fef2f0"  # info@example.com
    CF_FEEDBACK = "42242727262023212902212b31272137302b363b6c2d3025"  # feedback@cisecurity.org

    def test_the_stored_benchmark_carries_the_real_addresses(
        self, sample_benchmark_navtree, sample_recommendation_html, stub_session
    ):
        url = "https://workbench.cisecurity.org/benchmarks/18528"
        benchmark_page = (
            '<wb-benchmark-title title="CIS Amazon EKS Benchmark v1.8.0"></wb-benchmark-title>'
            "<h2>Overview</h2>"
            f'<p>Write us at <a href="/cdn-cgi/l/email-protection" class="__cf_email__" '
            f'data-cfemail="{self.CF_FEEDBACK}">[email&#160;protected]</a>.</p>'
        )
        # WorkBench links the parent recommendation by its full URL
        recommendation_page = sample_recommendation_html.replace(
            'href="/sections/123/recommendations/456"',
            'href="https://workbench.cisecurity.org/sections/123/recommendations/456"',
        ).replace(
            "ensure that the proxy kubeconfig file",
            f'mail <a href="/cdn-cgi/l/email-protection#{self.CF_INFO}">'
            f'<span class="__cf_email__" data-cfemail="{self.CF_INFO}">[email&#160;protected]</span>'
            "</a> and ensure that the proxy kubeconfig file",
        )

        def handler(requested):
            if "navtree" in requested:
                return sample_benchmark_navtree
            if requested == url:
                return benchmark_page
            return recommendation_page

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        benchmark = scraper.download_benchmark(url)

        assert benchmark.description == "Write us at feedback@cisecurity.org."
        stored = benchmark.model_dump_json()
        assert '<a href=\\"mailto:info@example.com\\">info@example.com</a>' in stored
        assert "protected" not in stored and "cfemail" not in stored


class TestWorkbenchScraperFullDownload:
    """Test complete benchmark download workflow."""

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_success(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        sample_recommendation_html,
        stub_session,
    ):
        """Test successful full benchmark download."""
        mock_detector.return_value = mock_strategy

        def handler(url):
            if "navtree" in url:
                return sample_benchmark_navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            return sample_recommendation_html

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        benchmark = scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        assert isinstance(benchmark, Benchmark)
        assert benchmark.benchmark_id == "18528"
        assert benchmark.title == "CIS Amazon Elastic Kubernetes Service (EKS) Benchmark v1.8.0"
        assert benchmark.version == "v1.8.0"
        assert benchmark.scraper_version == "v1_test"
        assert len(benchmark.recommendations) == 3
        assert benchmark.total_recommendations == 3
        assert benchmark.downloaded_at.tzinfo is not None
        assert benchmark.downloaded_at.utcoffset().total_seconds() == 0

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_the_recommendation_fetch_runs_with_the_given_workers_and_batch_size(
        self,
        mock_detector,
        mock_strategy,
        stub_session,
        sample_benchmark_navtree,
        sample_benchmark_title_html,
        sample_recommendation_html,
    ):
        from cis_bench.fetcher import workbench as workbench_module

        mock_detector.return_value = mock_strategy

        def handler(url):
            if "navtree" in url:
                return sample_benchmark_navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            return sample_recommendation_html

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=2, batch_size=3
        )
        with patch.object(
            workbench_module,
            "parallel_execute_batched",
            wraps=workbench_module.parallel_execute_batched,
        ) as run:
            scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        assert run.call_args.kwargs["max_workers"] == 2
        assert run.call_args.kwargs["batch_size"] == 3

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_with_progress_callback(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        sample_recommendation_html,
        stub_session,
    ):
        """Test benchmark download with progress callback."""
        mock_detector.return_value = mock_strategy
        progress_messages = []

        def handler(url):
            if "navtree" in url:
                return sample_benchmark_navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            return sample_recommendation_html

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        scraper.download_benchmark(
            "https://workbench.cisecurity.org/benchmarks/18528",
            progress_callback=progress_messages.append,
        )

        assert len(progress_messages) > 0
        assert any("Fetching benchmark" in msg for msg in progress_messages)
        assert any("Found 3 recommendations" in msg for msg in progress_messages)
        assert any("Successfully downloaded" in msg for msg in progress_messages)

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_handles_failed_recommendations(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        stub_session,
    ):
        """Test that benchmark download continues when individual recommendations fail."""
        mock_detector.return_value = mock_strategy

        # Make strategy fail for some recommendations
        # Save the original mock's return_value before replacing with function
        successful_extraction = mock_strategy.extract_recommendation.return_value
        call_count = [0]
        count_lock = threading.Lock()

        def mock_extract(html):
            with count_lock:
                call_count[0] += 1
                this_call = call_count[0]
            if this_call == 2:
                # Fail the second recommendation
                raise Exception("Extraction failed")
            return successful_extraction

        mock_strategy.extract_recommendation = Mock(side_effect=mock_extract)

        def handler(url):
            if "navtree" in url:
                return sample_benchmark_navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            return "<html>recommendation</html>"

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        benchmark = scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        # Verify - should have 2 recommendations (skipped the failed one)
        assert len(benchmark.recommendations) == 2
        assert benchmark.total_recommendations == 2

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_skips_a_recommendation_that_keeps_timing_out(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        caplog,
        stub_session,
    ):
        """One stalled recommendation costs that recommendation, not the whole download."""
        mock_detector.return_value = mock_strategy
        stalled_url = WorkbenchScraper(
            requests.Session(),
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        ).parse_navtree(sample_benchmark_navtree)[0]["url"]

        def handler(url):
            if url == stalled_url:
                raise requests.Timeout("Read timed out")
            if "navtree" in url:
                return sample_benchmark_navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            return "<html>recommendation</html>"

        session, transport = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with (
            caplog.at_level(logging.ERROR, logger="cis_bench.fetcher.workbench"),
        ):
            benchmark = scraper.download_benchmark(
                "https://workbench.cisecurity.org/benchmarks/18528"
            )

        assert len(benchmark.recommendations) == 2
        assert benchmark.total_recommendations == 2
        errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
        assert any(stalled_url in line and "timed out" in line for line in errors), errors

    @pytest.mark.parametrize(
        ("make_error", "detail"),
        [
            (lambda url: requests.Timeout("Read timed out"), "Read timed out"),
            (
                lambda url: requests.HTTPError(f"404 Client Error: Not Found for url: {url}"),
                "404 Client Error",
            ),
            (lambda url: RuntimeError("page could not be read"), "page could not be read"),
        ],
        ids=["error-that-starts-with-the-url", "error-that-ends-with-the-url", "error-without-it"],
    )
    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_the_failure_line_names_the_recommendation_url_exactly_once(
        self,
        mock_detector,
        make_error,
        detail,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        caplog,
        stub_session,
    ):
        mock_detector.return_value = mock_strategy
        failed_url = WorkbenchScraper(
            requests.Session(),
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        ).parse_navtree(sample_benchmark_navtree)[0]["url"]

        def handler(url):
            if url == failed_url:
                raise make_error(url)
            if "navtree" in url:
                return sample_benchmark_navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            return "<html>recommendation</html>"

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with caplog.at_level(logging.ERROR, logger="cis_bench.fetcher.workbench"):
            scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        lines = [
            r.getMessage()
            for r in caplog.records
            if r.name == "cis_bench.fetcher.workbench" and r.levelno == logging.ERROR
        ]
        assert len(lines) == 1, lines
        assert lines[0].startswith("Failed to fetch ")
        assert lines[0].count(failed_url) == 1, lines[0]
        assert detail in lines[0]

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_aborts_when_the_session_expires(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        stub_session,
    ):
        """A login page mid-download means every further fetch would fail: the download
        raises, and no recommendation after the batch that saw the login page is requested."""
        from cis_bench.exceptions import AuthenticationError

        mock_detector.return_value = mock_strategy
        navtree = _navtree_with(25)
        rec_urls = [
            r["url"]
            for r in WorkbenchScraper(
                requests.Session(),
                base_url=BASE,
                timeout=TIMEOUT,
                max_workers=WORKERS,
                batch_size=BATCH,
            ).parse_navtree(navtree)
        ]
        expired_url = rec_urls[1]
        login_html = (
            '<html><body><div class="index-signin-wrapper"><form action="/login">'
            '<input name="login"><input name="password"></form></div></body></html>'
        )

        def handler(url):
            if "navtree" in url:
                return navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            if url == expired_url:
                return login_html
            return "<html>recommendation</html>"

        session, transport = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with pytest.raises(AuthenticationError):
            scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        assert transport.urls.count(expired_url) == 1
        later_batches = set(rec_urls[10:])
        assert later_batches.isdisjoint(transport.urls)

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_download_benchmark_fetches_recommendations_concurrently_in_ref_order(
        self, mock_detector, mock_strategy, sample_benchmark_title_html, stub_session
    ):
        mock_detector.return_value = mock_strategy
        navtree = _navtree_with(12)
        rec_urls = [
            r["url"]
            for r in WorkbenchScraper(
                requests.Session(),
                base_url=BASE,
                timeout=TIMEOUT,
                max_workers=WORKERS,
                batch_size=BATCH,
            ).parse_navtree(navtree)
        ]

        def handler(url):
            if "navtree" in url:
                return navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            # Earlier recommendations answer more slowly, so completion order differs.
            time.sleep(0.01 * (len(rec_urls) - rec_urls.index(url)))
            return "<html>recommendation</html>"

        session, transport = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        benchmark = scraper.download_benchmark("https://workbench.cisecurity.org/benchmarks/18528")

        assert [r.ref for r in benchmark.recommendations] == [f"1.{n}" for n in range(1, 13)]
        assert benchmark.total_recommendations == 12
        assert 2 <= transport.peak_in_flight <= 5

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_progress_reports_each_recommendation_after_it_is_fetched(
        self, mock_detector, mock_strategy, sample_benchmark_title_html, stub_session
    ):
        mock_detector.return_value = mock_strategy
        navtree = _navtree_with(12)
        finished = [0]
        finished_lock = threading.Lock()

        def handler(url):
            if "navtree" in url:
                return navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            time.sleep(0.005)
            with finished_lock:
                finished[0] += 1
            return "<html>recommendation</html>"

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )
        messages = []

        def on_progress(msg):
            with finished_lock:
                messages.append((msg, finished[0]))

        scraper.download_benchmark(
            "https://workbench.cisecurity.org/benchmarks/18528", progress_callback=on_progress
        )

        texts = [msg for msg, _ in messages]
        assert any(t.startswith("Benchmark title: ") for t in texts)
        assert "Found 12 recommendations" in texts
        counted = [(msg, done) for msg, done in messages if msg.startswith("[")]
        assert [msg.split("]")[0] for msg, _ in counted] == [f"[{n}/12" for n in range(1, 13)]
        for n, (msg, done) in enumerate(counted, start=1):
            assert done >= n, f"{msg!r} was reported before {n} fetches had finished"
            assert " Fetching 1." in msg

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_a_failed_recommendation_is_logged_once_with_its_url_and_error(
        self, mock_detector, mock_strategy, sample_benchmark_title_html, caplog, stub_session
    ):
        mock_detector.return_value = mock_strategy
        navtree = _navtree_with(12)
        rec_urls = [
            r["url"]
            for r in WorkbenchScraper(
                requests.Session(),
                base_url=BASE,
                timeout=TIMEOUT,
                max_workers=WORKERS,
                batch_size=BATCH,
            ).parse_navtree(navtree)
        ]
        broken_url = rec_urls[4]

        def handler(url):
            if "navtree" in url:
                return navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            if url == broken_url:
                raise requests.ConnectionError("connection reset")
            return "<html>recommendation</html>"

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with (
            caplog.at_level(logging.ERROR, logger="cis_bench.fetcher.workbench"),
        ):
            benchmark = scraper.download_benchmark(
                "https://workbench.cisecurity.org/benchmarks/18528"
            )

        assert [r.ref for r in benchmark.recommendations] == [
            f"1.{n}" for n in range(1, 13) if n != 5
        ]
        errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
        about_broken = [line for line in errors if broken_url in line]
        assert len(about_broken) == 1, errors
        assert "connection reset" in about_broken[0]

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_the_cli_progress_bar_counts_every_fetched_recommendation(
        self, mock_detector, mock_strategy, sample_benchmark_title_html, stub_session
    ):
        from cis_bench.cli.helpers.download_helper import download_with_progress

        mock_detector.return_value = mock_strategy
        navtree = _navtree_with(12)

        def handler(url):
            if "navtree" in url:
                return navtree
            if "/benchmarks/" in url:
                return sample_benchmark_title_html
            return "<html>recommendation</html>"

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with (
            patch("cis_bench.cli.helpers.download_helper.Progress") as progress_class,
        ):
            benchmark = download_with_progress(
                scraper, "https://workbench.cisecurity.org/benchmarks/18528"
            )

        bar = progress_class.return_value
        assert bar.add_task.call_args.kwargs["total"] == 12
        completed = [c.kwargs["completed"] for c in bar.update.call_args_list]
        assert completed == list(range(1, 13))
        bar.stop.assert_called_once()
        assert benchmark.total_recommendations == 12

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

            scraper = WorkbenchScraper(
                mock_session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
            )

            # Execute
            benchmark = scraper.download_benchmark(
                "https://workbench.cisecurity.org/benchmarks/123"
            )

            # Verify
            assert benchmark.version == expected_version


# ============ Test Concurrent Fetches ============


class _RotatingCookieServer(LocalHTTPServer):
    """Local HTTP server that, like WorkBench, re-issues the session cookie on every response
    and records the cookies each request carried."""

    def __init__(self, page_html: str):
        self.page_html = page_html.encode()
        self.cookie_headers: list[str] = []
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        super().__init__(self._respond)

    def _respond(self, handler):
        with self._lock:
            self.cookie_headers.append(handler.headers.get("Cookie", ""))
            rotation = next(self._counter)
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html")
        handler.send_header("Set-Cookie", f"workbench_session=rotated-{rotation}; Path=/")
        handler.send_header("Set-Cookie", f"XSRF-TOKEN=xsrf-{rotation}; Path=/")
        handler.send_header("Content-Length", str(len(self.page_html)))
        handler.end_headers()
        handler.wfile.write(self.page_html)


class _VerifyRecordingAdapter(HTTPAdapter):
    """Transport that records the verify setting every request was sent with."""

    def __init__(self):
        super().__init__()
        self.verify_seen: list[object] = []
        self._lock = threading.Lock()

    def send(self, request, **kwargs):
        with self._lock:
            self.verify_seen.append(kwargs.get("verify"))
        return super().send(request, **kwargs)


@pytest.fixture
def saved_session(tmp_path):
    """A session as AuthManager loads it: saved cookies plus a configured verify setting."""
    session = requests.Session()
    session.verify = str(tmp_path / "corporate-ca.pem")
    session.cookies.set("auth0", "saved-auth", domain="127.0.0.1", path="/")
    session.cookies.set("workbench_session", "saved-session", domain="127.0.0.1", path="/")
    adapter = _VerifyRecordingAdapter()
    session.mount("http://", adapter)
    return session, adapter


class TestWorkbenchScraperConcurrentFetches:
    """Recommendations fetched from several threads at once."""

    THREADS = 5
    FETCHES = 50

    def _fetch_concurrently(self, scraper, server):
        urls = [f"{server.base_url}/sections/1/recommendations/{n}" for n in range(self.FETCHES)]
        return parallel_execute(urls, scraper.fetch_recommendation, max_workers=self.THREADS)

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_concurrent_recommendation_fetches_share_auth_without_races(
        self, mock_detector, saved_session, mock_strategy, sample_recommendation_html
    ):
        session, adapter = saved_session
        mock_detector.return_value = mock_strategy
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with _RotatingCookieServer(sample_recommendation_html) as server:
            result = self._fetch_concurrently(scraper, server)

        assert result.failed == []
        assert len(result.results) == self.FETCHES
        assert len(server.cookie_headers) == self.FETCHES
        for sent in server.cookie_headers:
            cookies = dict(part.split("=", 1) for part in sent.split("; "))
            assert cookies.get("auth0") == "saved-auth"
            assert cookies.get("workbench_session", "").startswith(("saved-", "rotated-"))
        assert adapter.verify_seen == [session.verify] * self.FETCHES

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_worker_threads_never_write_the_callers_session(
        self, mock_detector, saved_session, mock_strategy, sample_recommendation_html
    ):
        session, _ = saved_session
        mock_detector.return_value = mock_strategy
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with _RotatingCookieServer(sample_recommendation_html) as server:
            result = self._fetch_concurrently(scraper, server)

        assert result.failed == []
        # Every response rotated the session cookie, but only in the workers' own sessions.
        assert session.cookies.get("workbench_session") == "saved-session"
        assert session.cookies.get("XSRF-TOKEN") is None

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_strategy_is_detected_once_across_threads(
        self, mock_detector, saved_session, mock_strategy, sample_recommendation_html
    ):
        session, _ = saved_session

        def slow_detection(html):
            time.sleep(0.05)  # widen the window in which threads could detect at the same time
            return mock_strategy

        mock_detector.side_effect = slow_detection
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        with _RotatingCookieServer(sample_recommendation_html) as server:
            result = self._fetch_concurrently(scraper, server)

        assert result.failed == []
        assert mock_detector.call_count == 1

    def test_the_calling_thread_keeps_using_and_updating_its_own_session(
        self, saved_session, mock_strategy, sample_recommendation_html
    ):
        session, adapter = saved_session
        scraper = WorkbenchScraper(
            session,
            strategy=mock_strategy,
            base_url=BASE,
            timeout=TIMEOUT,
            max_workers=WORKERS,
            batch_size=BATCH,
        )

        with _RotatingCookieServer(sample_recommendation_html) as server:
            scraper.fetch_recommendation(f"{server.base_url}/sections/1/recommendations/1")
            scraper.fetch_recommendation(f"{server.base_url}/sections/1/recommendations/2")

        assert session.cookies.get("workbench_session") == "rotated-2"
        assert "workbench_session=rotated-1" in server.cookie_headers[1]
        assert adapter.verify_seen == [session.verify, session.verify]

    def test_a_worker_session_carries_every_setting_and_owns_its_mutable_state(self):
        base = requests.Session()
        base.headers["User-Agent"] = "cis-bench-test"
        base.cookies.set("auth0", "saved-auth", domain="127.0.0.1", path="/")
        base.auth = ("user", "secret")
        base.proxies = {"https": "http://proxy.example:3128"}
        base.hooks["response"].append(lambda response, *args, **kwargs: response)
        base.params = {"lang": "en"}
        base.stream = True
        base.verify = "/etc/ssl/corporate-ca.pem"
        base.cert = "/etc/ssl/client.pem"
        base.max_redirects = 7
        base.trust_env = False
        mounted = _VerifyRecordingAdapter()
        base.mount("https://", mounted)

        worker = session_for_worker(base)

        for attr in ("auth", "stream", "verify", "cert", "max_redirects", "trust_env"):
            assert getattr(worker, attr) == getattr(base, attr), attr
        assert dict(worker.headers) == dict(base.headers)
        assert worker.cookies.get_dict() == base.cookies.get_dict()
        assert worker.proxies == base.proxies
        assert worker.hooks == base.hooks
        assert worker.params == base.params
        # One shared, thread-safe connection pool.
        assert worker.adapters["https://"] is mounted
        assert list(worker.adapters) == list(base.adapters)
        # Mutable state is the worker's own.
        for attr in ("cookies", "headers", "proxies", "hooks", "params"):
            assert getattr(worker, attr) is not getattr(base, attr), attr
        assert worker.hooks["response"] is not base.hooks["response"]
        worker.cookies.set("workbench_session", "rotated", domain="127.0.0.1", path="/")
        worker.headers["X-Worker"] = "1"
        assert base.cookies.get("workbench_session") is None
        assert "X-Worker" not in base.headers


# A benchmark's profiles as WorkBench's page lists them (our own text, the component's shape)
PROFILE_DEFINITIONS = [
    {
        "title": "Level 1 - Alpha",
        "description": "<p>Items for every Alpha system.</p>",
        "parent_title": None,
    },
    {
        "title": "Level 2 - Alpha",
        "description": "<p>Extends Level 1 - Alpha.</p><ul><li>Defense in depth.</li></ul>",
        "parent_title": "Level 1 - Alpha",
    },
]


def _profiles_component(value: object) -> str:
    from tests.conftest import vue_json_attr

    return f'<wb-benchmark-profiles :profiles="{vue_json_attr(value)}"></wb-benchmark-profiles>'


class TestTheProfileDefinitions:
    """The benchmark page's profiles are read with their descriptions and parents."""

    def test_each_profile_is_read_with_its_parent(self):
        from cis_bench.fetcher.workbench import parse_benchmark_page
        from cis_bench.models.benchmark import ProfileDefinition

        page = parse_benchmark_page(_profiles_component(PROFILE_DEFINITIONS))

        assert page.profile_definitions == [
            ProfileDefinition(
                title="Level 1 - Alpha",
                description="<p>Items for every Alpha system.</p>",
                parent=None,
            ),
            ProfileDefinition(
                title="Level 2 - Alpha",
                description="<p>Extends Level 1 - Alpha.</p><ul><li>Defense in depth.</li></ul>",
                parent="Level 1 - Alpha",
            ),
        ]

    def test_a_page_without_the_component_has_no_definitions(self):
        from cis_bench.fetcher.workbench import parse_benchmark_page

        assert parse_benchmark_page(PUBLISHED_STATUS_HTML).profile_definitions == []

    @pytest.mark.parametrize(
        "html",
        [
            pytest.param(
                "<wb-benchmark-profiles :profiles=\"JSON.parse('[{not json')\">"
                "</wb-benchmark-profiles>",
                id="not-json",
            ),
            pytest.param(_profiles_component({"title": "Level 1 - Alpha"}), id="not-a-list"),
            pytest.param(_profiles_component([{"description": "<p>No title.</p>"}]), id="no-title"),
            pytest.param(_profiles_component(["Level 1 - Alpha"]), id="not-an-object"),
            pytest.param(
                _profiles_component([{"title": "Level 1 - Alpha", "parent_title": 1}]),
                id="parent-not-text",
            ),
            pytest.param(
                _profiles_component([{"title": "Level 1 - Alpha", "description": {"p": 1}}]),
                id="description-not-text",
            ),
            pytest.param(
                _profiles_component([PROFILE_DEFINITIONS[0], PROFILE_DEFINITIONS[0]]),
                id="duplicate-title",
            ),
            pytest.param("<wb-benchmark-profiles></wb-benchmark-profiles>", id="no-attribute"),
            pytest.param(
                '<wb-benchmark-profiles :profiles=""></wb-benchmark-profiles>',
                id="empty-attribute",
            ),
            pytest.param(
                '<wb-benchmark-profiles :profiles="  "></wb-benchmark-profiles>',
                id="blank-attribute",
            ),
            pytest.param(
                "<wb-benchmark-profiles :profiles=\"JSON.parse('')\"></wb-benchmark-profiles>",
                id="empty-literal",
            ),
        ],
    )
    def test_a_component_without_a_list_of_titled_profiles_is_an_error(self, html):
        # The component is there, so its profiles are never silently dropped.
        from cis_bench.exceptions import ParserError
        from cis_bench.fetcher.workbench import parse_benchmark_page

        with pytest.raises(ParserError, match="wb-benchmark-profiles"):
            parse_benchmark_page(html)

    def test_titles_are_trimmed_and_a_blank_parent_or_description_is_none(self):
        from cis_bench.fetcher.workbench import parse_benchmark_page
        from cis_bench.models.benchmark import ProfileDefinition

        page = parse_benchmark_page(
            _profiles_component(
                [{"title": "  Level 1 - Alpha ", "description": "  ", "parent_title": " "}]
            )
        )

        assert page.profile_definitions == [ProfileDefinition(title="Level 1 - Alpha")]

    @patch("cis_bench.fetcher.workbench.StrategyDetector.detect_strategy")
    def test_a_download_keeps_the_page_profile_definitions(
        self,
        mock_detector,
        mock_strategy,
        sample_benchmark_title_html,
        sample_benchmark_navtree,
        sample_recommendation_html,
        stub_session,
    ):
        mock_detector.return_value = mock_strategy
        page = sample_benchmark_title_html.replace(
            "</body>", _profiles_component(PROFILE_DEFINITIONS) + "</body>"
        )
        url = "https://workbench.cisecurity.org/benchmarks/18528"

        def handler(requested):
            if "navtree" in requested:
                return sample_benchmark_navtree
            if requested == url:
                return page
            return sample_recommendation_html

        session, _ = stub_session(handler)
        scraper = WorkbenchScraper(
            session, base_url=BASE, timeout=TIMEOUT, max_workers=WORKERS, batch_size=BATCH
        )

        benchmark = scraper.download_benchmark(url)

        assert [(p.title, p.parent) for p in benchmark.profile_definitions] == [
            ("Level 1 - Alpha", None),
            ("Level 2 - Alpha", "Level 1 - Alpha"),
        ]
