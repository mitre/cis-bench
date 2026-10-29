"""Unit tests for extended benchmark detail page metadata parsing.

Tests for extraction of CPE-IDs, release type, contributors, parent benchmarks,
revision history, and other metadata from benchmark detail pages.
"""

from cis_bench.catalog.parser import WorkBenchCatalogParser


class TestCPEExtraction:
    """Test CPE-ID extraction from Assets table."""

    def test_extract_cpe_ids_single_asset(self):
        """Test extracting single CPE-ID from Assets table."""
        html = """
        <html>
        <body>
            <h3>Assets</h3>
            <table>
                <thead>
                    <tr><th>Title</th><th>CPE-ID</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <td>AlmaLinux OS 9</td>
                        <td>cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*</td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "assets" in metadata
        assert len(metadata["assets"]) == 1
        assert metadata["assets"][0]["title"] == "AlmaLinux OS 9"
        assert metadata["assets"][0]["cpe_id"] == "cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"

    def test_extract_cpe_ids_multiple_assets(self):
        """Test extracting multiple CPE-IDs from Assets table."""
        html = """
        <html>
        <body>
            <h3>Assets</h3>
            <table>
                <thead>
                    <tr><th>Title</th><th>CPE-ID</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Microsoft Windows 11</td>
                        <td>cpe:2.3:o:microsoft:windows_11:-:*:*:*:*:*:x64:*</td>
                    </tr>
                    <tr>
                        <td>Microsoft Windows 10</td>
                        <td>cpe:2.3:o:microsoft:windows_10:-:*:*:*:*:*:x64:*</td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert len(metadata["assets"]) == 2
        assert metadata["assets"][0]["title"] == "Microsoft Windows 11"
        assert metadata["assets"][1]["title"] == "Microsoft Windows 10"

    def test_extract_cpe_ids_no_assets_table(self):
        """Test when no Assets table exists."""
        html = "<html><body><p>No assets here</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "assets" not in metadata or metadata["assets"] == []


class TestReleaseTypeExtraction:
    """Test Release Type extraction."""

    def test_extract_release_type_planned_update(self):
        """Test extracting 'Planned Update' release type."""
        html = """
        <html>
        <body>
            <p><strong>Release Type:</strong> Planned Update</p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert metadata["release_type"] == "Planned Update"

    def test_extract_release_type_bug_fix(self):
        """Test extracting 'Bug Fix' release type."""
        html = """
        <html>
        <body>
            <p><strong>Release Type:</strong> Bug Fix</p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert metadata["release_type"] == "Bug Fix"

    def test_extract_release_type_not_present(self):
        """Test when Release Type is not present."""
        html = "<html><body><p>No release type here</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "release_type" not in metadata


class TestContributorsExtraction:
    """Test Contributors extraction."""

    def test_extract_contributors_single_line(self):
        """Test extracting contributors from single paragraph."""
        html = """
        <html>
        <body>
            <h3>Contributors</h3>
            <p>Jonathan Lewis, Ron Colvin, Dave Billing</p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "contributors" in metadata
        assert len(metadata["contributors"]) == 3
        assert "Jonathan Lewis" in metadata["contributors"]
        assert "Ron Colvin" in metadata["contributors"]
        assert "Dave Billing" in metadata["contributors"]

    def test_extract_contributors_long_list(self):
        """Test extracting long contributors list."""
        html = """
        <html>
        <body>
            <h3>Contributors</h3>
            <p>Eric Pinnell, Thomas Sjögren, James Trigg, Matthew Burket, Marcus Burghardt, Graham Eames</p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert len(metadata["contributors"]) == 6
        assert "Eric Pinnell" in metadata["contributors"]
        assert "Thomas Sjögren" in metadata["contributors"]

    def test_extract_contributors_not_present(self):
        """Test when Contributors section is not present."""
        html = "<html><body><h3>Overview</h3><p>No contributors</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "contributors" not in metadata or metadata["contributors"] == []


