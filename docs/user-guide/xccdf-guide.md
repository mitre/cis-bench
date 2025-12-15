# XCCDF Export Guide

Complete guide to exporting CIS benchmarks to NIST XCCDF format with two style options: DISA STIG and CIS native.

!!! info "Documentation Path"
**You are here:** User Guide > XCCDF Export

- **For technical details:** See [XCCDF Styles Comparison](../technical-reference/XCCDF_STYLES.md)
- **For examples:** See [Workflows](workflows.md)
- **For commands:** See [Commands Reference](commands-reference.md)

## Overview

XCCDF (Extensible Configuration Checklist Description Format) is the standard format for security configuration checklists.

**Two Export Styles:**

1. **DISA** - DISA/DoD STIG-compatible (XCCDF 1.1.4)
2. **CIS** - CIS native format (XCCDF 1.2)

Both styles are fully validated and production-ready.

---

## Quick Start

```bash
# Export to CIS format (default recommended)
cis-bench export benchmark.json --format xccdf --style cis

# Export to DISA format
cis-bench export benchmark.json --format xccdf --style disa

# Specify output file
cis-bench export benchmark.json --format xccdf --style cis -o output.xml
```

---

## DISA Style

**XCCDF 1.1.4 - DISA STIG Compatible**

### Features

- VulnDiscussion structure (combines description + rationale)
- CCI mappings (Control Correlation Identifiers)
- NIST 800-53 controls via CCIs
- Legacy VMS tags (FalsePositives, etc.)
- Compatible with:
- DISA SCAP Compliance Checker (SCC)
- DISA STIG Viewer
- OpenSCAP (DoD configurations)

### Output Example

```xml
<Rule id="xccdf_cis_rule_6_1_1">
<title>Ensure AIDE is installed</title>
<description>
<VulnDiscussion>
AIDE is an intrusion detection tool...

Rationale: By monitoring filesystem state...
</VulnDiscussion>
<FalsePositives></FalsePositives>
...
</description>
<ident system="http://cyber.mil/cci">CCI-000123</ident>
<ident system="http://cyber.mil/cci">CCI-000126</ident>
<fixtext>Run the following command...</fixtext>
</Rule>
```

### Use Cases

- DoD/Federal compliance
- DISA STIGs analysis
- RMF (Risk Management Framework)
- Importing into SCC or STIG Viewer

---

## CIS Style

**XCCDF 1.2 - CIS Native Format**

### Features

- Official CIS Controls structure (nested framework/safeguard)
- cc7/cc8 controlURI attributes on ident elements
- MITRE ATT&CK mappings (techniques, tactics, mitigations)
- CIS Profiles (Level 1/2, Server/Workstation)
- NIST SP 800-53 references with Dublin Core
- Separate rationale element
- Enhanced metadata in custom namespace

### Output Example

```xml
<Rule id="xccdf_org.cisecurity.benchmarks_rule_6_1_1">
<title>Ensure AIDE is installed</title>
<description>AIDE is an intrusion detection tool...</description>

<metadata>
<controls:cis_controls>
<controls:framework urn="urn:cisecurity.org:controls:8.0">
<controls:safeguard title="Log Sensitive Data Access"
urn="urn:cisecurity.org:controls:8.0:3.14">
<controls:implementation_groups ig1="false" ig2="false" ig3="true"/>
<controls:asset_type>Unknown</controls:asset_type>
<controls:security_function>Protect</controls:security_function>
</controls:safeguard>
</controls:framework>
</controls:cis_controls>

<enhanced:mitre>
<enhanced:technique id="T1565.001">T1565.001</enhanced:technique>
<enhanced:tactic id="TA0001">TA0001</enhanced:tactic>
<enhanced:mitigation id="M1022">M1022</enhanced:mitigation>
</enhanced:mitre>
</metadata>

<ident system="http://cisecurity.org/20-cc/v8.0"
cc8:controlURI="http://cisecurity.org/20-cc/v8.0/control/3/subcontrol/14"/>

<rationale>By monitoring filesystem state...</rationale>
<fixtext>Run the following command...</fixtext>
</Rule>
```

### Use Cases

- CIS-CAT compatibility
- General XCCDF tools
- Compliance mapping (MITRE, NIST)
- Security analysis

---

## Comparison

| Feature | DISA Style | CIS Style |
|---------|------------|-----------|
| XCCDF Version | 1.1.4 | 1.2 |
| CCI Mappings | Yes (2161) | No |
| CIS Controls | Flat metadata | Official nested structure |
| MITRE ATT&CK | In metadata | Enhanced namespace |
| NIST 800-53 | Via CCIs | Direct + Dublin Core |
| VulnDiscussion | Yes | No (separate rationale) |
| File Size (322 recs) | 1.4 MB | 1.7 MB |
| Target Tools | DISA SCC, STIG Viewer | CIS-CAT, OpenSCAP |

---

## Advanced Options

### Output File Naming

```bash
# Auto-generated name
cis-bench export benchmark.json --format xccdf --style cis
# Creates: benchmark.xml

# Specify name
cis-bench export benchmark.json --format xccdf --style cis -o custom-name.xml
```

### Batch Export

```bash
# Export all downloaded benchmarks
for file in benchmarks/*.json; do
cis-bench export "$file" --format xccdf --style cis
done
```

### Validation

The exported XCCDF validates against:

- NIST XCCDF 1.2 schema (CIS style)
- NIST XCCDF 1.1.4 schema (DISA style)

Validate with xmllint:
```bash
xmllint --noout --schema xccdf_1.2.xsd output.xml
```

---

## Metadata Included

### DISA Style Metadata

- CCI identifiers (from CIS Controls)
- NIST 800-53 controls
- VulnDiscussion
- Mitigations
- Impact
- References

### CIS Style Metadata

**Official CIS Controls:**

- Version 7.0 and 8.0
- Control URNs
- Implementation groups (IG1, IG2, IG3)
- Asset types
- Security functions

**Enhanced Metadata:**

- MITRE ATT&CK techniques
- MITRE tactics
- MITRE mitigations
- CIS Profiles
- NIST SP 800-53 references

**Reference Elements:**

- Dublin Core metadata
- NIST control identifiers
- Source URLs

---

## Output Files

### Size Expectations

For 322 recommendations:

- DISA: ~1.4 MB
- CIS: ~1.7 MB

Larger benchmarks proportionally larger.

### File Locations

Default: Same directory as input file with `.xml` extension

Specify: Use `-o` option

---

## Troubleshooting

### "No converter registered for _Element"

This is an internal error. Report if you see it.

### Large File Size

XCCDF files are verbose (XML + metadata). This is normal.

### Validation Errors

Both styles validate against NIST schemas. If you get errors:
1. Check you're using correct schema version
2. Report as bug with sample data

---

## See Also

- [XCCDF Styles Design](../technical-reference/XCCDF_STYLES.md) - Technical details
- [Mapping Engine](../technical-reference/MAPPING_ENGINE_DESIGN.md) - How it works
