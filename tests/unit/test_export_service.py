"""Tests for ExportService - coordinates export operations."""

import pytest


class TestExportServiceExists:
    """Test that ExportService class exists and has expected structure."""

    def test_export_service_importable(self):
        """ExportService should be importable."""
        from cis_bench.services.export_service import ExportService

        assert ExportService is not None

    def test_export_service_has_export_single(self):
        """ExportService should have export_single method."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        assert hasattr(service, "export_single")
        assert callable(service.export_single)

    def test_export_service_has_export_diff(self):
        """ExportService should have export_diff method."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        assert hasattr(service, "export_diff")
        assert callable(service.export_diff)

    def test_export_service_has_export_batch(self):
        """ExportService should have export_batch method."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        assert hasattr(service, "export_batch")
        assert callable(service.export_batch)


class TestExportConfig:
    """Test ExportConfig data class."""

    def test_export_config_importable(self):
        """ExportConfig should be importable."""
        from cis_bench.services.export_service import ExportConfig

        assert ExportConfig is not None

    def test_export_config_has_format(self):
        """ExportConfig should have format field."""
        from cis_bench.services.export_service import ExportConfig

        config = ExportConfig(format="json")
        assert config.format == "json"

    def test_export_config_has_output_dir(self, tmp_path):
        """ExportConfig should have output_dir field."""
        from cis_bench.services.export_service import ExportConfig

        config = ExportConfig(format="json", output_dir=tmp_path)
        assert config.output_dir == tmp_path

    def test_export_config_has_style_for_xccdf(self):
        """ExportConfig should have optional style field for XCCDF."""
        from cis_bench.services.export_service import ExportConfig

        config = ExportConfig(format="xccdf", style="disa")
        assert config.style == "disa"

    def test_export_config_style_defaults_to_none(self):
        """ExportConfig style should default to None."""
        from cis_bench.services.export_service import ExportConfig

        config = ExportConfig(format="json")
        assert config.style is None

    def test_export_config_has_filename_pattern(self):
        """ExportConfig should have optional filename_pattern."""
        from cis_bench.services.export_service import ExportConfig

        config = ExportConfig(format="json", filename_pattern="{id}_{version}")
        assert config.filename_pattern == "{id}_{version}"


class TestExportResult:
    """Test ExportResult data class."""

    def test_export_result_importable(self):
        """ExportResult should be importable."""
        from cis_bench.services.export_service import ExportResult

        assert ExportResult is not None

    def test_export_result_success(self, tmp_path):
        """ExportResult should track success case."""
        from cis_bench.services.export_service import ExportResult

        test_path = tmp_path / "test.json"
        result = ExportResult(
            success=True,
            path=test_path,
            benchmark_id="23598",
        )
        assert result.success is True
        assert result.path == test_path
        assert result.error is None

    def test_export_result_failure(self):
        """ExportResult should track failure case."""
        from cis_bench.services.export_service import ExportResult

        result = ExportResult(
            success=False,
            benchmark_id="23598",
            error="File write failed",
        )
        assert result.success is False
        assert result.path is None
        assert result.error == "File write failed"


class TestExportServiceSingleExport:
    """Test single benchmark export."""

    @pytest.fixture
    def sample_benchmark(self):
        """Sample benchmark data."""
        return {
            "benchmark_id": "23598",
            "title": "CIS Ubuntu Linux 22.04 LTS Benchmark",
            "version": "v2.0.0",
            "recommendations": [{"ref": "1.1.1", "title": "Test rec", "description": "Test desc"}],
        }

    @pytest.fixture
    def export_config(self, tmp_path):
        """Sample export config."""
        from cis_bench.services.export_service import ExportConfig

        return ExportConfig(format="json", output_dir=tmp_path)

    def test_export_single_returns_result(self, sample_benchmark, export_config):
        """export_single should return ExportResult."""
        from cis_bench.services.export_service import ExportResult, ExportService

        service = ExportService()
        result = service.export_single(sample_benchmark, export_config)

        assert isinstance(result, ExportResult)

    def test_export_single_creates_file(self, sample_benchmark, export_config):
        """export_single should create output file."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        result = service.export_single(sample_benchmark, export_config)

        assert result.success is True
        assert result.path is not None
        assert result.path.exists()

    def test_export_single_uses_format(self, sample_benchmark, tmp_path):
        """export_single should use correct format exporter."""
        from cis_bench.services.export_service import ExportConfig, ExportService

        service = ExportService()

        # Test JSON
        json_config = ExportConfig(format="json", output_dir=tmp_path)
        result = service.export_single(sample_benchmark, json_config)
        assert result.path.suffix == ".json"

        # Test YAML
        yaml_config = ExportConfig(format="yaml", output_dir=tmp_path)
        result = service.export_single(sample_benchmark, yaml_config)
        assert result.path.suffix in [".yaml", ".yml"]


