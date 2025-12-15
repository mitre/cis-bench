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

```xml
<Rule id="xccdf_cis_almalinux8_rule_3_1_1"
severity="medium"
weight="10.0">

<!-- STIG ID (maps to CIS ref) -->
<version>3.1.1</version>

<!-- Title -->
<title>Ensure kubeconfig file permissions are set to 644 or more restrictive</title>

<!-- Description with DISA embedded XML tags -->
<description>
&lt;VulnDiscussion&gt;
If kubelet is running, and if it is configured by a kubeconfig file, ensure
that the proxy kubeconfig file has permissions of 644 or more restrictive.

Improper access permissions could allow unauthorized users to access
sensitive configuration data.
&lt;/VulnDiscussion&gt;
&lt;FalsePositives&gt;&lt;/FalsePositives&gt;
&lt;FalseNegatives&gt;&lt;/FalseNegatives&gt;
&lt;Documentable&gt;false&lt;/Documentable&gt;
&lt;Mitigations&gt;Additional configuration notes if present&lt;/Mitigations&gt;
&lt;SeverityOverrideGuidance&gt;&lt;/SeverityOverrideGuidance&gt;
&lt;PotentialImpacts&gt;None expected&lt;/PotentialImpacts&gt;
&lt;ThirdPartyTools&gt;&lt;/ThirdPartyTools&gt;
&lt;MitigationControl&gt;&lt;/MitigationControl&gt;
&lt;Responsibility&gt;&lt;/Responsibility&gt;
&lt;IAControls&gt;&lt;/IAControls&gt;
</description>

<!-- CCIs (from cis-cci-mapping.json) - DoD standard for NIST mapping -->
<ident system="http://cyber.mil/cci">CCI-000381</ident>
<ident system="http://cyber.mil/cci">CCI-000382</ident>
<ident system="http://cyber.mil/cci">CCI-000380</ident>

<!-- NIST controls NOT covered by CCIs (after deduplication) -->
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:identifier>SI-3</dc:identifier>
</reference>
<reference href="https://csrc.nist.gov/Projects/risk-management/sp800-53-controls">
<dc:identifier>MP-7</dc:identifier>
</reference>

<!-- Remediation (STIG convention) -->
<fixtext fixref="F-3_1_1">
Run the following command:
chmod 644 /var/lib/kubelet/kubeconfig
</fixtext>
<fix id="F-3_1_1"/>

<!-- Check/Audit (STIG convention) -->
<check system="C-3_1_1">
<check-content>
Run the following command:
stat -c %a /var/lib/kubelet/kubeconfig

Verify permissions are 644 or more restrictive.
</check-content>
</check>

<!-- Additional metadata (CIS-specific, standard XCCDF elements) -->
<metadata>
<cis-control version="8" id="4.8">
Uninstall or Disable Unnecessary Services on Enterprise Assets and Software
</cis-control>
<cis-control version="7" id="9.2">
Ensure Only Approved Ports, Protocols and Services Are Running
</cis-control>
<profile>Level 1 - Server</profile>
<profile>Level 1 - Workstation</profile>
<mitre-technique>T1068</mitre-technique>
<mitre-tactic>TA0001</mitre-tactic>
<mitre-mitigation>M1022</mitre-mitigation>
</metadata>

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
| cis_controls | `<metadata>` cis-control | Custom | CIS-specific metadata |
| mitre_mapping | `<metadata>` mitre-* | Custom | Techniques, tactics, mitigations |
| profiles | `<metadata>` profile | Custom | Level 1/2, Server/Workstation |
| nist_controls (via CCI mapping) | `<ident system="http://cyber.mil/cci">` | Direct | Primary + supporting CCIs |
| nist_controls (extras) | `<reference><dc:identifier>` | Direct | Only if NOT covered by CCIs |

### Attributes

| Attribute | Value | Reasoning |
|-----------|-------|-----------|
| Rule/@severity | "medium" | CIS has no severity concept, default to medium (CAT II equivalent) |
| Rule/@weight | "10.0" | DISA standard weight |
| Rule/@id | `xccdf_cis_{platform}_rule_{ref}` | Synthetic ID, CIS-prefixed |
| fixtext/@fixref | `F-{ref}` | Links to fix element |
| fix/@id | `F-{ref}` | Matches fixref |
| check/@system | `C-{ref}` | Synthetic check ID |

### CCI + NIST Deduplication Algorithm

**Goal**: Use CCIs (DoD standard) where available, add NIST references only for extras

**Input**:

- CIS Control from recommendation: "4.8"
- CIS nist_controls: ["CM-7", "SI-3", "MP-7"]
- CCI mapping for 4.8:
```json
{
"primary_cci": {"cci": "CCI-000381", "nist": "CM-7.1"},
"supporting_ccis": [
{"cci": "CCI-000382", "nist": "CM-7.3"},
{"cci": "CCI-000380", "nist": "CM-7.2"}
]
}
```

**Step 1**: Extract all CCIs from mapping
```
CCIs: [CCI-000381, CCI-000382, CCI-000380]
```

**Step 2**: Determine which NIST controls each CCI covers
```
CCI-000381 CM-7.1 covers "CM-7"
CCI-000382 CM-7.3 covers "CM-7"
CCI-000380 CM-7.2 covers "CM-7"
```

**Step 3**: Check each CIS-cited NIST control
```
For "CM-7": Covered by CCIs (CCI-000381, 382, 380)
For "SI-3": NOT in any CCI mapping
For "MP-7": NOT in any CCI mapping
```

**Step 4**: Build output
```xml
<!-- Add ALL CCIs from mapping (they cover CM-7) -->
<ident system="http://cyber.mil/cci">CCI-000381</ident>
<ident system="http://cyber.mil/cci">CCI-000382</ident>
<ident system="http://cyber.mil/cci">CCI-000380</ident>

