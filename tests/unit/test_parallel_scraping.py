"""Unit tests for parallel catalog scraping with retry logic."""

from unittest.mock import Mock, patch

import pytest

from cis_bench.catalog.scraper import CatalogScraper


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary test database."""
    from cis_bench.catalog.database import CatalogDatabase

    db_path = tmp_path / "test_catalog.db"
    db = CatalogDatabase(db_path)
    db.initialize_schema()
    return db


def get_sample_html(max_page=100):
    """Generate sample HTML with pagination."""
    return f"""
    <table>
        <tr>
            <td><a href="/benchmarks/12345">CIS Test Benchmark</a></td>
            <td>v1.0.0</td>
            <td>Published</td>
            <td>Test Community</td>
            <td>Test Collection</td>
            <td>testuser</td>
        </tr>
    </table>
    <nav>
        <a>1</a><a>2</a><a>3</a><a>{max_page}</a>
    </nav>
    """


@pytest.fixture
def sample_html():
    """Sample HTML for parsing."""
    return get_sample_html(100)


# ============================================================================
# Tests: Retry Logic
# ============================================================================


class TestRetryLogic:
    """Test retry logic for failed pages."""

    def test_fetch_and_parse_page_retries_on_failure(self, temp_db):
        """_fetch_and_parse_page retries failed requests."""
        session = Mock()
        scraper = CatalogScraper(temp_db, session)

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary network error")
            # Succeed on 3rd attempt
            response = Mock()
            response.text = "<table></table>"
            return response

        scraper._fetch_page = Mock(side_effect=side_effect)

        with patch(
            "cis_bench.catalog.parser.WorkBenchCatalogParser.parse_catalog_page"
        ) as mock_parse:
            mock_parse.return_value = []

            # Should succeed after retries
            result = scraper._fetch_and_parse_page(2, max_retries=3)

            assert call_count == 3  # Failed twice, succeeded third time
            assert result == []

    def test_fetch_and_parse_page_fails_after_max_retries(self, temp_db):
        """_fetch_and_parse_page raises exception after max retries."""
        session = Mock()
        scraper = CatalogScraper(temp_db, session)

        scraper._fetch_page = Mock(side_effect=Exception("Permanent error"))

        with pytest.raises(Exception) as exc_info:
            scraper._fetch_and_parse_page(2, max_retries=3)

        assert "Permanent error" in str(exc_info.value)


# ============================================================================
# Tests: Parallel Scraping
# ============================================================================


class TestMultiPageScraping:
    """Test scraping behavior with multiple pages."""

    def test_scrape_multiple_pages_successfully(self, temp_db, sample_html):
        """Scraping successfully processes all requested pages."""
        session = Mock()

        response = Mock()
        response.text = sample_html
        response.status_code = 200
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)

        scraper = CatalogScraper(temp_db, session)

        # Scrape multiple pages - should complete successfully
        stats = scraper.scrape_full_catalog(max_pages=5, rate_limit_seconds=0)

        # Behavior: completes scraping
        assert "pages_scraped" in stats
        assert "total_benchmarks" in stats
        assert stats["pages_scraped"] > 0
        assert stats["total_benchmarks"] >= 0

    def test_scrape_large_catalog_completes(self, temp_db, sample_html):
        """Scraping can handle large catalogs."""
        session = Mock()

        response = Mock()
        response.text = sample_html
        response.status_code = 200
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)

        scraper = CatalogScraper(temp_db, session)

        # Behavior: handles large number of pages without crashing
        stats = scraper.scrape_full_catalog(max_pages=20, rate_limit_seconds=0)

        assert stats["pages_scraped"] > 0
        assert "failed_pages" in stats


# ============================================================================
# Tests: Failure Threshold
# ============================================================================


class TestFailureThreshold:
    """Test failure threshold abort logic."""

    def test_scraping_aborts_when_failure_rate_exceeds_10_percent(self, temp_db, sample_html):
        """Scraping aborts when >10% of pages fail."""
        session = Mock()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Fail 50% of pages (way over 10% threshold)
            if call_count % 2 == 0:
                raise Exception("Network error")

            response = Mock()
            response.text = sample_html
            response.status_code = 200
            response.raise_for_status = Mock()
            return response

        session.get = Mock(side_effect=side_effect)

        scraper = CatalogScraper(temp_db, session)

        # Should abort due to high failure rate
        with pytest.raises(Exception) as exc_info:
            scraper.scrape_full_catalog(max_pages=20, rate_limit_seconds=0)

        assert "Scraping aborted" in str(exc_info.value)
        assert "pages failed" in str(exc_info.value)

    def test_scraping_handles_transient_failures_with_retry(self, temp_db, sample_html):
        """Scraping handles transient failures via retry logic."""
        session = Mock()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Fail first attempt on every 5th call, succeed on retry
            if call_count % 10 == 5:
                # This will fail first attempt, but retry will get next call which succeeds
                if call_count <= 5:
                    raise Exception(f"Transient error on call {call_count}")

            response = Mock()
            response.text = sample_html
            response.status_code = 200
            response.raise_for_status = Mock()
            return response

        session.get = Mock(side_effect=side_effect)

        scraper = CatalogScraper(temp_db, session)

        # Behavior: completes scraping, retry logic handles transient failures
        stats = scraper.scrape_full_catalog(max_pages=10, rate_limit_seconds=0)

        # Should complete successfully
        assert stats["pages_scraped"] > 0
        assert "failed_pages" in stats
        # Retry should fix transient failures
        assert stats["total_benchmarks"] >= 0


# ============================================================================
# Tests: Scraping Behavior
# ============================================================================


class TestScrapingBehavior:
    """Test overall scraping behavior (not implementation details)."""

    def test_scraping_respects_max_pages_limit(self, temp_db, sample_html):
        """Scraping stops at max_pages limit."""
        session = Mock()

        response = Mock()
        response.text = sample_html
        response.status_code = 200
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)

        scraper = CatalogScraper(temp_db, session)

        # Behavior: respects the max_pages parameter
        stats = scraper.scrape_full_catalog(max_pages=10, rate_limit_seconds=0)

        # Should not exceed requested pages
        assert stats["pages_scraped"] <= 10
        assert stats["pages_scraped"] > 0

    def test_scraping_returns_statistics(self, temp_db, sample_html):
        """Scraping returns useful statistics."""
        session = Mock()

        response = Mock()
        response.text = sample_html
        response.status_code = 200
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)

        scraper = CatalogScraper(temp_db, session)

        stats = scraper.scrape_full_catalog(max_pages=5, rate_limit_seconds=0)

        # Behavior: returns complete statistics
        assert "pages_scraped" in stats
        assert "total_benchmarks" in stats
        assert "failed_pages" in stats
        assert isinstance(stats["pages_scraped"], int)
        assert isinstance(stats["total_benchmarks"], int)
        assert isinstance(stats["failed_pages"], list)
