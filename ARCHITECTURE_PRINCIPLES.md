# Architecture Principles - CRITICAL REMINDERS

**Date:** December 16, 2025
**Purpose:** Prevent regression to hard-coded, organization-specific patterns

---

## Core Principle: Config-Driven Over Hard-Coded

**From design-philosophy.md:**
> "XCCDF field mappings defined in YAML configuration files, not Python code."

### ✅ CORRECT Pattern

**Adding a new framework (e.g., PCI-DSS):**
```yaml
# pci_dss_style.yaml - NO CODE CHANGES NEEDED!
field_mappings:
  pci_requirements:
    target_element: "ident"
    structure: "ident_from_list"
    source_field: "pci_controls"
    ident_spec:
      system_template: "https://www.pcisecuritystandards.org/pci_dss/v{item.version}"
      value_template: "{item.requirement}"
```

**Time:** 30 minutes (YAML only)

### ❌ WRONG Pattern (What We Keep Doing!)

**Hard-coding in Python:**
```python
def generate_pci_idents(self, recommendation):
    """Generate PCI-DSS ident elements."""  # WRONG!
    for control in recommendation.pci_controls:
        ident = IdentType(
            system=f"https://pci.org/v{control.version}",  # HARD-CODED!
            value=control.requirement
        )
```

**Time:** 3-5 hours (code + tests + docs)

**Why this is wrong:**
- Violates config-driven principle
- Creates organization-specific methods
- Not DRY
- Not extensible

---

## RED FLAGS - Stop Immediately If You See These

### 🚨 Red Flag #1: Organization Names in Method Names

```python
def build_cis_controls()      # ❌ CIS-specific
def generate_mitre_idents()   # ❌ MITRE-specific
def create_pci_metadata()     # ❌ PCI-specific
```

**Correct:**
```python
def generate_idents_from_config()    # ✅ Generic
def generate_metadata_from_config()  # ✅ Generic
def generate_profiles_from_rules()   # ✅ Generic
```

### 🚨 Red Flag #2: Hard-Coded URIs in Code

```python
system=f"http://cisecurity.org/controls/v{version}"  # ❌ Hard-coded
urn=f"urn:cisecurity.org:controls:{version}"        # ❌ Hard-coded
```

**Correct:**
```python
system = VariableSubstituter.substitute(
    config["system_template"],  # ✅ From config
    {"item": item}
)
```

### 🚨 Red Flag #3: Structure Logic in Python

```python
# Build framework elements
for version in versions:
    framework = Framework(urn=..., safeguard=...)  # ❌ Structure hard-coded
```

**Correct:**
```python
# Build from config spec
group_spec = metadata_spec.get("group_element")
element_name = group_spec.get("element")  # ✅ From config
attrs = group_spec.get("attributes")      # ✅ From config
```

### 🚨 Red Flag #4: If/Else for Organizations

```python
if framework == "cis":
    build_cis_structure()     # ❌ Organization-specific branching
elif framework == "pci":
    build_pci_structure()
```

**Correct:**
```python
# Generic - no branching!
metadata_elem = generate_metadata_from_config(rec, field_mapping)  # ✅ Works for all
```

### 🚨 Red Flag #5: "We'll Make It Generic Later"

```python
def generate_cis_controls():
    # TODO: Make this generic  # ❌ Never happens!
    return CisControls(...)
```

**Correct:**
- Make it generic NOW
- Or don't write it at all
- No "temporary" hard-coding

---

## The Approved Pattern Library

### Pattern 1: Simple Indices (ident_from_list)

**Use for:** CCIs, CIS Controls, MITRE, PCI-DSS, ISO 27001, etc.

**Config:**
```yaml
framework_controls:
  structure: "ident_from_list"
  source_field: "controls"
  ident_spec:
    system_template: "https://org.com/v{item.version}"
    value_template: "{item.id}"
```

**Code:** ZERO changes needed!

### Pattern 2: Nested XML (metadata_from_config)

**Use for:** CIS Controls metadata, PCI-DSS hierarchies, ISO 27001 families

**Config:**
```yaml
framework_metadata:
  structure: "metadata_from_config"
  requires_post_processing: true  # Complex nesting needs injection
  metadata_spec:
    root_element: "framework_controls"
    namespace: "https://org.com/schema"
    group_by: "item.version"
    group_element:
      element: "family"
      attributes:
        id: "{group_key}"
      item_element:
        element: "control"
        # ... all from config!
```

**Code:** ZERO changes needed!

### Pattern 3: Applicability (generate_profiles_from_rules)

**Use for:** CIS Levels, DISA MAC, PCI-DSS tiers

**Config:**
```yaml
profiles:
  generate_from_rules: true
  profile_mappings:
    - match: "Tier 1"
      id: "tier-1"
      title: "Tier 1"
```

**Code:** ZERO changes needed!

---

## How to Avoid Bad Habits

### Before Writing ANY Code, Ask:

1. **Is this structure defined in YAML?**
   - If NO: Add to YAML first
   - If YES: Read from config, don't hard-code

2. **Does this work for OTHER organizations?**
   - If NO: You're hard-coding - redesign it
   - If YES: Proceed

3. **Am I using templates or literals?**
   - Literals = hard-coding ❌
   - Templates from config = correct ✅

4. **Would adding PCI-DSS require code changes?**
   - If YES: You violated the principle ❌
   - If NO: Good ✅

### Code Review Checklist

Before committing ANY handler code:

- [ ] Method name is generic (no "cis", "mitre", "pci")
- [ ] No hard-coded URIs in the code
- [ ] All structure from YAML config
- [ ] Uses VariableSubstituter for templates
- [ ] Works with mock PCI-DSS data (test it!)
- [ ] Adding new framework = YAML only

---

## Enforcement

**Add to pre-commit hooks:**
```bash
# Check for organization names in new code
if grep -r "def.*_cis_\|def.*_mitre_\|def.*_pci_" src/; then
    echo "❌ Organization-specific method names detected!"
    exit 1
fi
```

**Add to CI:**
```python
def test_no_hard_coded_organizations():
    """Fail if organization names appear in structure logic."""
    with open("src/cis_bench/exporters/mapping_engine.py") as f:
        code = f.read()

    # Allow in comments, not in code
    for line in code.split("\n"):
        if line.strip().startswith("#"):
            continue
        if any(org in line for org in ["cisecurity.org", "attack.mitre.org", "pci.org"]):
            # Should only be in templates, not literals
            assert "template" in line or "VariableSubstituter" in line
```

---

## Success Criteria

**Before ANY PR merge:**

- [ ] Run: `grep -r "def.*build_.*_controls\|def.*generate_.*_idents" src/`
  - Result: ZERO matches (no org-specific methods)

- [ ] Test: Add mock PCI-DSS via YAML only
  - Result: Works without code changes

- [ ] Review: All structure handlers generic
  - `ident_from_list` ✅
  - `metadata_from_config` ✅
  - `generate_profiles_from_rules` ✅

---

## What We Learned (December 16, 2025)

**Mistake:** Kept reverting to hard-coded CIS Controls generation

**Root Cause:**
- Thinking "just for CIS" is acceptable
- Not testing generalization
- Taking shortcuts

**Fix:**
- Build from YAML config (lxml)
- Use `requires_post_processing` flag
- Generic injection method
- Test with multiple frameworks

**Never Again:**
- No "temporary" hard-coding
- No "we'll generalize later"
- No organization-specific methods

---

**This document is a CONTRACT - if we violate these principles, we're doing it wrong.**
