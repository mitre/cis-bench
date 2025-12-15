# CIS Benchmark InSpec Profile Style Guide

**OHDF-Compliant Format**
**Version:** 1.0.0
**Date:** November 6, 2025

!!! info "Documentation Path"
**You are here:** Technical Reference > InSpec Profile Style Guide

- **For XCCDF export:** See [XCCDF Guide](../user-guide/xccdf-guide.md)
- **For workflow example:** See [Workflows - Scenario 4](../user-guide/workflows.md#scenario-4-generate-inspec-profile-from-cis-benchmark)

## Overview

This style guide defines the standardized format for InSpec profiles generated from CIS Benchmarks. It ensures OHDF (OASIS Heimdall Data Format) compliance and consistency across all CIS Benchmark profiles.

## Control Structure

### Complete Example

```ruby
control 'almalinux-10-cis-6.1.1' do
title 'Ensure AIDE is installed'

# ============================================================================
# DESCRIPTIONS
# ============================================================================

# Main description (REQUIRED)
desc "Advanced Intrusion Detection Environment (AIDE) is an intrusion detection tool
that uses predefined rules to check the integrity of files and directories in the Linux
operating system. AIDE has its own database to check the integrity of files and directories.

By monitoring the filesystem state, compromised files can be detected to prevent or limit
the exposure of accidental or malicious misconfigurations or modified binaries."

# Check procedure (REQUIRED)
desc 'check', 'Run the following command and verify aide is installed:
# rpm -q aide

aide-<version>'

# Remediation (REQUIRED)
desc 'fix', 'Run the following command to install aide:
# dnf install aide
Configure aide as appropriate for your environment.
Initialize aide:
# aide --init
# mv /var/lib/aide/aide.db.new.gz /var/lib/aide/aide.db.gz'

# Optional sub-descriptions (only if present in source benchmark)
desc 'rationale', 'Detailed reasoning for this control...'
desc 'potential_impacts', 'Prelinking feature can interfere with aide...'
desc 'mitigations', 'Run prelink -ua to restore binaries...'
desc 'false_positives', '...'
desc 'false_negatives', '...'

# ============================================================================
# IMPACT
# ============================================================================

impact 0.5 # Mapped from CIS severity or default medium

# ============================================================================
# REFERENCES (External documentation only)
# ============================================================================

# Only include if external supplemental documentation exists
# DO NOT reference the benchmark itself (redundant)
ref 'NIST Security Guide', url: 'https://csrc.nist.gov/...'
ref 'Vendor Documentation', url: 'https://vendor.com/security'

# ============================================================================
# TAGS - Compliance Framework Mappings
# ============================================================================

# --- Basic Metadata ---
tag severity: 'medium' # low, medium, high, critical

# --- CIS Controls (v7 and v8) ---
# Multiple CIS Controls can map to one recommendation
# Array maintains alignment with cci and nist arrays
tag cis_controls: [
{
version: 7,
control: '14.9',
title: 'Enforce Detail Logging for Access or Changes to Sensitive Data',
implementation_groups: ['ig3'] # Only IGs where this applies
},
{
version: 8,
control: '3.14',
title: 'Log Sensitive Data Access',
implementation_groups: ['ig1', 'ig2', 'ig3'] # All IGs
}
]

# --- DoD/NIST Compliance Mappings ---
# ALIGNED ARRAYS: Position indicates mapping relationship
# cis_controls[0] cci[0] nist[0]
# cis_controls[1] cci[1] nist[1]

tag cci: [
'CCI-000123', # Primary CCI for CIS v7:14.9
'CCI-000126' # Primary CCI for CIS v8:3.14
]

tag nist: [
'AU-2 a', # NIST control for CCI-000123 (from v7:14.9)
'AU-2 c' # NIST control for CCI-000126 (from v8:3.14)
]

# --- MITRE ATT&CK Framework ---
tag mitre_technique_ids: ['T1565', 'T1565.001'] # Attack techniques
tag mitre_tactic_ids: ['TA0001'] # Attack tactics
tag mitre_mitigation_ids: ['M1022'] # Mitigations

# --- CIS Profile Applicability ---
# Which profile levels include this control
tag level_1: ['server', 'workstation'] # Both platforms at Level 1
# tag level_2: ['server'] # Only if in Level 2
# tag level_3: ['workstation'] # Only if benchmark has Level 3

# --- STIG Cross-References (Optional - only if in benchmark references) ---
# Enables cross-framework mapping via CCI as universal index
# tag stig_requirements: ['SV-251710', 'V-251710'] # STIGs covering same CCI

# ============================================================================
# TEST IMPLEMENTATION
# ============================================================================

describe package('aide') do
it { should be_installed }
end
end
```

---

## Style Rules

### 1. Control Naming

**Format:** `<benchmark-short>-cis-<control-ref>`

**Examples:**

- `almalinux-10-cis-6.1.1`
- `oci-foundations-cis-5.1.1`
- `ubuntu-22-cis-1.1.1.1`

**Rules:**

- Use lowercase with hyphens
- Include benchmark identifier for uniqueness
- Use CIS reference number from benchmark

### 2. Descriptions

**Required:**

- `desc` - Main description (always)
- `desc 'check'` - Audit procedure (always)
- `desc 'fix'` - Remediation (always)

**Optional (only if present in source):**

- `desc 'rationale'`
- `desc 'potential_impacts'`
- `desc 'mitigations'`
- `desc 'false_positives'`
- `desc 'false_negatives'`

**Formatting:**

- Use `%q()` for multi-line with complex quotes
- Use single quotes `'...'` for simple strings
- Use double quotes `"..."` for strings with single quotes

### 3. References

**Include:** External supplemental documentation only
**Exclude:** Self-references to the benchmark itself

**Format:**
```ruby
ref 'Document Title', url: 'https://...'
ref 'Document Title', uri: 'urn:...' # For non-HTTP URIs
```

### 4. Tags - Naming Conventions

**No "cis_" prefix spam:**

- `tag severity:` (not `tag cis_severity:`)
- `tag level_1:` (not `tag cis_level_1:`)
- `tag cis_controls:` (exception - it's a defined term)

**Consistency:**

- All list-type tags are ARRAYS (even single items)
- Use snake_case for tag names
- Use descriptive suffixes: `_ids`, `_groups`, etc.

### 5. Aligned Arrays - The Compliance Chain

**Critical:** Array positions indicate mapping relationships

```ruby
tag cis_controls: [control_v7, control_v8] # Source controls
tag cci: [cci_for_v7, cci_for_v8] # Mapped CCIs
tag nist: [nist_for_v7, nist_for_v8] # Mapped NIST
```

**Rules:**

- Position `[0]` in all three arrays represents one complete mapping chain
- Position `[1]` in all three arrays represents another complete mapping chain
- Do NOT reorder independently - alignment is semantic

**Rationale:** Both CIS Controls v7 and v8 are equally valid compliance frameworks. Neither should be privileged over the other.

### 6. CCI Mapping Strategy

**Default:** PRIMARY CCI only (key compliance mapping)
**Optional:** Supporting CCIs available via `--include-supporting-ccis` flag

**Reasoning:**

- Primary CCI provides the core compliance requirement
- Supporting CCIs add detail but can clutter
- Users can opt-in for comprehensive coverage

### 7. Implementation Groups

**Format:** Sparse array of applicable groups only

```ruby
implementation_groups: ['ig3'] # Only IG3
implementation_groups: ['ig1', 'ig2', 'ig3'] # All three
```

**Not:**
```ruby
# Do not use explicit true/false
{ig1: false, ig2: false, ig3: true}
```

### 8. Profile Levels

**Format:** Array of applicable platforms

```ruby
tag level_1: ['server', 'workstation'] # Both
tag level_2: ['server'] # Server only
tag level_3: ['workstation'] # Workstation only (if L3 exists)
```

**Values:** `'server'`, `'workstation'`, or both

---

## Data Flow

```
CIS Benchmark JSON cis-workbench-cli XCCDF SAF/ts-inspec-objects InSpec Profile

1. Source: CIS API JSON with cis_controls, mitre_mapping, nist_controls
2. Export: XCCDF with <metadata> containing all mappings
3. Parse: Extract metadata into InSpec tags
4. Output: OHDF-compliant InSpec profile
```

---

## Comparison: CIS vs DISA Profiles

| Element | CIS Profile | DISA STIG Profile |
|---------|-------------|-------------------|
| Control ID | `benchmark-cis-X.Y.Z` | `SV-######` or `V-######` |
| Reference | CIS ref number | STIG ID |
| gid/rid/stig_id | Not included | Included |
| cis_controls | Included | Not applicable |
| mitre_* | Included | Not typically included |
| level_1/2/3 | Included | Not applicable |
| cci/nist | Via CISCCI mapping | Direct from STIG |

---

## Examples

### Control with Multiple CIS Controls

```ruby
tag cis_controls: [
{version: 7, control: '6.2', implementation_groups: ['ig1', 'ig2', 'ig3']},
{version: 7, control: '6.3', implementation_groups: ['ig2', 'ig3']},
{version: 8, control: '8.2', implementation_groups: ['ig1', 'ig2', 'ig3']}
]
tag cci: ['CCI-000172', 'CCI-000173', 'CCI-000366']
tag nist: ['AU-12 c', 'AU-12 a', 'CM-6 b']
```

### Control in Multiple Levels

```ruby
tag level_1: ['server', 'workstation']
tag level_2: ['server', 'workstation']
# Both Level 1 and Level 2, both platforms
```

### Control with No MITRE Mapping

```ruby
# If no MITRE mapping exists, simply omit the tags
# tag mitre_technique_ids: [] # Do not include empty arrays
```

---

## Migration from Old Format

### Old (DISA-style for CIS - INCORRECT)
```ruby
control 'SV-6.1.1' do # Wrong ID format
tag gid: 'CIS-6_1_1' # DISA-specific, not needed
tag rid: 'xccdf_cis...' # DISA-specific
tag stig_id: '6.1.1' # Not a STIG
tag cci: ['CCI-1', 'CCI-2', 'CCI-3', 'CCI-4'] # Primary + Supporting
tag potential_impacts: '...' # Should be desc
end
```

### New (CIS-native - CORRECT)
```ruby
control 'almalinux-10-cis-6.1.1' do # CIS-specific ID
desc 'potential_impacts', '...' # desc not tag
tag cci: ['CCI-1', 'CCI-2'] # Primary only (2 CIS Controls)
tag cis_controls: [{...}, {...}] # CIS metadata
tag level_1: ['server'] # Profile applicability
end
```

---

## Optional Tags

### STIG Cross-References

If the benchmark includes STIG cross-references in its references field, include them:

```ruby
tag stig_requirements: ['SV-251710', 'V-251710'] # STIGs sharing same CCI
```

**Purpose:** Enables cross-framework mapping via CCI as the universal index. The CCI connects CIS controls to STIG requirements.

**Note:** Only include if present in source benchmark data. Not all CIS benchmarks have STIG mappings.

---

## Validation Checklist

- [ ] Control ID follows `<benchmark>-cis-<ref>` format
- [ ] No DISA-specific tags for control metadata (gid, rid, stig_id)
- [ ] Supplementary info uses `desc` not `tag`
- [ ] All list tags are arrays (even single items)
- [ ] cis_controls, cci, nist arrays are aligned by position
- [ ] Only primary CCIs included (not supporting)
- [ ] No self-references in `ref` statements
- [ ] Profile levels use clean format: `tag level_1: ['server']`
- [ ] No "cis_" prefix except on `cis_controls`
- [ ] Optional tags (stig_requirements) only if data exists

---

## See Also

- [OHDF Specification](https://saf.mitre.org/#/normalize)
- [InSpec Profile Documentation](https://docs.chef.io/inspec/profiles/)
- [CIS Controls Framework](https://www.cisecurity.org/controls)
- [NIST SP 800-53](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
