# End-to-End Workflows

**Real-world scenarios with complete commands and expected outcomes**

!!! info "Documentation Path"
**You are here:** User Guide > End-to-End Workflows

- **For command syntax:** See [Commands Reference](commands-reference.md)
- **For term definitions:** See [Glossary](../about/glossary.md)

---

## Overview

This guide shows complete workflows for common use cases. Each scenario includes:

- **Context** - Who you are and what you need
- **Prerequisites** - What you need before starting
- **Commands** - Complete CLI commands (copy-paste ready)
- **Expected Output** - What success looks like
- **Validation** - How to verify it worked
- **Troubleshooting** - Common issues

All examples use **real benchmark IDs** from CIS WorkBench.

---

## Scenario 1: Export AlmaLinux 10 for OpenSCAP Scanning

**Context:**
You're a security engineer setting up OpenSCAP compliance scanning for AlmaLinux 10 servers. You need the CIS Benchmark in XCCDF format.

**Prerequisites:**

- AlmaLinux 10 servers to scan
- OpenSCAP installed (`yum install openscap-scanner`)
- CIS WorkBench account

### Step 1: Setup (One-Time)

```bash
# Install cis-bench
pip install -e .

# Login to CIS WorkBench
cis-bench auth login --browser chrome

# Build catalog
cis-bench catalog refresh
```

**Expected:**
```
Logged in
Session saved to ~/.cis-bench/session.cookies

Catalog refresh complete!
Benchmarks: 1,343
Pages: 67
```

### Step 2: Find AlmaLinux 10 Benchmark

```bash
cis-bench search "almalinux 10" --latest
```

**Expected Output:**
```
╭─────────────┬──────────────────────────────────────┬─────────┬───────────╮
│ Benchmark │ Title │ Version │ Status │
│ ID │ │ │ │
├─────────────┼──────────────────────────────────────┼─────────┼───────────┤
│ 23598 │ CIS AlmaLinux OS 10 Benchmark │ v1.0.0 │ Published │
╰─────────────┴──────────────────────────────────────┴─────────┴───────────╯
```

**Note:** Benchmark ID is **23598**

### Step 3: Download and Export to XCCDF

```bash
# Download benchmark
cis-bench download 23598

# Export to CIS-style XCCDF
cis-bench export 23598 --format xccdf --style cis -o almalinux10-cis.xml
```

**Expected:**
```
Downloading benchmark 23598...
AlmaLinux OS 10 Benchmark v1.0.0
Downloading 322 recommendations ━━━━━━━━━━ 100%
Downloaded: almalinux10.json

Exporting to XCCDF (CIS style)...
Exported: almalinux10-cis.xml (1.8 MB, 322 rules)
```

### Step 4: Validate XCCDF

```bash
# Check file exists
ls -lh almalinux10-cis.xml

# Validate XML structure
xmllint --noout almalinux10-cis.xml && echo "Valid XML"

# Check rule count
xmllint --xpath "count(//Rule)" almalinux10-cis.xml
# Expected: 322
```

### Step 5: Run OpenSCAP Scan

```bash
# Run compliance scan
sudo oscap xccdf eval \
--profile "Level 1 - Server" \
--results scan-results.xml \
--report scan-report.html \
almalinux10-cis.xml

# View results
open scan-report.html
```

**Expected:**

- HTML report showing pass/fail for each rule
- XML results file for remediation tracking

### Troubleshooting

**Issue:** "Download failed - authentication required"
```bash
# Check auth status
cis-bench auth status

# Re-login if needed
cis-bench auth login --browser chrome
```

**Issue:** "OpenSCAP can't parse XCCDF"
```bash
# Verify XCCDF structure
xmllint --schema schemas/xccdf-1.2.xsd almalinux10-cis.xml

# Try DISA style instead (XCCDF 1.1.4, more compatible)
cis-bench export 23598 --format xccdf --style disa -o almalinux10-disa.xml
```

---

## Scenario 2: Create Compliance Tracking Spreadsheet

**Context:**
You're a compliance officer tracking Oracle Cloud Infrastructure security controls. You need a CSV spreadsheet for status tracking.

**Benchmark:** Oracle Cloud Infrastructure Foundations (ID: 24008)