<!-- Add extras as references (not covered by CCIs) -->
<reference>
<dc:identifier>SI-3</dc:identifier>
</reference>
<reference>
<dc:identifier>MP-7</dc:identifier>
</reference>
```

**Matching Logic for NIST Controls**:
```python
def nist_control_matches(cited, cci_mapped):
"""Check if CCI-mapped control covers cited control.

Examples:
cited="CM-7", cci_mapped="CM-7.1" True
cited="CM-7", cci_mapped="CM-7" True
cited="CM-7.1", cci_mapped="CM-7" False (too broad)
cited="CM-7(5)", cci_mapped="CM-7.1" False (different enhancement)

Logic: Strip enhancement numbers, check if cci_mapped starts with cited
"""
cited_base = cited.split('(')[0] # "CM-7(5)" "CM-7"
cci_base = cci_mapped.split('(')[0] # "CM-7(5)" "CM-7"

# CM-7.1 covers CM-7, but not vice versa
return cci_base.startswith(cited_base)
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
| **CIS Controls** | In metadata only | In metadata |
| **MITRE** | In metadata | In metadata |
| **Rationale** | Embedded in VulnDiscussion | Separate `<rationale>` element |
| **Impact** | Embedded as PotentialImpacts | `<warning>` element |
| **Complexity** | Higher (DoD conventions) | Lower (clean structure) |
| **Target audience** | DoD/Government | Commercial/General |

---

## CCI + NIST Deduplication Algorithm (DISA Style Only)

### Purpose
Avoid duplicating NIST control references when CCIs already provide that mapping.

### Algorithm

**Input**:

- `cis_controls`: List of CIS Control objects from recommendation
- `nist_controls`: List of NIST control IDs cited by CIS authors (e.g., ["CM-7", "SI-3"])
- `cis_cci_mapping`: Loaded from cis-cci-mapping.json

**Process**:

**Step 1**: For each CIS Control, look up CCI mapping
```python
for cis_ctrl in recommendation.cis_controls:
cis_id = f"{cis_ctrl.version}.{cis_ctrl.control}" # "8.4.8" or "7.9.2"

mapping = cis_cci_mapping.get(cis_id)
if mapping:
# Collect CCIs
all_ccis.append(mapping['primary_cci']['cci'])
all_ccis.extend([s['cci'] for s in mapping['supporting_ccis']])
```

**Step 2**: Build CCI NIST reverse map
```python
cci_to_nist = {}
for mapping in cis_cci_mapping.values():
# From primary
cci_to_nist[mapping['primary_cci']['cci']] = extract_nist(mapping['primary_cci'])

# From supporting
for supp in mapping['supporting_ccis']:
cci_to_nist[supp['cci']] = extract_nist(supp)

# Extract NIST from CCI mapping entry
def extract_nist(cci_entry):
# Could be in 'nist' field or need to parse from reasoning
# Return base control: "CM-7.1" "CM-7"
```

**Step 3**: Check which cited NIST controls are covered by CCIs
```python
covered_nist = set()
for cci in all_ccis:
nist_ctrl = cci_to_nist.get(cci)
if nist_ctrl:
base = nist_ctrl.split('(')[0].split('.')[0] # "CM-7(5)" "CM-7"
covered_nist.add(base)
```

