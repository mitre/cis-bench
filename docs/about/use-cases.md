# CIS Benchmark CLI - Use Cases and Workflows

## Core Workflows (v1.0)

### 1. Security Auditor - Compliance Assessment
**Goal**: Get benchmark in XCCDF for scanning tools

```bash
cis-bench get "AlmaLinux 8" --format xccdf --browser chrome
# Use with OpenSCAP, SCC, Nessus
```

### 2. Documentation Team - Create Runbooks
**Goal**: Generate readable documentation

```bash
cis-bench get 23598 --format markdown --browser chrome
# Publish as internal wiki/confluence
```

### 3. Compliance Manager - Spreadsheet Analysis
**Goal**: Analyze controls in Excel

```bash
cis-bench get "Windows Server 2022" --format csv --browser chrome
# Import to Excel, filter by CIS Controls v8 IG2
```

---

## Advanced Workflows (v1.1+)

### 4. Benchmark Comparison - Track Changes
**Goal**: See what changed between versions

```bash
cis-bench diff almalinux_v3.json almalinux_v4.json

Output:
Added: 45 new recommendations
Removed: 12 deprecated recommendations
Modified: 23 updated recommendations

CIS Controls changes:

- 15 recommendations now map to CIS v8
- 8 MITRE techniques added
```

### 5. Framework Mapping - Compliance Crosswalk
**Goal**: See all NIST 800-53 controls covered

```bash
cis-bench analyze benchmark.json --show-mappings

NIST 800-53 Coverage:
AU-2: 15 recommendations
SI-3: 8 recommendations
CM-7: 23 recommendations

MITRE ATT&CK Coverage:
T1068: 5 recommendations
T1565: 12 recommendations
```

### 6. Baseline Creation - Tailored Profiles
**Goal**: Create custom baseline (only Level 1, only specific sections)

```bash
cis-bench tailor benchmark.json \
--profiles "Level 1 - Server" \
--sections "1,2,3" \
--exclude "1.1.5,2.3.4" \
--output custom_baseline.json

# Then export to XCCDF
cis-bench export custom_baseline.json --format xccdf
```

### 7. Bulk Download - Entire Product Family
**Goal**: Get all versions of a platform

```bash
cis-bench bulk-download --platform almalinux --all-versions

Downloads:
AlmaLinux OS 8 v1.0.0
AlmaLinux OS 8 v2.0.0
AlmaLinux OS 8 v3.0.0
AlmaLinux OS 8 v4.0.0
AlmaLinux OS 9 v1.0.0
```

### 8. Update Checker - Stay Current
**Goal**: Know when benchmarks are updated

```bash
cis-bench check-updates

Updates available:
Amazon EKS: v1.7.0 v1.8.0 available
AlmaLinux OS 8: v4.0.0 (current)

cis-bench update-all --browser chrome
```

### 9. InSpec/Ansible Generation - Create Compliance Code
**Goal**: Generate scanning profiles

```bash
# Future integration
cis-bench export benchmark.json --format inspec --output controls/

# Generates InSpec controls
# controls/
# 6.1.1.rb
# 6.1.2.rb
# ...

# Or Ansible playbook
cis-bench export benchmark.json --format ansible --output playbook.yml
```

### 10. Compliance Dashboard - Generate Reports
**Goal**: HTML dashboard with coverage

```bash
cis-bench report benchmark.json --format html

Generates:

- Coverage by CIS Controls v8 Implementation Groups
- MITRE ATT&CK heatmap
- NIST 800-53 control mapping
- Automated vs Manual assessment breakdown
```

### 11. CI/CD Integration - Automated Benchmark Updates
**Goal**: Keep benchmarks current in pipeline

```yaml
# .github/workflows/update-benchmarks.yml

- name: Update CIS Benchmarks
run: |
cis-bench check-updates
cis-bench update-all --format xccdf
cis-bench export *.json --format inspec
git commit -m "Updated benchmarks"
```

### 12. Offline Mode - Work Without Network
**Goal**: Use in air-gapped environments

```bash
# Export catalog + benchmarks to bundle
cis-bench export-bundle --platform almalinux --output cis_bundle.tar.gz

# On air-gapped system
cis-bench import-bundle cis_bundle.tar.gz
cis-bench list-available --offline # Works from bundle
cis-bench export benchmark.json --format xccdf # No network needed
```

