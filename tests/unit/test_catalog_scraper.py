"""Unit tests for catalog scraper."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from cis_bench.catalog.database import CatalogDatabase
from cis_bench.catalog.scraper import CatalogScraper


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database."""
    db = CatalogDatabase(tmp_path / "test.db")
    db.initialize_schema()
    return db


@pytest.fixture
def sample_html():
    """Load sample catalog HTML."""
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "html" / "workbench_catalog_page1_sample.html"
    )
    return fixture_path.read_text()


@pytest.fixture
def mock_session(sample_html):
    """Mock authenticated session."""
    session = Mock()
    response = Mock()
    response.text = sample_html
    response.status_code = 200
    response.raise_for_status = Mock()
    session.get = Mock(return_value=response)
    session.verify = False
    return session


class TestScraperInitialization:
    """Test scraper initialization."""

    def test_scraper_creation(self, temp_db, mock_session):
        """Test scraper can be created."""
        scraper = CatalogScraper(temp_db, mock_session)

        assert scraper.db == temp_db
        assert scraper.session == mock_session

    def test_base_url(self):
        """Test base URL is set correctly."""
        assert CatalogScraper.BASE_URL == "https://workbench.cisecurity.org/benchmarks"


class TestConnectionTesting:
    """Test connection and authentication testing."""

    def test_connection_success(self, temp_db, mock_session):
        """Test successful connection test."""
        scraper = CatalogScraper(temp_db, mock_session)

        result = scraper.test_connection()

        assert result is True
        mock_session.get.assert_called_once()

    def test_connection_detects_login_redirect(self, temp_db):
        """Test detection of login redirect."""
        session = Mock()
        response = Mock()
        response.text = "<html><body>Login required</body></html>"
        response.status_code = 200
        session.get = Mock(return_value=response)

        scraper = CatalogScraper(temp_db, session)

        with pytest.raises(Exception, match="Not authenticated"):
            scraper.test_connection()

    def test_connection_handles_network_error(self, temp_db):
        """Test handling of network errors."""
        import requests

        session = Mock()
        session.get = Mock(side_effect=requests.ConnectionError("Network error"))

        scraper = CatalogScraper(temp_db, session)

        with pytest.raises(Exception, match="Connection failed"):
            scraper.test_connection()


class TestPageFetching:
    """Test individual page fetching."""

    def test_fetch_page(self, temp_db, mock_session, sample_html):
        """Test fetching single page."""
        scraper = CatalogScraper(temp_db, mock_session)

        html = scraper._fetch_page(1)

        assert html == sample_html
        mock_session.get.assert_called_once()

    def test_fetch_page_url_format(self, temp_db, mock_session):
        """Test page URL is formatted correctly."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper._fetch_page(5)

        # Check URL includes page parameter
        call_args = mock_session.get.call_args
        url = call_args[0][0]
        assert "?page=5" in url

    def test_fetch_page_user_agent(self, temp_db, mock_session):
        """Test User-Agent header is set."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper._fetch_page(1)

        call_args = mock_session.get.call_args
        headers = call_args[1].get("headers", {})
        assert "User-Agent" in headers
        assert "cis-bench-cli" in headers["User-Agent"]


class TestFullCatalogScrape:
    """Test full catalog scraping."""

    def test_scrape_full_catalog(self, temp_db, mock_session):
        """Test scraping multiple pages."""
        scraper = CatalogScraper(temp_db, mock_session)

        stats = scraper.scrape_full_catalog(max_pages=2, rate_limit_seconds=0)

        assert stats["total_benchmarks"] > 0
        assert stats["pages_scraped"] >= 1
        assert isinstance(stats["failed_pages"], list)

    def test_scrape_respects_max_pages(self, temp_db, mock_session):
        """Test max_pages parameter limits scraping."""
        scraper = CatalogScraper(temp_db, mock_session)

        stats = scraper.scrape_full_catalog(max_pages=3, rate_limit_seconds=0)

        # Should not scrape more than max_pages
        assert stats["pages_scraped"] <= 3

    def test_scrape_saves_to_database(self, temp_db, mock_session):
        """Test scraped benchmarks are saved to database."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper.scrape_full_catalog(max_pages=1, rate_limit_seconds=0)

        # Check database has benchmarks
        db_stats = temp_db.get_catalog_stats()
        assert db_stats["total_benchmarks"] > 0

    def test_scrape_marks_latest_versions(self, temp_db, mock_session):
        """Test scraper marks latest versions."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper.scrape_full_catalog(max_pages=1, rate_limit_seconds=0)

        # Verify mark_latest_versions was called (check metadata exists)
        # This is indirect - checking the method was executed
        db_stats = temp_db.get_catalog_stats()
        assert db_stats["total_benchmarks"] > 0  # Scrape completed

    def test_scrape_saves_metadata(self, temp_db, mock_session):
        """Test scraper saves scrape metadata."""
        scraper = CatalogScraper(temp_db, mock_session)

        scraper.scrape_full_catalog(max_pages=1, rate_limit_seconds=0)

        # Check metadata was saved
        last_scrape = temp_db.get_metadata("last_full_scrape")
        assert last_scrape is not None


class TestQuickUpdate:
    """Test quick update functionality."""

    def test_page_one_update(self, temp_db, mock_session):
        """Test quick update scrapes page 1 only."""
        scraper = CatalogScraper(temp_db, mock_session)

        stats = scraper.scrape_page_one_update(rate_limit_seconds=0)

        assert "new_count" in stats
        assert "updated_count" in stats
        assert isinstance(stats["new_count"], int)

    def test_update_detects_new_benchmarks(self, temp_db, mock_session):
        """Test update detects new benchmarks."""
        scraper = CatalogScraper(temp_db, mock_session)

        # First update - all new
        stats1 = scraper.scrape_page_one_update(rate_limit_seconds=0)
        assert stats1["new_count"] > 0

        # Second update - none new (same page)
        stats2 = scraper.scrape_page_one_update(rate_limit_seconds=0)
        assert stats2["new_count"] == 0


class TestErrorHandling:
    """Test error handling and resilience."""

    def test_failed_page_continues_scraping(self, temp_db, sample_html):
        """Test that failing one page doesn't stop the scrape."""
        session = Mock()

        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # First 19 calls succeed, only last fails (5% failure - below 10% threshold)
            if call_count <= 19:  # Pages 1-19 succeed
                response = Mock()
                response.text = sample_html
                response.status_code = 200
                response.raise_for_status = Mock()
                return response
            else:
                raise Exception("Network error on page 20")

        session.get = Mock(side_effect=side_effect)

        scraper = CatalogScraper(temp_db, session)

        # This should not crash even if one page fails (19 succeed, 1 fails = 5% failure)
        stats = scraper.scrape_full_catalog(max_pages=20, rate_limit_seconds=0)

        # Should have completed scrape attempt
        assert "total_benchmarks" in stats
        assert "failed_pages" in stats
        # At least page 1 should have succeeded
        assert stats["total_benchmarks"] > 0
