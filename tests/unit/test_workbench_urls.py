"""Unit tests for WorkBench benchmark URL validation and reference resolution."""

import pytest

from cis_bench.utils.workbench_urls import normalize_benchmark_url, resolve_benchmark_reference

BASE = "https://workbench.cisecurity.org"


class TestNormalizeBenchmarkUrl:
    @pytest.mark.parametrize(
        "raw",
        [
            f"{BASE}/benchmarks/23598",
            f"{BASE}/benchmarks/23598/",
            f"{BASE}/benchmarks/23598?tab=overview#top",
            "/benchmarks/23598",
            "benchmarks/23598",
            "https://WORKBENCH.cisecurity.org/benchmarks/23598",
            f"  {BASE}/benchmarks/23598  ",
        ],
    )
    def test_accepts_canonical_relative_and_decorated_forms(self, raw):
        assert normalize_benchmark_url(raw) == ("23598", f"{BASE}/benchmarks/23598")

    @pytest.mark.parametrize(
        ("raw", "fragment"),
        [
            (
                "http://workbench.cisecurity.org/benchmarks/23598",
                "must match configured WorkBench origin",
            ),
            ("https://evil.example/benchmarks/23598", "must match configured WorkBench origin"),
            (
                "https://workbench.cisecurity.org@evil.example/benchmarks/23598",
                "must match configured WorkBench origin",
            ),
            (
                "https://user:pw@workbench.cisecurity.org/benchmarks/23598",
                "must match configured WorkBench origin",
            ),
            (f"{BASE}/benchmarks/../admin", "must match configured WorkBench origin"),
            (f"{BASE}/benchmarks/abc", "path must match /benchmarks/<digits>"),
            (f"{BASE}/other/23598", "path must match /benchmarks/<digits>"),
            ("//evil.example/benchmarks/23598", "Invalid benchmark URL"),
            ("", "Invalid benchmark URL"),
            ("@evil", "Invalid benchmark URL"),
        ],
    )
    def test_rejects_off_origin_cleartext_userinfo_traversal_and_non_numeric(self, raw, fragment):
        with pytest.raises(ValueError, match=fragment):
            normalize_benchmark_url(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "/benchmarks/123/../23598",
            "benchmarks/../23598",
            f"{BASE}/benchmarks/123/%2e%2e/x",
            f"{BASE}/benchmarks/123/%2E%2E/x",
            f"{BASE}/benchmarks/%2e%2e/admin",
            f"{BASE}/benchmarks/235\t98",
            f"{BASE}/benchmarks/235\n98",
            f"{BASE}/benchmarks/235\r98",
            "https://workbench.cisecurity.org\t/benchmarks/23598",
        ],
    )
    def test_rejects_dot_segments_in_any_encoding_and_embedded_control_characters(self, raw):
        """Dot segments are rejected before URL resolution can collapse them, and control
        characters are rejected before urlsplit can silently strip them."""
        with pytest.raises(ValueError, match="Invalid benchmark URL"):
            normalize_benchmark_url(raw)

    def test_rejects_mismatched_expected_id(self):
        with pytest.raises(ValueError, match="does not match '1'"):
            normalize_benchmark_url(f"{BASE}/benchmarks/23598", expected_benchmark_id="1")

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="expected string"):
            normalize_benchmark_url(23598)  # type: ignore[arg-type]


class TestResolveBenchmarkReference:
    @pytest.mark.parametrize("ref", ["23598", " 23598 ", f"{BASE}/benchmarks/23598?x=1"])
    def test_numeric_id_or_url_resolves_to_canonical(self, ref):
        assert resolve_benchmark_reference(ref) == ("23598", f"{BASE}/benchmarks/23598")

    @pytest.mark.parametrize(
        "ref",
        [
            "abc",
            "23598abc",
            "http://workbench.cisecurity.org/benchmarks/23598",
            "",
            "２３５９８",
            "²³⁵",
        ],
    )
    def test_rejects_anything_that_is_neither_digits_nor_a_valid_url(self, ref):
        with pytest.raises(ValueError):
            resolve_benchmark_reference(ref)


class TestConfigurationErrorsAreDistinct:
    def test_invalid_workbench_url_configuration_raises_configuration_error(self, monkeypatch):
        """A bad CIS_BENCH_WORKBENCH_URL is a configuration error, distinguishable from a bad reference."""
        from cis_bench.exceptions import ConfigurationError

        monkeypatch.setenv("CIS_BENCH_WORKBENCH_URL", "http://evil.example")
        with pytest.raises(ConfigurationError, match="CIS_BENCH_WORKBENCH_URL"):
            resolve_benchmark_reference("23598")
