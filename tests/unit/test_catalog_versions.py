"""Unit tests for ordering CIS WorkBench benchmark version strings."""

import pytest

from cis_bench.catalog.versions import is_newer_version, parse_version, version_sort_key


class TestParseVersion:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("v1.0.0", (1, 0, 0)),
            ("1.0.0", (1, 0, 0)),
            ("v2.0.1", (2, 0, 1)),
            ("v1.0.0.1", (1, 0, 0, 1)),
            ("v8", (8,)),
            ("v0.1", (0, 1)),
            ("v7.1.0 (vNext)", (7, 1, 0)),
            ("v1.1.0 NEXT", (1, 1, 0)),
            ("  v3.0.0  ", (3, 0, 0)),
            ("V2.0.0", (2, 0, 0)),
        ],
    )
    def test_numeric_prefix_becomes_a_tuple(self, raw, expected):
        """Real WorkBench version strings: leading digits order, trailing labels are ignored."""
        assert parse_version(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "   ",
            "vNext",
            "vNEXT",
            "vDev",
            "vTest",
            "vOLD DO NOT USE",
            "vObsolete",
            "latest",
        ],
    )
    def test_strings_without_a_numeric_prefix_are_unversioned(self, raw):
        assert parse_version(raw) is None


class TestVersionOrdering:
    def test_numeric_versions_order_component_wise_not_lexically(self):
        ordered = ["v1.0.0", "v1.0.1", "v1.1.0", "v1.10.0", "v2.0.0", "v10.0.0"]
        shuffled = ["v10.0.0", "v1.10.0", "v2.0.0", "v1.0.0", "v1.1.0", "v1.0.1"]
        assert sorted(shuffled, key=version_sort_key) == ordered

    def test_shorter_tuple_sorts_below_its_extension(self):
        assert version_sort_key("v1.0") < version_sort_key("v1.0.0") < version_sort_key("v1.0.0.1")

    def test_unversioned_strings_sort_below_every_numeric_version_and_tie_with_each_other(self):
        assert version_sort_key("vNext") < version_sort_key("v0.0.0")
        assert version_sort_key(None) < version_sort_key("v0.1")
        assert version_sort_key("vNext") == version_sort_key("vDev") == version_sort_key("")

    def test_trailing_label_does_not_change_order(self):
        assert version_sort_key("v7.1.0 (vNext)") == version_sort_key("v7.1.0")


class TestIsNewerVersion:
    @pytest.mark.parametrize(
        ("candidate", "current", "expected"),
        [
            ("v2.0.0", "v1.0.0", True),
            ("v1.0.1", "v1.0.0", True),
            ("v1.0.0", "v1.0.0", False),
            ("v1.0.0", "v2.0.0", False),
            ("v2.0.0 (vNext)", "v1.9.0", True),
            ("vNext", "v1.0.0", False),
            ("v1.0.0", "vNext", False),
            (None, "v1.0.0", False),
            ("v1.0.0", None, False),
        ],
    )
    def test_only_a_strictly_greater_parseable_version_is_newer(self, candidate, current, expected):
        assert is_newer_version(candidate, current) is expected