**Step 4**: Find NIST controls NOT covered by CCIs
```python
extra_nist = []
for cited in recommendation.nist_controls:
cited_base = cited.split('(')[0].split('.')[0]
if cited_base not in covered_nist:
extra_nist.append(cited)
```

**Output**:
```xml
<!-- All CCIs (cover CM-7) -->
<ident>CCI-000381</ident>
<ident>CCI-000382</ident>
<ident>CCI-000380</ident>

<!-- Extras not covered by CCIs -->
<reference><dc:identifier>SI-3</dc:identifier></reference>
<reference><dc:identifier>MP-7</dc:identifier></reference>
```

### NIST Control Matching Rules

**Matching is hierarchical**:

- CCI maps to "CM-7.1" **covers** citation of "CM-7"
- CCI maps to "CM-7" does **NOT cover** citation of "CM-7.1" (too specific)
- CCI maps to "CM-7(5)" **covers** "CM-7" but not "CM-7(4)" (different enhancement)

**Base matching**:
```python
def cci_covers_citation(cci_nist_control: str, cited_nist_control: str) -> bool:
"""Check if CCI-mapped control covers the cited control.

Examples:
("CM-7.1", "CM-7") True
("CM-7", "CM-7") True
("CM-7", "CM-7.1") False (CCI too broad)
("CM-7.1", "CM-7.1") True
("CM-7.1", "CM-7.2") False (different sub-control)
"""
# Normalize: remove enhancements
cited_base = cited_nist_control.split('(')[0]
cci_base = cci_nist_control.split('(')[0]

# Check if CCI control starts with cited
# "CM-7.1".startswith("CM-7") True
return cci_base.startswith(cited_base)
```

### Edge Cases

**Case 1**: CIS cites "CM-7" but CCI maps to "CM-7(5)"

- Match: CM-7(5) covers CM-7? **YES** (enhancement of CM-7)
- Action: Use CCI

**Case 2**: CIS cites "CM-7.1" but CCI maps to "CM-7"

- Match: CM-7 covers CM-7.1? **NO** (too general)
- Action: Add CM-7.1 as reference (CCI doesn't cover specific sub-control)

**Case 3**: CIS has no CIS Controls (old benchmark)

- No CCI mapping available
- Action: Add all NIST controls as references

**Case 4**: CCI mapping not found for CIS Control

- Mapping incomplete
- Action: Add all NIST controls as references, log warning

### Implementation Notes

**CCI Mapping File**: Bundle cis-cci-mapping.json with tool
```python
# Load once at module import
import json
from pathlib import Path

CCI_MAPPING_FILE = Path(__file__).parent / 'data' / 'cis-cci-mapping.json'

with open(CCI_MAPPING_FILE) as f:
CIS_CCI_MAPPING = json.load(f)
```

**Lookup function**:
```python
def get_ccis_for_cis_control(cis_version: int, cis_control_id: str) -> List[str]:
"""Get all CCIs for a CIS control.

Args:
cis_version: 7 or 8
cis_control_id: "4.8", "10.3", etc.

Returns:
List of CCI identifiers ["CCI-000381", "CCI-000382", ...]
"""
# CCI mapping uses just control number, not version-prefixed
# Both v7 and v8 might map to same CCIs (NIST doesn't change)

mapping = CIS_CCI_MAPPING.get(cis_control_id)
if not mapping:
return []

ccis = []
if mapping.get('primary_cci'):
ccis.append(mapping['primary_cci']['cci'])

for supp in mapping.get('supporting_ccis', []):
ccis.append(supp.get('cci') or supp.get('cci_id'))

return ccis
```

---

## Comparison Matrix

| Feature | DISA Style | CIS Native Style |
|---------|------------|------------------|
| **Use case** | DoD compliance, STIG viewers | General compliance, analysis |
| **NIST mapping** | CCIs (DoD standard) | Direct references |
| **Description** | VulnDiscussion + legacy tags | Clean description + rationale |
| **CIS Controls** | Metadata only | Metadata (primary) |
| **MITRE** | Metadata | Metadata |
| **Profiles** | Metadata | Metadata |
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
cd schemas
XML_CATALOG_FILES=catalog.xml xmllint --schema xccdf_1.2.xsd ../disa_output.xml --noout
```

### CIS Style Validation
```bash
# Export
cis-bench export benchmark.json --format xccdf --style cis -o cis_output.xml

# Validate
xmllint --schema xccdf_1.2.xsd cis_output.xml --noout

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
