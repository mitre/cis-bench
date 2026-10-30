"""Unit tests for FTS5 query tokenization and quoting."""

import pytest

from cis_bench.catalog.fts import build_fts_query


class TestBuildFtsQuery:
    """Test FTS5 user query sanitization, NFC normalization, and prefix quoting."""

    @pytest.mark.parametrize(
        ("raw_query", "expected"),
        [
            ("ubuntu 20.04", '"ubuntu"* "20"* "04"*'),
            ("ubuntu", '"ubuntu"*'),
            ("ubunt*", '"ubunt"*'),
            ("red-hat!!!", '"red"* "hat"*'),
            ("oracle_9", '"oracle"* "9"*'),
            ("CIS Benchmark (v2.0.1)", '"CIS"* "Benchmark"* "v2"* "0"* "1"*'),
            ("re\u0301sume\u0301 20.04", '"résumé"* "20"* "04"*'),
            ("AND", '"AND"*'),
            ("OR", '"OR"*'),
            ("NOT", '"NOT"*'),
            ("NEAR", '"NEAR"*'),
            ("ubuntu AND rhel", '"ubuntu"* "AND"* "rhel"*'),
        ],
    )
    def test_tokenizes_normalizes_and_quotes_prefix_terms(self, raw_query: str, expected: str):
        """Test punctuation, decomposed NFD Unicode, and FTS5 keywords become quoted prefix terms."""
        assert build_fts_query(raw_query) == expected

    @pytest.mark.parametrize("raw_query", ["", "   ", "...", "!!!", "***", '""', "()", "___"])
    def test_empty_whitespace_and_punctuation_only_return_empty_string(self, raw_query: str):
        """Test inputs with no word characters return an empty string."""
        assert build_fts_query(raw_query) == ""
