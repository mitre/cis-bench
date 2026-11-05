"""Unit tests for WorkBench benchmark URL validation and reference resolution."""

import pytest

from cis_bench.utils.workbench_urls import (
    catalog_listing_url,
    navtree_url,
    normalize_benchmark_url,
    recommendation_url,
    resolve_benchmark_reference,
)

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
        assert normalize_benchmark_url(raw, base_url=BASE) == ("23598", f"{BASE}/benchmarks/23598")

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
            normalize_benchmark_url(raw, base_url=BASE)

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
            normalize_benchmark_url(raw, base_url=BASE)

    def test_rejects_mismatched_expected_id(self):
        with pytest.raises(ValueError, match="does not match '1'"):
            normalize_benchmark_url(
                f"{BASE}/benchmarks/23598", base_url=BASE, expected_benchmark_id="1"
            )

    def test_rejects_non_string(self):
        with pytest.raises(ValueError, match="expected string"):
            normalize_benchmark_url(23598, base_url=BASE)  # type: ignore[arg-type]


class TestResolveBenchmarkReference:
    @pytest.mark.parametrize("ref", ["23598", " 23598 ", f"{BASE}/benchmarks/23598?x=1"])
    def test_numeric_id_or_url_resolves_to_canonical(self, ref):
        assert resolve_benchmark_reference(ref, base_url=BASE) == (
            "23598",
            f"{BASE}/benchmarks/23598",
        )

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
            resolve_benchmark_reference(ref, base_url=BASE)


STAGING = "https://workbench-staging.cisecurity.org"


class TestWorkBenchPageUrls:
    """Every WorkBench page cis-bench fetches is built here, on the origin the caller gives."""

    def test_catalog_listing_url_is_on_the_given_origin(self):
        assert catalog_listing_url(base_url=STAGING) == f"{STAGING}/benchmarks"

    def test_navtree_url_names_the_benchmark(self):
        assert navtree_url(23598, base_url=STAGING) == f"{STAGING}/api/v1/benchmarks/23598/navtree"
        assert (
            navtree_url("23598", base_url=STAGING) == f"{STAGING}/api/v1/benchmarks/23598/navtree"
        )

    def test_recommendation_url_names_the_section_and_recommendation(self):
        assert (
            recommendation_url(4567, 374956, base_url=STAGING)
            == f"{STAGING}/sections/4567/recommendations/374956"
        )

    @pytest.mark.parametrize("bad", ["1/../2", "abc", "", " 1", "١٢", -1, None, 1.5])
    def test_page_urls_refuse_ids_that_are_not_ascii_digits(self, bad):
        with pytest.raises(ValueError):
            navtree_url(bad, base_url=STAGING)
        with pytest.raises(ValueError):
            recommendation_url(bad, 1, base_url=STAGING)
        with pytest.raises(ValueError):
            recommendation_url(1, bad, base_url=STAGING)


class TestTheOriginComesFromTheCaller:
    """Validation is against the origin passed in, so no environment is read."""

    def test_a_url_on_the_given_origin_is_accepted_and_others_refused(self):
        url = f"{STAGING}/benchmarks/23598"
        assert normalize_benchmark_url(url, base_url=STAGING) == ("23598", url)
        with pytest.raises(ValueError, match="origin"):
            normalize_benchmark_url(url, base_url=BASE)

    def test_a_numeric_reference_resolves_on_the_given_origin(self):
        assert resolve_benchmark_reference("23598", base_url=STAGING) == (
            "23598",
            f"{STAGING}/benchmarks/23598",
        )