### Complete Workflow

```bash
# 1. Setup (if not done)
cis-bench auth login --browser chrome
cis-bench catalog refresh

# 2. Search and download
cis-bench search "oracle cloud foundations"
# Shows: Benchmark ID 24008

cis-bench download 24008

# 3. Export to CSV
cis-bench export 24008 --format csv -o oci-compliance.csv

# 4. Open in spreadsheet
open oci-compliance.csv # macOS
# Or: libreoffice oci-compliance.csv # Linux
```

**CSV Output Includes:**
```csv
ref,title,assessment_status,profiles,audit,remediation,cis_controls,nist_controls
1.1,Ensure service admin is set,Automated,"Level 1",Check IAM policy...,Set IAM policy...,"[4.1, 5.4]","[AC-2, AC-3]"
1.2,Ensure password policy requires...,Automated,"Level 1",Check password settings...,Configure password...,"[5.2]","[IA-5]"
```

### Add Status Tracking Column

Edit CSV to add tracking:

1. Open in Excel/Numbers/Google Sheets
2. Add column: "Implementation Status"
3. Add column: "Assigned To"
4. Add column: "Target Date"
5. Add column: "Notes"

**Use for:**

- Track implementation progress
- Assign controls to team members
- Report to management
- Audit evidence

---

## Scenario 3: Batch Export All Cloud Benchmarks

**Context:**
You manage cloud security across AWS, Azure, GCP, and Oracle Cloud. You need XCCDF files for all cloud platforms.

### Complete Workflow

```bash
# 1. Find all cloud benchmarks
cis-bench search --platform-type cloud --latest --output-format json > cloud-benchmarks.json

# View what we found
jq -r '.[] | "\(.benchmark_id): \(.title)"' cloud-benchmarks.json

# 2. Download all cloud benchmarks
jq -r '.[].benchmark_id' cloud-benchmarks.json | \
head -10 | \
xargs -I {} cis-bench download {}

# 3. Create output directory
mkdir -p xccdf-cloud-benchmarks

# 4. Export all to XCCDF (DISA format for SCC)
cis-bench list --output-format json | \
jq -r 'select(.benchmark_id) | .benchmark_id' | \
while read id; do
cis-bench export "$id" \
--format xccdf \
--style disa \
-o "xccdf-cloud-benchmarks/benchmark-${id}-disa.xml"
echo "Exported: $id"
done

# 5. Verify
ls -lh xccdf-cloud-benchmarks/
```

**Expected Output:**
```
xccdf-cloud-benchmarks/
├── benchmark-12345-disa.xml (AWS Foundations)
├── benchmark-12346-disa.xml (Azure Foundations)
├── benchmark-12347-disa.xml (Google Cloud)
├── benchmark-24008-disa.xml (Oracle Cloud)
└── ...
```

### Use with SCAP Compliance Checker (SCC)

```bash
# Import all XCCDFs into SCC
for xccdf in xccdf-cloud-benchmarks/*.xml; do
echo "Importing: $xccdf"
# SCC import process (tool-specific)
done
```

---

## Scenario 4: Generate InSpec Profile from CIS Benchmark

**Context:**
You need to create an InSpec compliance profile from a CIS Benchmark for automated testing.

**Benchmark:** Ubuntu 22.04 LTS (ID: 22162)

### Complete Workflow

```bash
# 1. Download and export to XCCDF
cis-bench auth login --browser chrome
cis-bench download 22162
cis-bench export 22162 --format xccdf --style cis -o ubuntu2204-cis.xml

# 2. Use SAF CLI to convert XCCDF InSpec
npm install -g @mitre/saf

saf generate xccdf_benchmark2inspec_stub \
-X ubuntu2204-cis.xml \
-o ubuntu2204-inspec \
--idType cis

# 3. Verify InSpec profile
cd ubuntu2204-inspec
inspec check .

# 4. Run compliance scan
inspec exec . -t ssh://user@server --reporter cli json:results.json

# 5. View results
inspec_tools summary -j results.json
```

**Expected InSpec Profile:**
```
ubuntu2204-inspec/
├── inspec.yml # Profile metadata
├── controls/
│ ├── 1_1_1.rb # Recommendation 1.1.1
│ ├── 1_1_2.rb # Recommendation 1.1.2
│ └── ... # 200+ control files
└── libraries/
└── helper.rb # Shared code
```