### 13. Compliance Tracking - Gap Analysis
**Goal**: Track what's implemented

```bash
# Import scan results
cis-bench import-scan-results openscap_results.xml

# Show gaps
cis-bench gaps benchmark.json --scan-results openscap_results.xml

Compliance Status:
Passed: 245 / 322 (76%)
Failed: 45 / 322 (14%)
WARNING: Manual: 32 / 322 (10%)

Top gaps by CIS Control:

- CIS v8 3.14 (IG3): 12 failures
- CIS v8 4.8 (IG2): 8 failures
```

### 14. Benchmark Merge - Multi-Platform
**Goal**: Combine benchmarks for hybrid environments

```bash
cis-bench merge \
almalinux8.json \
docker.json \
kubernetes.json \
--output hybrid_baseline.json \
--deduplicate \
--resolve-conflicts interactive

# Creates unified benchmark for Docker on AlmaLinux with K8s
```

### 15. Custom Export Templates
**Goal**: Organization-specific formats

```bash
# Custom Jinja2 template
cis-bench export benchmark.json \
--template templates/corporate_policy.j2 \
--format pdf

# Generates PDF with corporate branding
```

---

## Feature Priority Matrix

### High Value + Easy (v1.1)

- Catalog scraper with caching
- list-available with filtering
- requests-cache integration
- --no-cache flag

### High Value + Medium (v1.2)

- Interactive multi-select
- `get` command with fuzzy matching
- Benchmark diff/comparison
- Framework mapping analysis

### High Value + Hard (v1.3+)

- InSpec/Ansible export
- Scan results integration
- Compliance gap analysis
- HTML dashboards

### Future Research

- Benchmark tailoring/customization
- Offline bundles
- CI/CD integration examples
- Benchmark merging for hybrid environments

---

## Technical Considerations

### Caching Strategy
```python
# Three-tier cache:
1. Catalog cache (~1 MB, 24 hour TTL)
2. HTTP cache (SQLite, 7 day TTL)
3. Downloaded benchmarks (permanent, user manages)

Cache locations:
~/.cis-bench/cache/catalog.json
~/.cis-bench/cache/http_cache.sqlite
~/.cis-bench/cache/benchmark_metadata.json
```

### Platform Detection
```python
# Extract platform from titles:
"CIS Amazon Elastic Kubernetes Service" platform: "aws", product: "eks"
"CIS AlmaLinux OS 8 Benchmark" platform: "almalinux", version: "8"
"CIS Microsoft Windows Server 2022" platform: "windows", product: "server-2022"

# Use regex patterns + fuzzy matching
```

### Search/Filter Performance
```python
# Build searchable index on catalog load
{
"platforms": {"aws": [id1, id2], "alma": [id3]},
"versions": {"8": [id3], "9": [id4]},
"keywords": {"kubernetes": [id1, id2]}
}

# O(1) lookups instead of linear search
```

---

## User Stories

### Story 1: New Security Engineer
"I'm new to CIS benchmarks. I want to see what's available for our AWS environment and download the latest EKS benchmark."

```bash
cis-bench list-available --platform aws
cis-bench get "EKS" --format xccdf --browser chrome
```

### Story 2: Compliance Analyst
"I need to create a compliance matrix showing which NIST controls are covered by our AlmaLinux baseline."

```bash
cis-bench get "AlmaLinux 8" --browser chrome
cis-bench analyze almalinux8.json --show-nist-mapping --format xlsx
```

### Story 3: DevOps Engineer
"I want to generate InSpec profiles from CIS benchmarks for automated testing."

```bash
cis-bench get 23598 --browser chrome
cis-bench export almalinux8.json --format inspec --output ./controls/
kitchen test # Uses generated InSpec controls
```

### Story 4: Security Manager
"I need to track which benchmarks have been updated and download the latest versions quarterly."

```bash
cis-bench check-updates
cis-bench update-all --format xccdf --format csv
# Email: "3 benchmarks updated - reports attached"
```

### Story 5: Consultant
"I work with multiple clients. I need offline bundles of benchmarks to work in air-gapped environments."

```bash
# Online system
cis-bench export-bundle --platform all --output cis_bundle_2025_q4.tar.gz

# Air-gapped system
cis-bench import-bundle cis_bundle_2025_q4.tar.gz
cis-bench list-available --offline
cis-bench get 23598 --offline --format xccdf
```

---