class TestParentBenchmarkExtraction:
    """Test Parent Benchmark extraction."""

    def test_extract_parent_benchmark(self):
        """Test extracting parent benchmark link from title."""
        html = """
        <html>
        <body>
            <h1>
                CIS AlmaLinux OS 9 Benchmark v2.0.0
                <a href="https://workbench.cisecurity.org/benchmarks/16763">
                    CIS Fedora 34 Branch Benchmark v2.0.0
                </a>
            </h1>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert (
            metadata["parent_benchmark_url"] == "https://workbench.cisecurity.org/benchmarks/16763"
        )
        assert metadata["parent_benchmark_title"] == "CIS Fedora 34 Branch Benchmark v2.0.0"

    def test_extract_parent_benchmark_not_present(self):
        """Test when no parent benchmark link exists."""
        html = """
        <html>
        <body>
            <h1>CIS Ubuntu 22.04 Benchmark v1.0.0</h1>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "parent_benchmark_url" not in metadata


class TestIntendedAudienceExtraction:
    """Test Intended Audience extraction."""

    def test_extract_intended_audience(self):
        """Test extracting Intended Audience section."""
        html = """
        <html>
        <body>
            <h3>Intended Audience</h3>
            <p>This benchmark is intended for system administrators and security specialists.</p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "intended_audience" in metadata
        assert "system administrators" in metadata["intended_audience"]

    def test_extract_intended_audience_not_present(self):
        """Test when Intended Audience section is not present."""
        html = "<html><body><h3>Overview</h3><p>No audience</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "intended_audience" not in metadata


class TestAcknowledgementsExtraction:
    """Test Acknowledgements extraction."""

    def test_extract_acknowledgements(self):
        """Test extracting Acknowledgements section."""
        html = """
        <html>
        <body>
            <h3>Acknowledgements</h3>
            <p>This benchmark is based upon previous Linux benchmarks published by CIS.</p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "acknowledgements" in metadata
        assert "previous Linux benchmarks" in metadata["acknowledgements"]

    def test_extract_acknowledgements_not_present(self):
        """Test when Acknowledgements section is not present."""
        html = "<html><body><h3>Overview</h3><p>No acks</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "acknowledgements" not in metadata


class TestRevisionHistoryExtraction:
    """Test Revision History extraction."""

    def test_extract_revision_history_single_entry(self):
        """Test extracting single revision history entry."""
        html = """
        <html>
        <body>
            <h3>Revision History</h3>
            <table>
                <thead>
                    <tr><th>Current Version</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <td>1 year ago</td>
                        <td>Eric</td>
                        <td>5 modifications</td>
                        <td><a href="/diff/123">View Diff</a></td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "revision_history" in metadata
        assert len(metadata["revision_history"]) == 1
        assert metadata["revision_history"][0]["revision_date"] == "1 year ago"
        assert metadata["revision_history"][0]["author"] == "Eric"
        assert metadata["revision_history"][0]["modification_count"] == 5

    def test_extract_revision_history_multiple_entries(self):
        """Test extracting multiple revision history entries."""
        html = """
        <html>
        <body>
            <h3>Revision History</h3>
            <table>
                <tbody>
                    <tr>
                        <td>8 months ago</td>
                        <td>Tom</td>
                        <td>1 modification</td>
                        <td></td>
                    </tr>
                    <tr>
                        <td>1 year ago</td>
                        <td>Eric</td>
                        <td>2 modifications</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert len(metadata["revision_history"]) == 2
        assert metadata["revision_history"][0]["author"] == "Tom"
        assert metadata["revision_history"][1]["author"] == "Eric"

    def test_extract_revision_history_not_present(self):
        """Test when Revision History section is not present."""
        html = "<html><body><h3>Overview</h3><p>No history</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "revision_history" not in metadata or metadata["revision_history"] == []