class TestExportServiceBatchExport:
    """Test batch benchmark export."""

    @pytest.fixture
    def sample_benchmarks(self):
        """Multiple sample benchmarks."""
        return [
            {
                "benchmark_id": "23598",
                "title": "CIS Ubuntu 22.04 Benchmark",
                "version": "v2.0.0",
                "recommendations": [],
            },
            {
                "benchmark_id": "12345",
                "title": "CIS RHEL 9 Benchmark",
                "version": "v1.0.0",
                "recommendations": [],
            },
        ]

    @pytest.fixture
    def export_config(self, tmp_path):
        """Sample export config."""
        from cis_bench.services.export_service import ExportConfig

        return ExportConfig(format="json", output_dir=tmp_path)

    def test_export_batch_returns_list(self, sample_benchmarks, export_config):
        """export_batch should return list of ExportResults."""
        from cis_bench.services.export_service import ExportResult, ExportService

        service = ExportService()
        results = service.export_batch(sample_benchmarks, export_config)

        assert isinstance(results, list)
        assert len(results) == 2
        assert all(isinstance(r, ExportResult) for r in results)

    def test_export_batch_creates_multiple_files(self, sample_benchmarks, export_config):
        """export_batch should create file for each benchmark."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        results = service.export_batch(sample_benchmarks, export_config)

        assert all(r.success for r in results)
        paths = [r.path for r in results]
        assert len(set(paths)) == 2  # Unique paths

    def test_export_batch_calls_progress_callback(self, sample_benchmarks, export_config):
        """export_batch should call progress callback."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        progress_calls = []

        def progress_callback(current, total, benchmark_id):
            progress_calls.append((current, total, benchmark_id))

        service.export_batch(sample_benchmarks, export_config, progress_callback)

        assert len(progress_calls) == 2
        assert progress_calls[0][0] == 1  # First item
        assert progress_calls[1][0] == 2  # Second item
        assert progress_calls[0][1] == 2  # Total


class TestExportServiceDiffExport:
    """Test diff/comparison export."""

    @pytest.fixture
    def sample_comparison(self):
        """Sample diff comparison data."""
        return {
            "old_version": "v1.0.0",
            "new_version": "v2.0.0",
            "benchmark_title": "CIS Ubuntu 22.04 Benchmark",
            "summary": {"added": 5, "removed": 2, "modified": 10, "unchanged": 100},
            "changes": {
                "added": [{"ref": "1.2.3", "title": "New rec"}],
                "removed": [{"ref": "1.2.4", "title": "Old rec"}],
                "modified": [],
                "unchanged": [],
                "renumbered": [],
            },
        }

    @pytest.fixture
    def export_config(self, tmp_path):
        """Sample export config for diff."""
        from cis_bench.services.export_service import ExportConfig

        return ExportConfig(format="markdown", output_dir=tmp_path)

    def test_export_diff_returns_result(self, sample_comparison, export_config):
        """export_diff should return ExportResult."""
        from cis_bench.services.export_service import ExportResult, ExportService

        service = ExportService()
        result = service.export_diff(sample_comparison, export_config)

        assert isinstance(result, ExportResult)

    def test_export_diff_creates_file(self, sample_comparison, export_config):
        """export_diff should create output file."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        result = service.export_diff(sample_comparison, export_config)

        assert result.success is True
        assert result.path is not None
        assert result.path.exists()

    def test_export_diff_supports_markdown(self, sample_comparison, tmp_path):
        """export_diff should support markdown format."""
        from cis_bench.services.export_service import ExportConfig, ExportService

        config = ExportConfig(format="markdown", output_dir=tmp_path)
        service = ExportService()
        result = service.export_diff(sample_comparison, config)

        assert result.success is True
        assert result.path.suffix == ".md"

    def test_export_diff_supports_json(self, sample_comparison, tmp_path):
        """export_diff should support JSON format."""
        from cis_bench.services.export_service import ExportConfig, ExportService

        config = ExportConfig(format="json", output_dir=tmp_path)
        service = ExportService()
        result = service.export_diff(sample_comparison, config)

        assert result.success is True
        assert result.path.suffix == ".json"


class TestPathGeneration:
    """Test output path generation."""

    def test_generate_filename_default_pattern(self):
        """Should generate filename with default pattern."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        filename = service._generate_filename(
            benchmark_id="23598",
            title="CIS Ubuntu 22.04 Benchmark",
            version="v2.0.0",
            extension="json",
        )

        assert "23598" in filename
        assert filename.endswith(".json")

    def test_generate_filename_custom_pattern(self):
        """Should generate filename with custom pattern."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        filename = service._generate_filename(
            benchmark_id="23598",
            title="CIS Ubuntu 22.04 Benchmark",
            version="v2.0.0",
            extension="json",
            pattern="{id}_{version}",
        )

        assert filename == "23598_v2.0.0.json"

    def test_generate_filename_sanitizes_title(self):
        """Should sanitize title for safe filenames."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        filename = service._generate_filename(
            benchmark_id="23598",
            title="CIS Ubuntu/Linux 22.04: Benchmark",
            version="v2.0.0",
            extension="json",
            pattern="{title}",
        )

        # Should not contain unsafe characters
        assert "/" not in filename
        assert ":" not in filename


class TestAvailableFormats:
    """Test format availability by context."""

    def test_get_formats_for_single(self):
        """Should return formats available for single benchmark export."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        formats = service.get_available_formats("single")

        assert "json" in formats
        assert "yaml" in formats
        assert "xccdf" in formats
        assert "csv" in formats
        assert "markdown" in formats

    def test_get_formats_for_diff(self):
        """Should return formats available for diff export."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        formats = service.get_available_formats("diff")

        assert "json" in formats
        assert "markdown" in formats
        # XCCDF doesn't make sense for diffs
        assert "xccdf" not in formats

    def test_get_formats_for_batch(self):
        """Should return formats available for batch export."""
        from cis_bench.services.export_service import ExportService

        service = ExportService()
        formats = service.get_available_formats("batch")

        assert "json" in formats
        assert "yaml" in formats
        assert "xccdf" in formats
