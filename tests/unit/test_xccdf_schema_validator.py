"""The XCCDF schema validator picks the shipped schema from the document's namespace and
reports validity the way ``oscap xccdf validate`` does: valid, invalid with line numbers, or
not an XCCDF document at all."""

from pathlib import Path

import pytest
from lxml import etree

from cis_bench.validators.xccdf_schema import (
    NotXccdfError,
    check_xccdf,
    untrusted_xml_parser,
    validate_xccdf,
)

XCCDF_1_1 = "http://checklists.nist.gov/xccdf/1.1"
XCCDF_1_2 = "http://checklists.nist.gov/xccdf/1.2"


def _benchmark(namespace: str, benchmark_id: str, *children: str) -> str:
    body = "\n".join(children)
    return (
        f'<Benchmark xmlns="{namespace}" id="{benchmark_id}">\n'
        f"<status>draft</status>\n{body}\n<version>1</version>\n</Benchmark>\n"
    )


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


class TestValidDocuments:
    def test_a_valid_xccdf_1_2_document_validates(self, tmp_path):
        path = _write(tmp_path, "b.xml", _benchmark(XCCDF_1_2, "xccdf_org.example_benchmark_t"))

        result = validate_xccdf(path)

        assert result.is_valid
        assert result.version == "1.2"
        assert result.errors == []

    def test_a_valid_xccdf_1_1_document_validates(self, tmp_path):
        path = _write(tmp_path, "b.xml", _benchmark(XCCDF_1_1, "t"))

        result = validate_xccdf(path)

        assert result.is_valid
        assert result.version == "1.1"

    def test_an_official_disa_stig_validates(self, xccdf_fixtures):
        official = xccdf_fixtures / "official" / "disa" / "U_RHEL_9_STIG_V2R5_Manual-xccdf.xml"

        result = validate_xccdf(official)

        assert result.version == "1.1"
        assert result.is_valid, result.errors[:3]


class TestInvalidDocuments:
    def test_an_unexpected_element_is_reported_with_its_line(self, tmp_path):
        path = _write(
            tmp_path, "b.xml", _benchmark(XCCDF_1_2, "xccdf_org.example_benchmark_t", "<bogus/>")
        )

        result = validate_xccdf(path)

        assert not result.is_valid
        assert result.version == "1.2"
        assert len(result.errors) == 1
        assert result.errors[0].startswith("line 3: ")
        assert "bogus" in result.errors[0]

    def test_an_external_entity_is_never_resolved(self, tmp_path):
        secret = _write(tmp_path, "secret.txt", "the-secret-value")
        path = _write(
            tmp_path,
            "b.xml",
            f'<!DOCTYPE Benchmark [<!ENTITY leak SYSTEM "{secret.as_uri()}">]>\n'
            + _benchmark(XCCDF_1_2, "xccdf_org.example_benchmark_t", "<title>&leak;</title>"),
        )

        with pytest.raises(NotXccdfError, match="document type declaration") as refused:
            validate_xccdf(path)

        assert "the-secret-value" not in str(refused.value)


class TestDocumentsGivenAsBytes:
    """An export is checked before it is written, so the check takes the serialized bytes."""

    def test_a_document_given_as_bytes_reports_errors_with_their_lines(self):
        content = _benchmark(XCCDF_1_2, "xccdf_org.example_benchmark_t", "<bogus/>").encode()

        result = check_xccdf(content, "export of 23598")

        assert not result.is_valid
        assert result.version == "1.2"
        assert len(result.errors) == 1
        assert result.errors[0].startswith("line 3: ")
        assert "bogus" in result.errors[0]

    def test_a_valid_document_given_as_bytes_validates(self):
        content = _benchmark(XCCDF_1_1, "t").encode()

        result = check_xccdf(content, "export of 23598")

        assert result.is_valid
        assert result.version == "1.1"

    def test_bytes_that_are_not_xccdf_are_refused_by_their_source_name(self):
        with pytest.raises(NotXccdfError, match="^export of 23598: not an XCCDF document"):
            check_xccdf(b'<html xmlns="http://www.w3.org/1999/xhtml"/>', "export of 23598")


class TestNotXccdf:
    def test_a_document_type_declaration_is_refused(self, tmp_path):
        """XCCDF carries no DOCTYPE; one could only declare entities, which are never expanded."""
        path = _write(
            tmp_path,
            "b.xml",
            "<!DOCTYPE Benchmark>\n" + _benchmark(XCCDF_1_2, "xccdf_org.example_benchmark_t"),
        )

        with pytest.raises(NotXccdfError, match="document type declaration"):
            validate_xccdf(path)

    def test_a_file_that_is_not_xml_is_refused(self, tmp_path):
        path = _write(tmp_path, "notes.txt", "just text\n")

        with pytest.raises(NotXccdfError, match="not XML|not well-formed|parse"):
            validate_xccdf(path)

    def test_an_xml_document_in_another_namespace_is_refused(self, tmp_path):
        path = _write(tmp_path, "page.xml", '<html xmlns="http://www.w3.org/1999/xhtml"/>\n')

        with pytest.raises(NotXccdfError, match="not an XCCDF document"):
            validate_xccdf(path)

    def test_an_xccdf_version_without_a_shipped_schema_is_refused(self, tmp_path):
        path = _write(tmp_path, "b.xml", _benchmark("http://checklists.nist.gov/xccdf/1.0", "t"))

        with pytest.raises(NotXccdfError, match="1.0"):
            validate_xccdf(path)

    def test_a_missing_file_is_refused_by_name(self, tmp_path):
        with pytest.raises(NotXccdfError, match="missing.xml"):
            validate_xccdf(tmp_path / "missing.xml")


class TestTheParserForUserFiles:
    def test_an_internal_entity_is_left_unexpanded(self):
        """The parser never expands entities, whatever the document declares."""
        root = etree.fromstring(
            b'<!DOCTYPE a [<!ENTITY e "expanded">]><a>&e;</a>', untrusted_xml_parser()
        )

        assert root.text is None
        assert [type(child).__name__ for child in root] == ["_Entity"]

    def test_an_external_dtd_is_never_asked_for(self):
        """A DOCTYPE naming an external DTD is recorded, not loaded: lxml never asks any
        resolver for it, so nothing is read from disk or the network."""

        class Recording(etree.Resolver):
            asked: list[str] = []

            def resolve(self, system_url, public_id, context):
                self.asked.append(system_url)
                return self.resolve_string("<!ENTITY e 'from-dtd'>", context)

        parser = untrusted_xml_parser()
        parser.resolvers.add(Recording())

        root = etree.fromstring(
            b'<!DOCTYPE a SYSTEM "http://example.invalid/a.dtd"><a>&e;</a>', parser
        )

        assert Recording.asked == []
        assert root.text is None
