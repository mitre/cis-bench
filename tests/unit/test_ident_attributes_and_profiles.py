"""Unit tests for namespaced ident attributes and generated profile ids."""

import logging

import pytest

from cis_bench.exporters.mapping_engine import MappingEngine
from cis_bench.models.benchmark import Recommendation

CC8_URI = "http://cisecurity.org/20-cc/v8.0"


@pytest.fixture
def cis_engine(cis_config_path):
    return MappingEngine(cis_config_path)


@pytest.fixture
def disa_engine(disa_config_path):
    return MappingEngine(disa_config_path)


def _ident(engine):
    return engine.get_xccdf_class("IdentType")(value="8:4.1", system="urn:test")


def _rec(ref, profiles):
    return Recommendation(
        ref=ref,
        title=f"Rec {ref}",
        url=f"https://workbench.cisecurity.org/recommendations/{ref}",
        assessment_status="Automated",
        profiles=profiles,
    )


class TestSetIdentAttribute:
    def test_prefixed_attribute_uses_clark_notation(self, cis_engine):
        ident = _ident(cis_engine)
        cis_engine._set_ident_attribute(
            ident,
            {"name": "controlURI", "namespace_prefix": "cc8", "template": "uri-{id}"},
            {"id": "4.1"},
        )
        assert ident.other_attributes == {f"{{{CC8_URI}}}controlURI": "uri-4.1"}

    def test_unprefixed_attribute_uses_bare_name(self, cis_engine):
        ident = _ident(cis_engine)
        cis_engine._set_ident_attribute(ident, {"name": "note", "template": "x"}, {})
        assert ident.other_attributes == {"note": "x"}

    def test_unknown_prefix_warns_and_uses_bare_name(self, cis_engine, caplog):
        ident = _ident(cis_engine)
        with caplog.at_level(logging.WARNING):
            cis_engine._set_ident_attribute(
                ident, {"name": "controlURI", "namespace_prefix": "nope", "template": "v"}, {}
            )
        assert ident.other_attributes == {"controlURI": "v"}
        assert "nope" in caplog.text

    def test_missing_name_is_ignored(self, cis_engine):
        ident = _ident(cis_engine)
        cis_engine._set_ident_attribute(ident, {"template": "v"}, {})
        assert ident.other_attributes == {}

    def test_ident_without_other_attributes_warns(self, disa_engine, caplog):
        ident = _ident(disa_engine)  # XCCDF 1.1.4 IdentType has no other_attributes
        with caplog.at_level(logging.WARNING):
            disa_engine._set_ident_attribute(
                ident, {"name": "controlURI", "namespace_prefix": "cc8", "template": "v"}, {}
            )
        assert not hasattr(ident, "other_attributes")
        assert "controlURI" in caplog.text


class TestProfileSlug:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("SEVERITY: CAT II", "severity-cat-ii"),
            ("Level 1 - Database Engine", "level-1-database-engine"),
            ("1 - Basic", "profile-1-basic"),
            ("!!!", "profile"),
        ],
    )
    def test_slug(self, name, expected):
        assert MappingEngine._profile_slug(name, set()) == expected

    def test_slug_dedupes_against_used_ids(self):
        used = {"level-1", "level-1-2"}
        assert MappingEngine._profile_slug("Level 1", used) == "level-1-3"


class TestIncludeUnmappedProfiles:
    def test_unmapped_names_become_profiles(self, cis_engine):
        recs = [_rec("1.1", ["Level 1", "SEVERITY: CAT II"]), _rec("1.2", ["Level 1"])]
        config = {
            "generate_from_rules": True,
            "include_unmapped": True,
            "unmapped_description": "CIS {name} profile",
            "profile_mappings": [],
        }
        profiles = {p.id: p for p in cis_engine.generate_profiles_from_rules(recs, config)}
        assert set(profiles) == {"level-1", "severity-cat-ii"}
        assert len(profiles["level-1"].select) == 2
        assert profiles["level-1"].description[0].content[0] == "CIS Level 1 profile"

    def test_unmapped_slug_avoids_explicit_ids(self, cis_engine):
        recs = [_rec("1.1", ["Level 1 - Server", "Level 1 Server"])]
        config = {
            "generate_from_rules": True,
            "include_unmapped": True,
            "profile_mappings": [
                {"match": "Level 1 - Server", "id": "level-1-server", "title": "L1 Server"}
            ],
        }
        ids = [p.id for p in cis_engine.generate_profiles_from_rules(recs, config)]
        assert ids == ["level-1-server", "level-1-server-2"]

    def test_without_include_unmapped_only_explicit_profiles(self, cis_engine):
        recs = [_rec("1.1", ["Level 1"])]
        config = {"generate_from_rules": True, "profile_mappings": []}
        assert cis_engine.generate_profiles_from_rules(recs, config) == []