class TestMilestoneExtraction:
    """Test Milestone extraction."""

    def test_extract_milestone_from_breadcrumb(self):
        """Test extracting milestone name and URL from breadcrumb."""
        html = """
        <html>
        <body>
            <p>
                <a href="/communities/139">CIS AlmaLinux OS Benchmarks</a>
                -
                <a href="/community/139/milestones/956">CIS AlmaLinux OS 9 Benchmark v2.0.0</a>
            </p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert metadata["milestone_name"] == "CIS AlmaLinux OS 9 Benchmark v2.0.0"
        assert "/milestones/956" in metadata["milestone_url"]

    def test_extract_milestone_not_present(self):
        """Test when milestone is not present."""
        html = "<html><body><p>No milestone</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "milestone_name" not in metadata
        assert "milestone_url" not in metadata


class TestCommunityURLExtraction:
    """Test Community URL extraction."""

    def test_extract_community_url(self):
        """Test extracting community URL from breadcrumb."""
        html = """
        <html>
        <body>
            <p>
                <a href="https://workbench.cisecurity.org/communities/139">CIS AlmaLinux OS Benchmarks</a>
            </p>
        </body>
        </html>
        """
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert metadata["community_url"] == "https://workbench.cisecurity.org/communities/139"

    def test_extract_community_url_not_present(self):
        """Test when community URL is not present."""
        html = "<html><body><p>No community</p></body></html>"
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        assert "community_url" not in metadata


class TestCompleteMetadataExtraction:
    """Test extracting all metadata fields together."""

    def test_extract_all_fields_comprehensive(self):
        """Test extracting all metadata fields from a complete detail page."""
        html = """
        <html>
        <body>
            <h1>
                CIS AlmaLinux OS 9 Benchmark v2.0.0
                <a href="/benchmarks/16763">CIS Fedora 34 Benchmark</a>
            </h1>

            <p>
                <a href="/communities/139">CIS AlmaLinux OS Benchmarks</a>
                -
                <a href="/community/139/milestones/956">CIS AlmaLinux 9 v2.0.0</a>
            </p>

            <p>Published 1 year ago on Jun 24th 2024</p>
            <p><strong>Release Type:</strong> Planned Update</p>

            <h3>Overview</h3>
            <p>This benchmark provides security guidance for AlmaLinux 9.</p>

            <h3>Intended Audience</h3>
            <p>System administrators and security specialists.</p>

            <h3>Acknowledgements</h3>
            <p>Thanks to all contributors to previous Linux benchmarks.</p>

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
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        # Verify all fields extracted
        assert metadata["published_date"] == "Jun 24th 2024"
        assert metadata["release_type"] == "Planned Update"
        assert len(metadata["contributors"]) == 3
        assert (
            metadata["parent_benchmark_url"] == "https://workbench.cisecurity.org/benchmarks/16763"
        )
        assert metadata["parent_benchmark_title"] == "CIS Fedora 34 Benchmark"
        assert metadata["intended_audience"] == "System administrators and security specialists."
        assert (
            metadata["acknowledgements"]
            == "Thanks to all contributors to previous Linux benchmarks."
        )
        assert len(metadata["assets"]) == 1
        assert metadata["assets"][0]["cpe_id"] == "cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"
        assert len(metadata["revision_history"]) == 1
        assert metadata["revision_history"][0]["author"] == "Eric"
        assert metadata["community_url"] == "https://workbench.cisecurity.org/communities/139"
        assert metadata["milestone_name"] == "CIS AlmaLinux 9 v2.0.0"
        assert (
            metadata["milestone_url"]
            == "https://workbench.cisecurity.org/community/139/milestones/956"
        )


