"""Tests for CIS Controls and Enhanced Metadata models.

These models are dataclasses used for XCCDF metadata serialization.
Tests verify instantiation, default values, and nested structures.
"""


class TestCISControlsModels:
    """Tests for CIS Controls official structure models."""

    def test_implementation_groups_defaults(self):
        """ImplementationGroups should have None defaults."""
        from cis_bench.models.cis_controls_official import ImplementationGroups

        ig = ImplementationGroups()
        assert ig.ig1 is None
        assert ig.ig2 is None
        assert ig.ig3 is None

    def test_implementation_groups_with_values(self):
        """ImplementationGroups should accept boolean values."""
        from cis_bench.models.cis_controls_official import ImplementationGroups

        ig = ImplementationGroups(ig1=True, ig2=True, ig3=False)
        assert ig.ig1 is True
        assert ig.ig2 is True
        assert ig.ig3 is False

    def test_implementation_groups_meta(self):
        """ImplementationGroups should have correct Meta attributes."""
        from cis_bench.models.cis_controls_official import ImplementationGroups

        assert ImplementationGroups.Meta.name == "implementation_groups"
        assert ImplementationGroups.Meta.namespace == "http://cisecurity.org/controls"

    def test_safeguard_defaults(self):
        """Safeguard should have None/empty defaults."""
        from cis_bench.models.cis_controls_official import Safeguard

        sg = Safeguard()
        assert sg.title is None
        assert sg.urn is None
        assert sg.implementation_groups is None
        assert sg.asset_type is None
        assert sg.security_function is None

    def test_safeguard_with_values(self):
        """Safeguard should accept full values including nested ImplementationGroups."""
        from cis_bench.models.cis_controls_official import (
            ImplementationGroups,
            Safeguard,
        )

        ig = ImplementationGroups(ig1=True, ig2=True, ig3=True)
        sg = Safeguard(
            title="Use Unique Passwords",
            urn="urn:cisecurity.org:controls:8.0:5:2",
            implementation_groups=ig,
            asset_type="Users",
            security_function="Protect",
        )

        assert sg.title == "Use Unique Passwords"
        assert sg.urn == "urn:cisecurity.org:controls:8.0:5:2"
        assert sg.implementation_groups.ig1 is True
        assert sg.asset_type == "Users"
        assert sg.security_function == "Protect"

    def test_safeguard_meta(self):
        """Safeguard should have correct Meta attributes."""
        from cis_bench.models.cis_controls_official import Safeguard

        assert Safeguard.Meta.name == "safeguard"
        assert Safeguard.Meta.namespace == "http://cisecurity.org/controls"

    def test_framework_defaults(self):
        """Framework should have empty list default for safeguards."""
        from cis_bench.models.cis_controls_official import Framework

        fw = Framework()
        assert fw.urn is None
        assert fw.safeguard == []

    def test_framework_with_safeguards(self):
        """Framework should contain multiple safeguards."""
        from cis_bench.models.cis_controls_official import Framework, Safeguard

        sg1 = Safeguard(title="Control 1", urn="urn:1")
        sg2 = Safeguard(title="Control 2", urn="urn:2")

        fw = Framework(
            urn="urn:cisecurity.org:controls:8.0",
            safeguard=[sg1, sg2],
        )

        assert fw.urn == "urn:cisecurity.org:controls:8.0"
        assert len(fw.safeguard) == 2
        assert fw.safeguard[0].title == "Control 1"
        assert fw.safeguard[1].title == "Control 2"

    def test_framework_meta(self):
        """Framework should have correct Meta attributes."""
        from cis_bench.models.cis_controls_official import Framework

        assert Framework.Meta.name == "framework"
        assert Framework.Meta.namespace == "http://cisecurity.org/controls"

    def test_cis_controls_defaults(self):
        """CisControls should have empty list default for frameworks."""
        from cis_bench.models.cis_controls_official import CisControls

        cc = CisControls()
        assert cc.framework == []

    def test_cis_controls_with_frameworks(self):
        """CisControls should contain multiple frameworks (v7, v8)."""
        from cis_bench.models.cis_controls_official import (
            CisControls,
            Framework,
            Safeguard,
        )

        v8_sg = Safeguard(title="v8 Control", urn="urn:v8:1")
        v7_sg = Safeguard(title="v7 Control", urn="urn:v7:1")

        v8_fw = Framework(urn="urn:cisecurity.org:controls:8.0", safeguard=[v8_sg])
        v7_fw = Framework(urn="urn:cisecurity.org:controls:7.0", safeguard=[v7_sg])

        cc = CisControls(framework=[v8_fw, v7_fw])

        assert len(cc.framework) == 2
        assert cc.framework[0].urn == "urn:cisecurity.org:controls:8.0"
        assert cc.framework[1].urn == "urn:cisecurity.org:controls:7.0"

    def test_cis_controls_meta(self):
        """CisControls should have correct Meta attributes."""
        from cis_bench.models.cis_controls_official import CisControls

        assert CisControls.Meta.name == "cis_controls"
        assert CisControls.Meta.namespace == "http://cisecurity.org/controls"