**Each control file contains:**
```ruby
control '1_1_1' do
title 'Ensure mounting of cramfs filesystems is disabled'
desc 'The cramfs filesystem type is a compressed...'

impact 0.7 # From XCCDF severity

tag cis_controls: ['4.8']
tag nist: ['CM-7', 'CM-7(1)']

describe command('modprobe -n -v cramfs') do
its('stdout') { should match /install \/bin\/true/ }
end
end
```

---

## Scenario 5: Compare Benchmark Versions

**Context:**
CIS updated the AlmaLinux 8 benchmark from v3.0.0 to v4.0.0. You need to see what changed.

**Benchmarks:**

- AlmaLinux 8 v3.0.0 (ID: 15287)
- AlmaLinux 8 v4.0.0 (ID: 23598)

### Complete Workflow

```bash
# 1. Download both versions
cis-bench download 15287 23598

# 2. Export both to JSON (full data)
cis-bench export 15287 --format json -o alma8-v3.json
cis-bench export 23598 --format json -o alma8-v4.json

# 3. Compare recommendation counts
jq '.total_recommendations' alma8-v3.json
jq '.total_recommendations' alma8-v4.json

# 4. Extract recommendation refs
jq -r '.recommendations[].ref' alma8-v3.json | sort > v3-refs.txt
jq -r '.recommendations[].ref' alma8-v4.json | sort > v4-refs.txt

# 5. Find differences
comm -23 v3-refs.txt v4-refs.txt > removed.txt # In v3, not in v4
comm -13 v3-refs.txt v4-refs.txt > added.txt # In v4, not in v3
comm -12 v3-refs.txt v4-refs.txt > common.txt # In both

# 6. Summary
echo "Removed: $(wc -l < removed.txt) recommendations"
echo "Added: $(wc -l < added.txt) recommendations"
echo "Common: $(wc -l < common.txt) recommendations"

# 7. Detail on new recommendations
echo "New recommendations in v4.0.0:"
cat added.txt | while read ref; do
jq -r ".recommendations[] | select(.ref==\"$ref\") | .title" alma8-v4.json
done
```

**Expected Output:**
```
Removed: 5 recommendations
Added: 12 recommendations
Common: 310 recommendations

New recommendations in v4.0.0:
1.1.28 Ensure bootloader password is set
1.2.15 Ensure system-wide crypto policy is configured
...
```

---

## Scenario 6: Automated CI/CD Integration

**Context:**
You want to automatically download and export benchmarks in your CI/CD pipeline to keep compliance docs up-to-date.

### GitHub Actions Workflow

```yaml
# .github/workflows/update-compliance-docs.yml

name: Update Compliance Documentation

on:
schedule:

- cron: '0 0 * * 1' # Weekly on Monday
workflow_dispatch:

jobs:
update-benchmarks:
runs-on: ubuntu-latest

steps:

- uses: actions/checkout@v3

- name: Setup Python
uses: actions/setup-python@v4
with:
python-version: '3.11'

- name: Install cis-bench
run: |
pip install -e .

- name: Setup cookies
run: |
echo "${{ secrets.CIS_COOKIES }}" > cookies.txt

- name: Download benchmarks
run: |
cis-bench download 23598 --cookies cookies.txt # AlmaLinux 10
cis-bench download 22162 --cookies cookies.txt # Ubuntu 22.04
cis-bench download 24008 --cookies cookies.txt # Oracle Cloud

- name: Export to Markdown
run: |
mkdir -p docs/compliance
cis-bench export 23598 --format markdown -o docs/compliance/almalinux10.md
cis-bench export 22162 --format markdown -o docs/compliance/ubuntu2204.md
cis-bench export 24008 --format markdown -o docs/compliance/oracle-cloud.md

- name: Commit updates
run: |
git config user.name "GitHub Actions"
git config user.email "actions@github.com"
git add docs/compliance/
git commit -m "docs: update CIS benchmarks [skip ci]" || true
git push
```

**Result:** Compliance documentation automatically updated weekly.

---

## Scenario 7: Multi-Format Export for Different Stakeholders

