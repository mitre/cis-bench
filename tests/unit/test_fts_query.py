"""Unit tests for FTS5 query tokenization and quoting."""

import pytest

from cis_bench.catalog.fts import build_fts_query


class TestBuildFtsQuery:
    """Test FTS5 user query sanitization and prefix quoting."""

    def test_dotted_version_tokens_are_quoted_with_prefix_wildcards(self):
        """Test dotted version strings split into quoted prefix tokens."""
        assert build_fts_query("ubuntu 20.04") == '"ubuntu"* "20"* "04"*'

    def test_single_word_and_trailing_wildcard(self):
        """Test single terms and explicit trailing wildcards produce one quoted prefix."""
        assert build_fts_query("ubuntu") == '"ubuntu"*'
        assert build_fts_query("ubunt*") == '"ubunt"*'

    def test_hyphenated_and_symbol_queries(self):
        """Test hyphens, underscores, slashes, and punctuation split into quoted word tokens."""
        assert build_fts_query("red-hat!!!") == '"red"* "hat"*'
        assert build_fts_query("oracle_9") == '"oracle"* "9"*'
        assert build_fts_query("CIS Benchmark (v2.0.1)") == '"CIS"* "Benchmark"* "v2"* "0"* "1"*'

    @pytest.mark.parametrize(
        ("raw_query", "expected"),
        [
            ("AND", '"AND"*'),
            ("OR", '"OR"*'),
            ("NOT", '"NOT"*'),
            ("NEAR", '"NEAR"*'),
            ("ubuntu AND rhel", '"ubuntu"* "AND"* "rhel"*'),
        ],
    )
    def test_fts5_boolean_keywords_are_quoted_as_literal_prefixes(
        self, raw_query: str, expected: str
    ):
        """Test uppercase FTS5 reserved keywords are quoted so SQLite treats them as terms."""
        assert build_fts_query(raw_query) == expected

    @pytest.mark.parametrize("raw_query", ["", "   ", "...", "!!!", "***", '""', "()", "___"])
    def test_empty_whitespace_and_punctuation_only_return_empty_string(self, raw_query: str):
        """Test inputs with no word characters return an empty string."""
        assert build_fts_query(raw_query) == ""
