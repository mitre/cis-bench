# XCCDF Export Styles - Complete Specification

!!! info "Documentation Path"
**You are here:** Technical Reference > XCCDF Styles Comparison

**For practical usage:** See [Workflows](../user-guide/workflows.md) | [Commands Reference](../user-guide/commands-reference.md)

## Overview

CIS Benchmark CLI supports TWO [XCCDF](../about/glossary.md#xccdf) export [styles](../about/glossary.md#style):

1. **DISA/DoD Style** - STIG-compatible for DoD compliance tools (Uses XCCDF 1.1.4)
2. **CIS Native Style** - Clean CIS-centric format for general XCCDF tools (Uses XCCDF 1.2)

**XCCDF Version Difference**:

- DISA STIGs use XCCDF 1.1.4 (NOT 1.2)
- XCCDF 1.1.4 allows simple IDs (`CIS-6_1_1`)
- XCCDF 1.2 requires pattern IDs (`xccdf_org.cisecurity_rule_*`)
- Config specifies version, MappingEngine loads appropriate models

Both styles use different XCCDF versions AND different conventions for mapping CIS Benchmark concepts to XCCDF elements.

## Style Selection

```bash
# DISA/DoD STIG-compatible export
cis-bench export benchmark.json --format xccdf --style disa

# CIS native clean export
cis-bench export benchmark.json --format xccdf --style cis

# Default: DISA style (most compatible)
cis-bench export benchmark.json --format xccdf
```

---

## Style 1: DISA/DoD XCCDF (STIG-Compatible)

### Purpose

- Compatible with DoD STIG tools and workflows
- Uses DISA STIG conventions
- Includes CCI (Control Correlation Identifiers) for NIST 800-53 mapping
- Follows STIG element structure and naming

### Target Tools

- DISA SCAP Compliance Checker (SCC)
- OpenSCAP (DoD configurations)
- DISA STIG Viewer
- Nessus (Government configurations)
- Any tool expecting DISA STIG format

### Complete Rule Structure

A Rule for a recommendation with ref 3.1.1, CIS Controls v8 4.8 and v7 9.2, and the NIST
controls CM-7 and AC-3 (element text shortened):

```xml
<Rule id="SV-030101r1_rule" severity="medium" weight="10.0">

<!-- The recommendation's ref -->
<version>3.1.1</version>

<title>Ensure the example service is disabled</title>

<!-- DISA's embedded tags; empty ones are kept -->
<description>
&lt;VulnDiscussion&gt;The recommendation's description and rationale.&lt;/VulnDiscussion&gt;
&lt;FalsePositives&gt;&lt;/FalsePositives&gt;
&lt;FalseNegatives&gt;&lt;/FalseNegatives&gt;
&lt;Documentable&gt;false&lt;/Documentable&gt;
&lt;Mitigations&gt;Additional information, when the recommendation has it&lt;/Mitigations&gt;
&lt;SeverityOverrideGuidance&gt;&lt;/SeverityOverrideGuidance&gt;
&lt;PotentialImpacts&gt;The recommendation's impact, when it has one&lt;/PotentialImpacts&gt;
&lt;ThirdPartyTools&gt;&lt;/ThirdPartyTools&gt;
&lt;MitigationControl&gt;&lt;/MitigationControl&gt;
&lt;Responsibility&gt;&lt;/Responsibility&gt;
&lt;IAControls&gt;&lt;/IAControls&gt;
</description>

<!-- NIST controls the CCIs below do not cover: AC-3 (4.8's CCI covers CM-7) -->
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:title>NIST SP 800-53</dc:title>
<dc:identifier>AC-3</dc:identifier>
</reference>

<!-- The primary CCI of each CIS Controls v8 safeguard (cis-cci-mapping.json);
     CCI-000366 when none has one -->
<ident system="http://cyber.mil/cci">CCI-001762</ident>

<!-- CIS Controls and MITRE ATT&CK -->
<ident system="https://www.cisecurity.org/controls/v7">7:9.2</ident>
<ident system="https://www.cisecurity.org/controls/v8">8:4.8</ident>
<ident system="https://attack.mitre.org/techniques">T1068</ident>
<ident system="https://attack.mitre.org/tactics">TA0004</ident>
<ident system="https://attack.mitre.org/mitigations">M1042</ident>

<!-- Remediation -->
<fixtext fixref="F-3_1_1">The recommendation's remediation.</fixtext>
<fix id="F-3_1_1"/>

<!-- Audit -->
<check system="C-3_1_1">
<check-content>The recommendation's audit procedure.</check-content>
</check>

</Rule>
```

### CIS Field DISA Element Mapping

| CIS Field | DISA Element | Location | Notes |
|-----------|--------------|----------|-------|
| ref | `<version>` | Direct | CIS 3.1.1 STIG ID equivalent |
| title | `<title>` | Direct | Unchanged |
| description | `<description>` VulnDiscussion (first part) | Embedded | Strip HTML tags |
| rationale | `<description>` VulnDiscussion (second part) | Embedded | Strip HTML tags, append to description |
| impact | `<description>` PotentialImpacts | Embedded | Strip HTML tags |
| additional_info | `<description>` Mitigations | Embedded | If present |
| remediation | `<fixtext>` | Direct | Strip HTML, preserve code blocks |
| audit | `<check><check-content>` | Nested | Strip HTML, preserve code blocks |
| cis_controls | `<ident>` per CIS Controls version | Direct | `system` names the version, value `8:4.8` |
| mitre_mapping | `<ident>` per technique, tactic and mitigation | Direct | `system` under attack.mitre.org |
| profiles | Benchmark `<Profile>` with a `<select>` per Rule | Benchmark | One Profile per profile, e.g. `level-1-server` |
| cis_controls (v8, via CCI mapping) | `<ident system="http://cyber.mil/cci">` | Direct | Primary CCI of each v8 safeguard (`cci_lookup.extract: primary`) |
| nist_controls (extras) | `<reference>` with `dc:title` and `dc:identifier` | Direct | Only controls the CCIs do not cover |

### Attributes

| Attribute | Value | Reasoning |
|-----------|-------|-----------|
| Rule/@severity | "medium" | CIS has no severity concept, default to medium (CAT II equivalent) |
| Rule/@weight | "10.0" | DISA standard weight |
| Rule/@id | `SV-{stig_number}r1_rule` | STIG rule id from the ref (3.1.1 gives `SV-030101r1_rule`) |
| Group/@id | `V-{stig_number}` | STIG group id from the ref |
| fixtext/@fixref | `F-{ref_normalized}` | Links to fix element |
| fix/@id | `F-{ref_normalized}` | Matches fixref |
| check/@system | `C-{ref_normalized}` | Synthetic check ID |

### CCI + NIST Deduplication Algorithm

**Goal**: use CCIs (the DoD standard) where the mapping gives them, and add a NIST reference
only for each cited NIST control no CCI on the rule covers. The full rules are in
[CCI + NIST Deduplication Algorithm](#cci-nist-deduplication-algorithm-disa-style-only).

**Input**:

- The recommendation's CIS Controls: v8 "4.8" (and its v7 control, which is not looked up)
- Its NIST controls: ["CM-7", "SI-3", "MP-7"]
- The mapping entry for 4.8 in `cis-cci-mapping.json`:
```json
{
"cis_id": "4.8",
"primary_cci": {"cci": "CCI-001762", "nist_control": "CM-7 (1) (b)"},
"supporting_ccis": [
{"cci": "CCI-000382", "nist_control": "CM-7 b"},
{"cci": "CCI-000381", "nist_control": "CM-7 a"},
{"cci": "CCI-000384", "nist_control": "CM-7 (1) (a)"}
],
"mapping_status": "OFFICIAL"
}
```

**Step 1**: the DISA style takes the primary CCI (`extract: "primary"`): CCI-001762.

**Step 2**: it covers the base control of its `nist_control`: CM-7.

**Step 3**: "CM-7" is covered; "SI-3" and "MP-7" are not.

**Step 4**: output
```xml
<ident system="http://cyber.mil/cci">CCI-001762</ident>
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:title>NIST SP 800-53</dc:title><dc:identifier>SI-3</dc:identifier>
</reference>
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:title>NIST SP 800-53</dc:title><dc:identifier>MP-7</dc:identifier>
</reference>
```

### Why This Normalization Is Correct

**Respects source material**: Uses exactly what CIS authors cited
**DoD compliant**: Uses CCI (standard DoD method)
**No duplication**: CM-7 not stated twice
**No invention**: Does not add NIST controls CIS didn't cite
**Preserves extras**: CIS-specific NIST citations become references
**Tool compatible**: DISA tools understand CCIs, ignore CIS metadata

---

## Style 2: CIS Native XCCDF (Clean Format)

### Purpose

- Clean, CIS-centric XCCDF export
- No DoD baggage (no CCI, no VMS tags)
- Optimized for non-DoD XCCDF tools
- Preserves all CIS-specific data

### Target Tools

- OpenSCAP (commercial/non-DoD)
- Generic XCCDF validators
- Custom compliance tools
- Research/analysis tools

### Complete Rule Structure

```xml
<Rule id="xccdf_org.cisecurity.benchmarks_rule_3_1_1">

<!-- CIS Reference -->
<version>3.1.1</version>

<!-- Title -->
<title>Ensure kubeconfig file permissions are set to 644 or more restrictive</title>

<!-- Clean separated content (no embedded XML tags) -->
<description>
If kubelet is running, and if it is configured by a kubeconfig file, ensure
that the proxy kubeconfig file has permissions of 644 or more restrictive.
</description>

<rationale>
Improper access permissions could allow unauthorized users to access
sensitive configuration data.
</rationale>

<!-- Impact as warning (XCCDF standard for caveats) -->
<warning category="general">
None expected
</warning>

<!-- Direct NIST 800-53 references -->
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:title>NIST SP 800-53</dc:title>
<dc:identifier>CM-7</dc:identifier>
</reference>
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:title>NIST SP 800-53</dc:title>
<dc:identifier>SI-3</dc:identifier>
</reference>
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:title>NIST SP 800-53</dc:title>
<dc:identifier>MP-7</dc:identifier>
</reference>

<!-- CIS-specific metadata (standard XCCDF metadata element) -->
<metadata>
<!-- Profiles -->
<cis-profile>Level 1 - Server</cis-profile>
<cis-profile>Level 1 - Workstation</cis-profile>

<!-- CIS Controls v8 -->
<cis-control version="8">
<control-id>4.8</control-id>
<title>Uninstall or Disable Unnecessary Services on Enterprise Assets and Software</title>
<ig1>false</ig1>
<ig2>true</ig2>
<ig3>true</ig3>
</cis-control>

<!-- CIS Controls v7 -->
<cis-control version="7">
<control-id>9.2</control-id>
<title>Ensure Only Approved Ports, Protocols and Services Are Running</title>
<ig1>false</ig1>
<ig2>true</ig2>
<ig3>true</ig3>
</cis-control>

<!-- MITRE ATT&CK -->
<mitre-attack>
<technique>T1068</technique>
<technique>T1203</technique>
<tactic>TA0001</tactic>
<mitigation>M1022</mitigation>
</mitre-attack>

<!-- Assessment type -->
<assessment-status>Automated</assessment-status>

<!-- Artifacts (if present) -->
<artifacts>
<artifact id="1.1.1.1.1" status="draft">
Script Check Engine Check "nix_module_chk_v3.sh"...
</artifact>
</artifacts>
</metadata>

<!-- Remediation -->
<fixtext>
Run the following command:
chmod 644 /var/lib/kubelet/kubeconfig
</fixtext>

<!-- Audit/Check -->
<check>
<check-content>
Run the following command:
stat -c %a /var/lib/kubelet/kubeconfig

Verify the permissions are 644 or more restrictive.
</check-content>
</check>

</Rule>
```

### CIS Field CIS Native Element Mapping

| CIS Field | CIS Native Element | Location | Notes |
|-----------|-------------------|----------|-------|
| ref | `<version>` | Direct | CIS reference number |
| title | `<title>` | Direct | Unchanged |
| description | `<description>` | Direct | Clean, no embedded tags |
| rationale | `<rationale>` | Direct | Separate element |
| impact | `<warning category="general">` | Direct | XCCDF standard for impacts |
| additional_info | `<metadata>` additional-info | Custom | If present |
| remediation | `<fixtext>` | Direct | Same as DISA |
| audit | `<check><check-content>` | Nested | Same as DISA |
| profiles | `<metadata>` cis-profile | Custom | Level/workload tags |
| cis_controls | `<metadata>` cis-control | Custom | v7/v8 with IG groups |
| mitre_mapping | `<metadata>` mitre-attack | Custom | Techniques/tactics/mitigations |
| nist_controls | `<reference><dc:identifier>` | Direct | All NIST controls (no CCI) |
| artifacts | `<metadata>` artifacts | Custom | Test artifacts |
| assessment_status | `<metadata>` assessment-status | Custom | Automated/Manual |

### Differences from DISA Style

| Aspect | DISA Style | CIS Native Style |
|--------|------------|------------------|
| **Description structure** | Embedded XML tags (VulnDiscussion, etc.) | Clean separate elements |
| **NIST mapping** | Via CCIs (`<ident>`) | Direct references |
| **CIS Controls** | `<ident>` per version | `<metadata>` cis_controls and `<ident>` with controlURI |
| **MITRE** | `<ident>` | `<ident>` |
| **Rationale** | Embedded in VulnDiscussion | Separate `<rationale>` element |
| **Impact** | Embedded as PotentialImpacts | `<warning>` element |
| **Complexity** | Higher (DoD conventions) | Lower (clean structure) |
| **Target audience** | DoD/Government | Commercial/General |

---

## CCI + NIST Deduplication Algorithm (DISA Style Only)

### Purpose
Avoid duplicating NIST control references when CCIs already provide that mapping.

### The mapping file

`src/cis_bench/data/cis-cci-mapping.json` maps each CIS Controls v8 safeguard (`cis_id`,
"4.8") to DISA CCIs: a `primary_cci` and up to three `supporting_ccis`, each with its
`cci`, `confidence`, `reasoning` and `nist_control` (the CCI's NIST SP 800-53 Rev 5 index
in DISA's CCI list, such as "CM-7 (1) (b)"). `mapping_status` is:

- `OFFICIAL`: the safeguard's NIST controls are CIS's own, and its CCIs are DISA's for those
  controls. Only these entries give CCIs.

- `INFERRED`: CCIs kept as research data; they give no CCIs and cover nothing.
- `UNMAPPED`: no CCI fits; no `primary_cci`.

`utils/cci_lookup.py` reads every entry through one reader and refuses an OFFICIAL entry
whose primary CCI is missing or any of whose CCIs lacks `cci` or `nist_control`.

### Algorithm

For each recommendation, once:

1. Look up only the CIS Controls of the version the mapping file is keyed by
   (`cci_lookup.cis_controls_version: 8` in `disa.yaml`); v7 numbers name unrelated v8
   safeguards.
2. Collect each safeguard's CCIs (`extract: "primary"` in the DISA style: the primary CCI
   only; `"all"` adds the supporting CCIs), each CCI once.
3. A CCI covers the base control of its `nist_control`: the family and number at its
   start ("CM-7 (1) (b)" covers CM-7, "SC-7 (4) (b)" covers SC-7).
4. Every NIST control the recommendation cites whose base control no CCI covers becomes a
   `<reference>` (`source_logic: "nist_after_cci_deduplication"`), with the `dc_elements`
   the field names.
5. A recommendation with no CCI gets `fallback_cci` (CCI-000366, CM-6 b), and all its NIST
   controls become references.

### NIST Control Matching Rules

Matching compares base controls, both ways: a CCI for "CM-7 (5)" or "CM-7 b" covers a
citation of "CM-7", "CM-7(4)" or "CM-7.1", and a CCI for "CM-7" covers "CM-7 (5)". The
cited control is written as a reference only when its family and number differ from every
covered base control.

### Edge Cases

- **A recommendation with no CIS Controls** (older benchmarks): the fallback CCI, and every
  NIST control as a reference.

- **A safeguard that is INFERRED, UNMAPPED or not in the file**: it adds no CCI; if no other
  safeguard of the recommendation does, the fallback CCI applies.

---

## Comparison Matrix

| Feature | DISA Style | CIS Native Style |
|---------|------------|------------------|
| **Use case** | DoD compliance, STIG viewers | General compliance, analysis |
| **NIST mapping** | CCIs (DoD standard) | Direct references |
| **Description** | VulnDiscussion + legacy tags | Clean description + rationale |
| **CIS Controls** | `<ident>` | `<metadata>` and `<ident>` |
| **MITRE** | `<ident>` | `<ident>` |
| **Profiles** | Benchmark `<Profile>` | Benchmark `<Profile>` |
| **Validation** | DISA STIG tools | Generic XCCDF tools |
| **File size** | Smaller (no duplicated NIST) | Slightly larger |
| **Complexity** | Higher | Lower |

---

## Implementation Plan

### Phase 1: DISA Style Exporter
1. Add `cci_mappings: List[str]` to Pydantic Recommendation model
2. Create `cis_bench/utils/cci_lookup.py` - Load and query cis-cci-mapping.json
3. Enhance `cis_bench/exporters/xccdf_exporter.py`:

- Add CCI lookup
- Implement deduplication algorithm
- Add `<ident>` elements
- Structure description with VulnDiscussion/PotentialImpacts/Mitigations
- Add fixtext, fix, check elements
- Add severity, weight attributes
4. Test with DISA tools

### Phase 2: CIS Native Exporter
1. Create `cis_bench/exporters/xccdf_cis_exporter.py`
2. Clean structure (no embedded tags)
3. Separate rationale element
4. Direct NIST references (all of them)
5. Rich metadata with CIS/MITRE data
6. Test validation

### Phase 3: CLI Integration
1. Add `--style disa|cis` flag to export command
2. Default to DISA (broader compatibility)
3. Document both in README

---

## Testing Strategy

### DISA Style Validation
```bash
# Export
cis-bench export benchmark.json --format xccdf --style disa -o disa_output.xml

# Parse with stig_parser (should work!)
python -c "from stig_parser import convert_xccdf; ..."

# Validate structure
cis-bench validate disa_output.xml
```

### CIS Style Validation
```bash
# Export
cis-bench export benchmark.json --format xccdf --style cis -o cis_output.xml

# Validate
cis-bench validate cis_output.xml

# Check for CIS metadata
grep -o '<cis-control' cis_output.xml | wc -l # Should find CIS controls
```

### Comparison Test
```bash
# Export same benchmark in both styles
cis-bench export alma8.json --format xccdf --style disa -o alma8_disa.xml
cis-bench export alma8.json --format xccdf --style cis -o alma8_cis.xml

# Compare
diff <(xmllint --format alma8_disa.xml) <(xmllint --format alma8_cis.xml)

# Should show:
# - DISA has <ident> elements
# - DISA has VulnDiscussion structure
# - CIS has separate <rationale>
# - CIS has more <reference> elements (no CCI deduplication)
```

---

## Future Enhancements

### v1.1 - Style Auto-Detection on Import

- Parse existing XCCDF
- Detect: Has CCIs? DISA style
- Detect: Has `<rationale>`? CIS style
- Round-trip: Import Modify Export in same style

### v1.2 - Hybrid Style

- Best of both worlds
- CCIs AND direct NIST references (explicit redundancy for maximum compatibility)
- User choice: `--style hybrid`

### v1.3 - Custom Styles

- User-defined XCCDF templates (Jinja2)
- Corporate branding
- Custom metadata namespaces

---