**Context:**
You need to share Ubuntu 22.04 benchmark with different teams:

- **Security team** - Needs XCCDF for scanning
- **Management** - Needs CSV for tracking
- **Documentation team** - Needs Markdown for wiki

**Benchmark:** Ubuntu 22.04 LTS Server (ID: 22162)

### Complete Workflow

```bash
# 1. Download once
cis-bench download 22162

# 2. Export to all formats
mkdir -p exports/ubuntu2204

# XCCDF for OpenSCAP/SCC
cis-bench export 22162 --format xccdf --style disa \
-o exports/ubuntu2204/ubuntu-2204-disa.xml

# CSV for tracking
cis-bench export 22162 --format csv \
-o exports/ubuntu2204/ubuntu-2204-controls.csv

# Markdown for wiki
cis-bench export 22162 --format markdown \
-o exports/ubuntu2204/ubuntu-2204-guide.md

# YAML for automation (Ansible/Chef)
cis-bench export 22162 --format yaml \
-o exports/ubuntu2204/ubuntu-2204-data.yaml

# JSON for scripting
cis-bench export 22162 --format json \
-o exports/ubuntu2204/ubuntu-2204-structured.json

# 3. Verify all exports
ls -lh exports/ubuntu2204/
```

**Expected:**
```
total 12M
-rw-r--r-- 1 user group 1.8M ubuntu-2204-disa.xml (SCAP scanning)
-rw-r--r-- 1 user group 450K ubuntu-2204-controls.csv (Excel tracking)
-rw-r--r-- 1 user group 2.1M ubuntu-2204-guide.md (Documentation)
-rw-r--r-- 1 user group 1.2M ubuntu-2204-data.yaml (Automation)
-rw-r--r-- 1 user group 980K ubuntu-2204-structured.json (APIs/Scripts)
```

### Distribution

```bash
# Share with teams
cp exports/ubuntu2204/ubuntu-2204-disa.xml /shared/security/
cp exports/ubuntu2204/ubuntu-2204-controls.csv /shared/management/
cp exports/ubuntu2204/ubuntu-2204-guide.md /shared/wiki/
```

---

## Scenario 8: Validate XCCDF Before Importing to SCC

**Context:**
You're importing CIS benchmarks into DISA SCC (SCAP Compliance Checker). SCC is picky about XCCDF format and will reject invalid files.

**Benchmark:** RHEL 9 (ID: 18208)

### Complete Workflow with Validation

```bash
# 1. Download and export
cis-bench download 18208
cis-bench export 18208 --format xccdf --style disa -o rhel9-disa.xml

# 2. Validate XML syntax
xmllint --noout rhel9-disa.xml
if [ $? -eq 0 ]; then
echo " Valid XML syntax"
else
echo " XML syntax error"
exit 1
fi

# 3. Validate against XCCDF schema
xmllint --schema schemas/xccdf-1.1.4.xsd --noout rhel9-disa.xml
if [ $? -eq 0 ]; then
echo " Valid XCCDF 1.1.4 structure"
else
echo " XCCDF schema validation failed"
exit 1
fi

# 4. Check DISA conventions
python3 << EOF
from cis_bench.validators.disa_conventions import validate_disa_conventions
issues = validate_disa_conventions('rhel9-disa.xml')
if not issues:
print(" DISA conventions validated")
else:
print(f"WARNING: {len(issues)} convention issues found:")
for issue in issues:
print(f" - {issue}")
EOF

# 5. Verify CCI count (should be reasonable)
cci_count=$(xmllint --xpath "count(//ident)" rhel9-disa.xml)
echo "Total CCIs: $cci_count"

# Sanity check (should be ~500-1500 for typical benchmark)
if [ "$cci_count" -gt 100 ] && [ "$cci_count" -lt 5000 ]; then
echo " CCI count reasonable"
else
echo "WARNING: Unusual CCI count (expected 500-1500)"
fi

# 6. Check for required STIG elements
required_elements="VulnDiscussion FalsePositives"
for elem in $required_elements; do
count=$(xmllint --xpath "count(//*[local-name()='$elem'])" rhel9-disa.xml)
echo "$elem elements: $count"
done

# 7. If all validations pass, import to SCC
echo " All validations passed - ready for SCC import"
# Import to SCC (tool-specific steps)
```

