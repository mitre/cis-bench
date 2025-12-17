# How to Add PCI-DSS Support (No Code Changes!)

This guide shows how to add PCI-DSS v4.0 support using **only YAML configuration**.

**Time required:** 30 minutes
**Code changes needed:** ZERO

---

## Step 1: Create Configuration File

Create `src/cis_bench/exporters/configs/pci_dss_style.yaml`:

```yaml
# PCI-DSS v4.0 XCCDF Export Configuration
extends: base_style.yaml

metadata:
  style_name: "pci_dss"
  description: "PCI-DSS v4.0 compliance export"
  xccdf_version: "1.2"

benchmark:
  id_template: "xccdf_org.pcisecuritystandards_benchmark_PCI_DSS_v4.0"

  profiles:
    generate_from_rules: true
    profile_mappings:

      - match: "SAQ A"
        id: "saq-a"
        title: "Self-Assessment Questionnaire A"

field_mappings:
  pci_requirements:
    target_element: "ident"
    structure: "ident_from_list"
    source_field: "your_pci_field"
    ident_spec:
      system_template: "https://www.pcisecuritystandards.org/pci_dss/v4.0"
      value_template: "Requirement-{item.requirement}"
```

## Step 2: Use It

```bash
cis-bench export benchmark.json --format xccdf --style pci_dss -o pci.xml
```

**That's it!** No code changes needed.

---

See `tests/fixtures/configs/mock_pci_dss.yaml` for working example.
