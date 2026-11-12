# XCCDF Export Guide

Complete guide to exporting CIS benchmarks to NIST XCCDF format with two style options: DISA STIG and CIS native.

!!! info "Documentation Path"
**You are here:** User Guide > XCCDF Export

- **For technical details:** See [XCCDF Styles Comparison](../technical-reference/xccdf-styles.md)
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
- One ident per CIS Controls mapping, in the form CIS-CAT benchmark XCCDF uses: `system` names the Controls version (`http://cisecurity.org/20-cc/v8.0`) and a `cc7:`/`cc8:controlURI` attribute names the safeguard (`.../control/3/subcontrol/14`), or the whole control when the mapping has no safeguard (`.../control/13`)
- MITRE ATT&CK mappings (techniques, tactics, mitigations) as ident elements
- CIS Profiles (Level 1/2, Server/Workstation)
- NIST SP 800-53 references with Dublin Core
- Separate rationale element

### Output Example

```xml
<Rule id="xccdf_org.cisecurity.benchmarks_rule_6_1_1">
<title>Ensure AIDE is installed</title>
<description>AIDE is an intrusion detection tool...</description>

<metadata>
<controls:cis_controls>
<controls:framework urn="urn:cisecurity.org:controls:8">
<controls:safeguard title="Log Sensitive Data Access"
urn="urn:cisecurity.org:controls:8:3.14">
<controls:implementation_groups ig1="false" ig2="false" ig3="true"/>
<controls:asset_type>Unknown</controls:asset_type>
<controls:security_function>Protect</controls:security_function>
</controls:safeguard>
</controls:framework>
</controls:cis_controls>
</metadata>

<ident system="http://cisecurity.org/20-cc/v8.0"
cc8:controlURI="http://cisecurity.org/20-cc/v8.0/control/3/subcontrol/14"/>
<ident system="http://cisecurity.org/20-cc/v7.0"
cc7:controlURI="http://cisecurity.org/20-cc/v7.0/control/8/subcontrol/11"/>
<ident system="https://attack.mitre.org/techniques">T1565.001</ident>
<ident system="https://attack.mitre.org/tactics">TA0001</ident>
<ident system="https://attack.mitre.org/mitigations">M1022</ident>

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
| CCI Mappings | Yes (626 CCIs) | No |
| CIS Controls | As idents (681) | Ident + metadata (dual) |
| MITRE ATT&CK | As idents (1570) | As idents (cleaner) |
| NIST 800-53 | Via CCIs + references | Direct Dublin Core |
| VulnDiscussion | Yes (embedded tags) | No (separate rationale) |
| Profiles | Benchmark level (4) | Benchmark level (4) |
| File Size (322 recs) | 1.5 MB | 1.8 MB |
| Target Tools | DISA SCC, STIG Viewer, **Vulcan** | CIS-CAT, OpenSCAP |

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
for file in ~/.local/share/cis-bench/benchmarks/*.json; do
cis-bench export "$file" --format xccdf --style cis
done
```

### Validation

The exported XCCDF validates against:

- NIST XCCDF 1.2 schema (CIS style)
- NIST XCCDF 1.1.4 schema (DISA style)

Validate with the schemas shipped in cis-bench:
```bash
cis-bench validate output.xml
```

The command picks the schema from the document's XCCDF version and exits `0` when it is valid, `2` when it is not (each error with its line). See [`cis-bench validate`](commands-reference.md#cis-bench-validate).

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

- [XCCDF Styles Design](../technical-reference/xccdf-styles.md) - Technical details
- [Mapping Engine](../technical-reference/mapping-engine-design.md) - How it works