---

## Scenario 9: Search and Filter for Specific Platforms

**Context:**
You support multiple platforms and need to find all relevant CIS benchmarks.

### Find All Database Benchmarks

```bash
# Search by category
cis-bench search --platform-type database --output-format table

# Export to JSON for processing
cis-bench search --platform-type database --output-format json > databases.json

# Extract specific platforms
jq -r '.[] | select(.platform == "oracle-database") | "\(.benchmark_id): \(.title) \(.version)"' databases.json
jq -r '.[] | select(.platform == "mysql") | "\(.benchmark_id): \(.title) \(.version)"' databases.json
jq -r '.[] | select(.platform == "postgresql") | "\(.benchmark_id): \(.title) \(.version)"' databases.json
```

### Find All Container/Kubernetes Benchmarks

```bash
cis-bench search --platform-type container
```

**Shows:**
```
╭─────────────┬──────────────────────────────────────┬─────────╮
│ Benchmark │ Title │ Version │
├─────────────┼──────────────────────────────────────┼─────────┤
│ 6467 │ CIS Kubernetes Benchmark │ v1.9.0 │
│ 7533 │ CIS Docker Benchmark │ v1.7.0 │
│ 8034 │ CIS Amazon EKS Benchmark │ v1.5.0 │
│ 12696 │ CIS Azure AKS Benchmark │ v1.6.0 │
╰─────────────┴──────────────────────────────────────┴─────────╯
```

### Download Specific Platform

```bash
# Download all Kubernetes-related
cis-bench search "kubernetes" --output-format json | \
jq -r '.[].benchmark_id' | \
xargs -I {} cis-bench download {}
```

---

## Scenario 10: Quick Lookup and Get

**Context:**
You need a specific benchmark fast and don't remember the ID.

### Using the Unified `get` Command

```bash
# Search and export in one command
cis-bench get "ubuntu 22" --format xccdf --style cis

# What happens:
# 1. Searches catalog for "ubuntu 22"
# 2. If multiple matches, shows interactive selection
# 3. Downloads benchmark (or uses cache)
# 4. Exports to XCCDF CIS style
# 5. Outputs file path
```

**Interactive Selection:**
```
Found 3 matching benchmarks:
? Select benchmark:
❯ CIS Ubuntu Linux 22.04 LTS Benchmark v2.0.0 (22162)
CIS Ubuntu Linux 22.04 LTS Server Benchmark v1.0.0 (18208)
CIS Ubuntu Linux 20.04 LTS Benchmark v2.0.1 (23595)

Downloading: 22162
Downloaded (from cache)

Exporting to XCCDF (CIS style)...
Exported: ubuntu-22-04-cis.xml
```

**Non-Interactive Mode:**
```bash
# Skip interactive selection, show table instead
cis-bench get "ubuntu 22" --format xccdf --style cis --non-interactive
```

---

## Scenario 11: Scripting with JSON Output

**Context:**
You're building automation and need machine-readable output.

### Search to JSON Pipeline

```bash
# Find all latest OS benchmarks
cis-bench search --platform-type os --latest --output-format json | \
jq -r '.[] | {
id: .benchmark_id,
title: .title,
version: .version,
platform: .platform
}'

# Download IDs from JSON
cis-bench search --platform-type os --latest --output-format json | \
jq -r '.[].benchmark_id' | \
xargs -I {} cis-bench download {}
```

### Check Auth Status Programmatically

```bash
# Get auth status as JSON
auth_status=$(cis-bench auth status --output-format json)

# Parse with jq
is_logged_in=$(echo "$auth_status" | jq -r '.logged_in')

if [ "$is_logged_in" = "true" ]; then
echo "Already logged in"
else
echo "Need to login"
cis-bench auth login --browser chrome
fi
```

### List Downloaded Benchmarks as JSON

```bash
# Get all downloaded benchmarks
cis-bench list --output-format json > inventory.json

# Extract specific fields
jq -r '.[] | "\(.benchmark_id),\(.title),\(.version)"' inventory.json > inventory.csv

# Count by platform
jq -r '.[] | .title' inventory.json | \
grep -o "AlmaLinux\|Ubuntu\|RHEL" | \
sort | uniq -c
```

