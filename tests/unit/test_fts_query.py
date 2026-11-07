"""Unit tests for FTS5 query tokenization and quoting."""

import pytest

from cis_bench.catalog.fts import (
    build_fts_query,
    build_version_match_query,
    version_index_text,
)

# A plain word is looked up in the text columns of the index and, whole, in the version column;
# a plain number is looked up in the text columns only.
TEXT = "{title platform community description}"


def word(term: str) -> str:
    return f'({TEXT} : "{term}"* OR {{version}} : "{term}")'


class TestBuildFtsQuery:
    """Test FTS5 user query sanitization, NFC normalization, and prefix quoting."""

    @pytest.mark.parametrize(
        ("raw_query", "expected"),
        [
            ("ubuntu", word("ubuntu")),
            ("ubunt*", word("ubunt")),
            ("red-hat!!!", f"{word('red')} AND {word('hat')}"),
            ("oracle_9", f'{word("oracle")} AND {TEXT} : "9"*'),
            ("8", f'{TEXT} : "8"*'),
            ("AND", word("AND")),
            ("OR", word("OR")),
            ("NOT", word("NOT")),
            ("NEAR", word("NEAR")),
            ("ubuntu AND rhel", f"{word('ubuntu')} AND {word('AND')} AND {word('rhel')}"),
        ],
    )
    def test_tokenizes_normalizes_and_quotes_prefix_terms(self, raw_query: str, expected: str):
        """Test punctuation and FTS5 keywords become quoted prefix terms on the text columns."""
        assert build_fts_query(raw_query) == expected

    @pytest.mark.parametrize(
        ("raw_query", "expected"),
        [
            (
                "ubuntu 20.04",
                f'{word("ubuntu")} AND ({TEXT} : ("20"* AND "04"*) OR {{version}} : ^"20 04")',
            ),
            (
                "CIS Benchmark (v2.0.1)",
                f"{word('CIS')} AND {word('Benchmark')} AND "
                f'({TEXT} : ("v2"* AND "0"* AND "1"*) OR {{version}} : ^"2 0 1")',
            ),
            (
                "re\u0301sume\u0301 20.04",
                f'{word("résumé")} AND ({TEXT} : ("20"* AND "04"*) OR {{version}} : ^"20 04")',
            ),
            ("v18", f'({TEXT} : "v18"* OR {{version}} : ^"18")'),
            ("V2.1", f'({TEXT} : ("V2"* AND "1"*) OR {{version}} : ^"2 1")'),
        ],
    )
    def test_a_version_shaped_term_is_also_matched_from_the_start_of_the_version(
        self, raw_query: str, expected: str
    ):
        """A dotted number or v-number may be a number in a title or the start of a version."""
        assert build_fts_query(raw_query) == expected

    @pytest.mark.parametrize("raw_query", ["", "   ", "...", "!!!", "***", '""', "()", "___"])
    def test_empty_whitespace_and_punctuation_only_return_empty_string(self, raw_query: str):
        """Test inputs with no word characters return an empty string."""
        assert build_fts_query(raw_query) == ""


class TestBuildVersionMatchQuery:
    """The query for rows a search matches through their version, not only through a title."""

    @pytest.mark.parametrize(
        ("raw_query", "expected"),
        [
            (
                "kubernetes v2.0.0",
                f"{word('kubernetes')} AND "
                f'({TEXT} : ("v2"* AND "0"* AND "0"*) OR {{version}} : ^"2 0 0") AND '
                '({version} : ^"2 0 0")',
            ),
            (
                "22.04 v1.0",
                f'({TEXT} : ("22"* AND "04"*) OR {{version}} : ^"22 04") AND '
                f'({TEXT} : ("v1"* AND "0"*) OR {{version}} : ^"1 0") AND '
                '({version} : ^"22 04" OR {version} : ^"1 0")',
            ),
        ],
    )
    def test_the_whole_query_with_one_of_its_versions_matched_in_the_version(
        self, raw_query: str, expected: str
    ):
        assert build_version_match_query(raw_query) == expected

    @pytest.mark.parametrize("raw_query", ["kubernetes", "almalinux 8", "oracle_9", "vmware", ""])
    def test_a_query_without_a_version_has_none(self, raw_query: str):
        assert build_version_match_query(raw_query) == ""


class TestVersionIndexText:
    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("v2.1.0", "2.1.0"),
            ("V8", "8"),
            (" v7.1.0 (vNext)", "7.1.0 (vNext)"),
            ("2.1.0", "2.1.0"),
            ("vNext", "vNext"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_the_leading_v_of_a_numbered_version_is_dropped(self, version, expected: str):
        assert version_index_text(version) == expected