class TestRealHTMLRegression:
    """Regression tests using actual HTML from CIS WorkBench.

    These tests use real HTML fixtures to ensure the parser handles actual
    web component structures, not just synthetic test HTML.
    """

    def test_parse_real_benchmark_18208(self):
        """Test parsing actual HTML from benchmark 18208 (AlmaLinux 9 v2.0.0)."""
        from pathlib import Path

        fixture_path = (
            Path(__file__).parent.parent / "fixtures" / "html" / "benchmark_detail_18208_real.html"
        )
        html = fixture_path.read_text()

        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        # Verify ALL 10+ fields extracted from real HTML
        assert metadata["published_date"] == "Jun 24th 2024"
        assert metadata["published_relative"] == "1 year ago on Jun 24th 2024"
        assert metadata["release_type"] == "Planned Update"

        # Assets (from wb-benchmark-assets web component)
        assert "assets" in metadata
        assert len(metadata["assets"]) == 1
        assert metadata["assets"][0]["title"] == "AlmaLinux OS 9"
        assert metadata["assets"][0]["cpe_id"] == "cpe:2.3:o:almalinux:almalinux:9:*:*:*:*:*:*:*"

        # Contributors (22 names)
        assert "contributors" in metadata
        assert len(metadata["contributors"]) >= 20
        assert "Jonathan Lewis Christopherson" in metadata["contributors"]
        assert "Eric Pinnell" in metadata["contributors"]

        # Parent benchmark (from wb-html-link component)
        assert (
            metadata["parent_benchmark_url"] == "https://workbench.cisecurity.org/benchmarks/16763"
        )
        assert metadata["parent_benchmark_title"] == "CIS Fedora 34 Branch Benchmark v2.0.0"

        # Organizational
        assert metadata["community_url"] == "https://workbench.cisecurity.org/communities/139"
        assert metadata["milestone_name"] == "CIS AlmaLinux OS 9 Benchmark v2.0.0"

        # Documentation sections (from wb-recommendation-data components)
        assert "description" in metadata
        assert "AlmaLinux OS 9" in metadata["description"]
        assert "intended_audience" in metadata
        assert "system and application administrators" in metadata["intended_audience"]
        assert "acknowledgements" in metadata
        assert "previous Linux benchmarks" in metadata["acknowledgements"]

        # Revision history
        assert "revision_history" in metadata
        assert len(metadata["revision_history"]) >= 5
        assert metadata["revision_history"][0]["author"] in ["Tom", "Eric"]

    def test_parse_real_aws_benchmark_21960(self):
        """Test parsing AWS Foundations benchmark (cloud platform)."""
        from pathlib import Path

        fixture_path = (
            Path(__file__).parent.parent / "fixtures" / "html" / "benchmark_detail_21960_aws.html"
        )
        html = fixture_path.read_text()
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        # Verify extraction works for cloud benchmarks
        assert metadata["published_date"] == "Sep 23rd 2025"
        assert metadata["release_type"] == "Planned Update"
        assert len(metadata["assets"]) == 1
        assert "aws" in metadata["assets"][0]["cpe_id"].lower()
        assert len(metadata["contributors"]) >= 10

    def test_parse_real_eks_benchmark_22605(self):
        """Test parsing EKS benchmark (container platform, multiple assets)."""
        from pathlib import Path

        fixture_path = (
            Path(__file__).parent.parent / "fixtures" / "html" / "benchmark_detail_22605_eks.html"
        )
        html = fixture_path.read_text()
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        # EKS might have multiple CPE-IDs (EKS + Kubernetes)
        assert metadata["published_date"] == "Oct 26th 2025"
        assert "assets" in metadata
        assert len(metadata["assets"]) >= 1
        assert len(metadata["contributors"]) >= 5

    def test_parse_real_mssql_benchmark_24450(self):
        """Test parsing SQL Server benchmark (database, has parent)."""
        from pathlib import Path

        fixture_path = (
            Path(__file__).parent.parent / "fixtures" / "html" / "benchmark_detail_24450_mssql.html"
        )
        html = fixture_path.read_text()
        metadata = WorkBenchCatalogParser.parse_benchmark_detail_page(html)

        # SQL Server benchmark - verify database platform
        assert metadata["published_date"] == "Oct 24th 2025"
        assert metadata["release_type"] == "Bug Fix"  # Different from others
        assert len(metadata["assets"]) >= 1
        assert "sql_server" in metadata["assets"][0]["cpe_id"]
        # This benchmark has a parent (v1.5.0)
        assert "parent_benchmark_url" in metadata
        assert "18146" in metadata["parent_benchmark_url"]