---

## Scenario 12: Update Catalog and Re-Export

**Context:**
You downloaded benchmarks 6 months ago. CIS has released updates. You need to check for and download new versions.

### Complete Workflow

```bash
# 1. Check what you have
cis-bench list --output-format table

# 2. Update catalog (quick - page 1 only)
cis-bench catalog update

# 3. Check for updates to your downloaded benchmarks
cis-bench catalog check-updates

# Expected output:
# Checking 12 downloaded benchmarks...
# Updates available:
# 23598: AlmaLinux 10 v1.0.0 v1.1.0
# 22162: Ubuntu 22.04 v2.0.0 v2.0.1
# No updates: 10 benchmarks

# 4. Download updates
cis-bench download 23598 --force # Force re-download
cis-bench download 22162 --force

# 5. Re-export to XCCDF
cis-bench export 23598 --format xccdf --style disa -o almalinux10-v1.1.xml
cis-bench export 22162 --format xccdf --style disa -o ubuntu2204-v2.0.1.xml

# 6. Update your OpenSCAP/SCC configuration with new files
```

---

## Scenario 13: Corporate Environment with SSL Issues

**Context:**
You're behind a corporate proxy with custom SSL certificates. Standard commands fail with SSL errors.

### Setup for Corporate Environment

```bash
# Option 1: Disable SSL verification (not recommended for production)
export CIS_BENCH_VERIFY_SSL=false
cis-bench auth login --browser chrome
cis-bench catalog refresh

# Option 2: Use corporate certificate bundle
export REQUESTS_CA_BUNDLE=/etc/ssl/corporate-ca-bundle.crt
cis-bench auth login --browser chrome
cis-bench catalog refresh

# Option 3: Per-command flag
cis-bench auth login --browser chrome --no-verify-ssl
cis-bench download 23598 # Uses saved session settings
```

**Verify SSL Settings:**
```bash
cis-bench auth status --output-format json | jq '.ssl_verify'
# false (if disabled)
```

---

## Scenario 14: Offline Mode (Work from Cache)

**Context:**
You're on a plane without internet. You need to work with benchmarks you've already downloaded.

### Prepare Before Going Offline

```bash
# 1. Download everything you'll need
cis-bench download 23598 22162 24008 18208

# 2. Verify cache
cis-bench list
```

### Work Offline

```bash
# All these work offline (use cache):
cis-bench list
cis-bench info 23598
cis-bench export 23598 --format xccdf --style cis
cis-bench export 22162 --format csv
cis-bench search "ubuntu" # Works if catalog cached

# These REQUIRE internet (will fail offline):
cis-bench download 12345 # New download
cis-bench catalog refresh # Network required
```

---

## Common Command Combinations

### Quick Reference Table

| Task | Command |
|------|---------|
| Setup | `cis-bench auth login --browser chrome && cis-bench catalog refresh` |
| Search | `cis-bench search "platform name"` |
| Get XCCDF | `cis-bench get "query" --format xccdf --style cis` |
| Download by ID | `cis-bench download XXXXX` |
| Export cached | `cis-bench export XXXXX --format xccdf --style disa` |
| List downloaded | `cis-bench list` |
| Check updates | `cis-bench catalog check-updates` |
| Batch export | `cis-bench list --output-format json \| jq -r '.[].benchmark_id' \| xargs -I {} cis-bench export {} --format xccdf` |

---

## Benchmark ID Reference

**Common Benchmarks (as of Dec 2025):**

| ID | Platform | Version |
|----|----------|---------|
| 23598 | AlmaLinux 10 | v1.0.0 |
| 15287 | AlmaLinux 8 | v3.0.0 |
| 22162 | Ubuntu 22.04 LTS Server | v2.0.0 |
| 23595 | Ubuntu 20.04 LTS | v2.0.1 |
| 18208 | RHEL 9 | v2.0.0 |
| 24008 | Oracle Cloud Infrastructure | v3.0.0 |
| 6467 | Kubernetes | v1.9.0 |
| 7533 | Docker | v1.7.0 |

**Find more:**
```bash
cis-bench search --platform-type <category>
cis-bench catalog platforms
```