class TestEnhancedMetadataModels:
    """Tests for Enhanced Metadata extension models."""

    def test_technique_defaults(self):
        """Technique should have None/empty defaults."""
        from cis_bench.models.enhanced_metadata import Technique

        t = Technique()
        assert t.id is None
        assert t.value == ""

    def test_technique_with_values(self):
        """Technique should accept MITRE ATT&CK data."""
        from cis_bench.models.enhanced_metadata import Technique

        t = Technique(id="T1565.001", value="Data Manipulation: Stored Data Manipulation")
        assert t.id == "T1565.001"
        assert t.value == "Data Manipulation: Stored Data Manipulation"

    def test_technique_meta(self):
        """Technique should have correct Meta attributes."""
        from cis_bench.models.enhanced_metadata import Technique

        assert Technique.Meta.name == "technique"
        assert Technique.Meta.namespace == "http://cisecurity.org/xccdf/enhanced/1.0"

    def test_tactic_defaults(self):
        """Tactic should have None/empty defaults."""
        from cis_bench.models.enhanced_metadata import Tactic

        t = Tactic()
        assert t.id is None
        assert t.value == ""

    def test_tactic_with_values(self):
        """Tactic should accept MITRE ATT&CK data."""
        from cis_bench.models.enhanced_metadata import Tactic

        t = Tactic(id="TA0040", value="Impact")
        assert t.id == "TA0040"
        assert t.value == "Impact"

    def test_tactic_meta(self):
        """Tactic should have correct Meta attributes."""
        from cis_bench.models.enhanced_metadata import Tactic

        assert Tactic.Meta.name == "tactic"
        assert Tactic.Meta.namespace == "http://cisecurity.org/xccdf/enhanced/1.0"

    def test_mitigation_defaults(self):
        """Mitigation should have None/empty defaults."""
        from cis_bench.models.enhanced_metadata import Mitigation

        m = Mitigation()
        assert m.id is None
        assert m.value == ""

    def test_mitigation_with_values(self):
        """Mitigation should accept MITRE ATT&CK data."""
        from cis_bench.models.enhanced_metadata import Mitigation

        m = Mitigation(id="M1022", value="Restrict File and Directory Permissions")
        assert m.id == "M1022"
        assert m.value == "Restrict File and Directory Permissions"

    def test_mitigation_meta(self):
        """Mitigation should have correct Meta attributes."""
        from cis_bench.models.enhanced_metadata import Mitigation

        assert Mitigation.Meta.name == "mitigation"
        assert Mitigation.Meta.namespace == "http://cisecurity.org/xccdf/enhanced/1.0"

    def test_mitre_metadata_defaults(self):
        """MitreMetadata should have empty list defaults."""
        from cis_bench.models.enhanced_metadata import MitreMetadata

        mm = MitreMetadata()
        assert mm.technique == []
        assert mm.tactic == []
        assert mm.mitigation == []

    def test_mitre_metadata_with_values(self):
        """MitreMetadata should contain techniques, tactics, mitigations."""
        from cis_bench.models.enhanced_metadata import (
            Mitigation,
            MitreMetadata,
            Tactic,
            Technique,
        )

        t1 = Technique(id="T1565.001", value="Data Manipulation")
        t2 = Technique(id="T1485", value="Data Destruction")
        tactic = Tactic(id="TA0040", value="Impact")
        mitigation = Mitigation(id="M1022", value="Restrict Permissions")

        mm = MitreMetadata(
            technique=[t1, t2],
            tactic=[tactic],
            mitigation=[mitigation],
        )

        assert len(mm.technique) == 2
        assert mm.technique[0].id == "T1565.001"
        assert len(mm.tactic) == 1
        assert mm.tactic[0].id == "TA0040"
        assert len(mm.mitigation) == 1
        assert mm.mitigation[0].id == "M1022"

    def test_mitre_metadata_meta(self):
        """MitreMetadata should have correct Meta attributes."""
        from cis_bench.models.enhanced_metadata import MitreMetadata

        assert MitreMetadata.Meta.name == "mitre"
        assert MitreMetadata.Meta.namespace == "http://cisecurity.org/xccdf/enhanced/1.0"

    def test_profile_defaults(self):
        """Profile should have empty string default."""
        from cis_bench.models.enhanced_metadata import Profile

        p = Profile()
        assert p.value == ""

    def test_profile_with_value(self):
        """Profile should accept profile name."""
        from cis_bench.models.enhanced_metadata import Profile

        p = Profile(value="Level 1 - Server")
        assert p.value == "Level 1 - Server"

    def test_profile_meta(self):
        """Profile should have correct Meta attributes."""
        from cis_bench.models.enhanced_metadata import Profile

        assert Profile.Meta.name == "profile"
        assert Profile.Meta.namespace == "http://cisecurity.org/xccdf/enhanced/1.0"

    def test_enhanced_metadata_defaults(self):
        """EnhancedMetadata should have None/empty defaults."""
        from cis_bench.models.enhanced_metadata import EnhancedMetadata

        em = EnhancedMetadata()
        assert em.mitre is None
        assert em.profile == []

    def test_enhanced_metadata_with_values(self):
        """EnhancedMetadata should contain MITRE data and profiles."""
        from cis_bench.models.enhanced_metadata import (
            EnhancedMetadata,
            MitreMetadata,
            Profile,
            Technique,
        )

        tech = Technique(id="T1565", value="Data Manipulation")
        mitre = MitreMetadata(technique=[tech])
        p1 = Profile(value="Level 1 - Server")
        p2 = Profile(value="Level 2 - Server")

        em = EnhancedMetadata(mitre=mitre, profile=[p1, p2])

        assert em.mitre is not None
        assert len(em.mitre.technique) == 1
        assert len(em.profile) == 2
        assert em.profile[0].value == "Level 1 - Server"

    def test_enhanced_metadata_meta(self):
        """EnhancedMetadata should have correct Meta attributes."""
        from cis_bench.models.enhanced_metadata import EnhancedMetadata

        assert EnhancedMetadata.Meta.name == "enhanced"
        assert EnhancedMetadata.Meta.namespace == "http://cisecurity.org/xccdf/enhanced/1.0"
