# How to Add a New XCCDF Style

**Adding a new XCCDF style is 100% configuration, 0% code!**

Create YAML config → Test → Done. (No CLI changes needed with generic handlers)

!!! success "December 2025 Update"
With generic structure handlers, adding frameworks like PCI-DSS, ISO 27001, or HIPAA requires **ONLY YAML configuration** - zero Python code changes!

See working example: [Adding PCI-DSS](adding-pci-dss.md)

!!! info "Documentation Path"
    **You are here:** Developer Guide > How To Add XCCDF Style

    - **For MappingEngine:** See [MappingEngine User Guide](mapping-engine-guide.md)
    - **For YAML syntax:** See [YAML Config Reference](../technical-reference/yaml-config-reference.md)
    - **For examples:** See [Workflows](../user-guide/workflows.md)

---

## Overview

The CIS WorkBench CLI uses a **configuration-driven architecture** for XCCDF exports. Adding a new style means creating a YAML file that tells the MappingEngine how to transform your Pydantic data models into XCCDF XML.

### What You Get For Free

When you add a new XCCDF style:

- **JSON export:** Works automatically (raw Pydantic data)
- **YAML export:** Works automatically (raw Pydantic data)
- **CSV export:** Works automatically (raw Pydantic data)
- **Markdown export:** Works automatically (raw Pydantic data)
- **XCCDF export:** Uses your YAML configuration

**Only XCCDF uses style configs** - other formats export the Pydantic models directly.

### What's Automated vs Manual

**The system handles automatically:**

- Loading and parsing your YAML config
- Applying field mappings you define
- Executing transformations (strip_html, html_to_markdown, etc.)
- Generating XCCDF models using xsdata
- XML serialization with proper namespaces

**You provide:**

- YAML configuration file with field mappings (main work)
- One line of CLI code to register the style option
- Tests for the new style
- Documentation

---

## Step 1: Create YAML Configuration

Create `src/cis_bench/exporters/configs/pci_dss_style.yaml`:

```yaml
# PCI-DSS XCCDF Export Configuration
metadata:
  style_name: "pci-dss"
  description: "PCI-DSS compliant XCCDF export"
  xccdf_version: "1.2"  # Use "1.1.4" for DISA/DoD compatibility
  target_tools:

    - "PCI Compliance Tools"
    - "OpenSCAP"

# Namespaces (required for XCCDF)
namespaces:
  default: "http://checklists.nist.gov/xccdf/1.2"
  xccdf: "http://checklists.nist.gov/xccdf/1.2"
  dc: "http://purl.org/dc/elements/1.1/"
  pci: "http://pci-dss.org/xccdf/1.0"  # Your custom namespace

# Benchmark-level configuration
benchmark:
  id_template: "xccdf_pci_dss_{platform}"
  title:
    source: "title"
    transform: "none"
  version:
    source: "version"

# Default values for Rule elements
rule_defaults:
  severity: "high"  # PCI-DSS is strict by default
  weight: "10.0"
  selected: "true"

# Field mappings: YAML tells the engine what to do
field_mappings:
  # Basic text fields
  title:
    target_element: "title"
    source_field: "title"
    transform: "strip_html"

  description:
    target_element: "description"
    source_field: "description"
    transform: "html_to_markdown"

  # Use generic metadata handler for CIS Controls
  cis_controls_metadata:
    structure: "metadata_from_config"
    requires_post_processing: true
    source_field: "cis_controls"
    metadata_spec:
      root_element: "cis_controls"
      namespace: "http://cisecurity.org/controls"
      group_by: "item.version"
      # ... (see cis_style.yaml for full spec)
```

**The configuration is the implementation.** The MappingEngine reads this YAML and executes the transformations automatically.

---

## Step 2: Add CLI Option (One Line of Code)

Edit `src/cis_bench/cli/commands/export.py`:

```python
@click.option(
    "--style",
    type=click.Choice(["disa", "cis", "pci-dss"]),  # Add your style here
    default="disa",
    help="XCCDF export style (only for --format xccdf)"
)
```

**That's the only Python code change needed.**

---

## Step 3: Test the New Style

### Manual Testing

```bash
# Export using your new style
cis-bench export benchmark.json --format xccdf --style pci-dss

# Check the output exists
ls -lh output.xml
```

---

## Step 4: XSD Validation (CRITICAL)

**Always validate your XCCDF output against the official NIST schema.**

### For XCCDF 1.2 (Modern Standard)

```bash
# Validate against XCCDF 1.2 schema
xmllint --schema schemas/xccdf_1.2.xsd --noout output.xml
```

**Success looks like:**
```
output.xml validates
```

**Failure looks like:**
```
output.xml:42: element description: Schemas validity error : Element
'{http://checklists.nist.gov/xccdf/1.2}description': This element is
not expected. Expected is ( {http://checklists.nist.gov/xccdf/1.2}title ).
```

### For XCCDF 1.1.4 (DISA/DoD Compatibility)

```bash
# Validate against XCCDF 1.1.4 schema
xmllint --schema schemas/xccdf-1.1.4.xsd --noout output.xml
```

### When to Use Which Schema

- **XCCDF 1.2:** Modern standard, supports more features
  - Use for: CIS native, OpenSCAP, modern tools
  - Config: `xccdf_version: "1.2"`

- **XCCDF 1.1.4:** Legacy standard, DISA STIG requirement
  - Use for: DoD/DISA compliance, STIG compatibility
  - Config: `xccdf_version: "1.1.4"`

### Add XSD Validation to Tests

```python
import subprocess

def test_pci_dss_xsd_validation(sample_benchmark, tmp_path):
    """Verify output validates against XCCDF 1.2 schema."""
    output_file = tmp_path / "pci_dss_validation.xml"
    exporter = ExporterFactory.create("xccdf", style="pci-dss")
    exporter.export(sample_benchmark, output_file)

    # Run xmllint validation
    result = subprocess.run(
        ["xmllint", "--schema", "schemas/xccdf_1.2.xsd", "--noout", str(output_file)],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"XSD validation failed:\n{result.stderr}"
```

**XSD validation is mandatory before releasing a new style.**

---

## Best Practices

### 1. Copy an Existing Style First

**Do not start from scratch.** Copy a similar style:

```bash
# For modern XCCDF 1.2
cp src/cis_bench/exporters/configs/cis_style.yaml \
   src/cis_bench/exporters/configs/pci_dss_style.yaml

# For DISA/DoD XCCDF 1.1.4
cp src/cis_bench/exporters/configs/disa_style.yaml \
   src/cis_bench/exporters/configs/banking_style.yaml
```

Then modify incrementally.

### 2. Test Incrementally

Add fields one at a time:

```bash
# Add title field, test
cis-bench export benchmark.json --format xccdf --style pci-dss
xmllint --schema schemas/xccdf_1.2.xsd --noout output.xml

# Add description, test again
# Add metadata, test again
```

### 3. Use Generic Handlers

The system provides 3 generic handlers that work for ANY framework:

```yaml
# For simple indices (CCIs, controls, techniques)
framework_controls:
  structure: "ident_from_list"
  source_field: "controls"
  ident_spec:
    system_template: "https://framework.org/v{item.version}"
    value_template: "{item.id}"

# For nested hierarchies (CIS Controls, PCI-DSS requirements)
framework_metadata:
  structure: "metadata_from_config"
  requires_post_processing: true
  source_field: "controls"
  metadata_spec:
    # Define structure in YAML
```

### 4. Always Validate Output

Before committing:

```bash
# XSD validation (must pass)
xmllint --schema schemas/xccdf_1.2.xsd --noout output.xml

# Visual inspection
xmllint --format output.xml | less

# Test with target tool (if available)
oscap xccdf validate output.xml
```

---

## Troubleshooting

### XSD Validation Errors

**Common issues:**

- Wrong namespace URIs
- Elements in wrong order (XCCDF is order-sensitive)
- Missing required attributes
- XCCDF version mismatch (1.2 vs 1.1.4)

**Fix:**

1. Check namespace declarations match schema
2. Verify element order in your config
3. Use correct schema for your XCCDF version
4. Compare with working style (disa_style.yaml or cis_style.yaml)

### Missing Elements in Output

**Cause:** Field mapping not found or source field empty.

**Debug:**

```bash
cis-bench export benchmark.json --format xccdf --style pci-dss --verbose
```

**Check:**

- Source field exists in Pydantic model
- Field mapping defined in YAML config
- Transform function exists
- Source field name spelled correctly (case-sensitive)

---

## Summary Checklist

Before considering your new style complete:

- [ ] YAML config created in `src/cis_bench/exporters/configs/`
- [ ] Config follows naming convention: `{style}_style.yaml`
- [ ] CLI option added to `export.py`
- [ ] Manual test: `cis-bench export --format xccdf --style {name}`
- [ ] **XSD validation passes:** `xmllint --schema schemas/xccdf_*.xsd --noout output.xml`
- [ ] Unit tests written and passing
- [ ] XSD validation in automated tests
- [ ] Documentation added to `XCCDF_STYLES.md`
- [ ] Config file has explanatory comments
- [ ] Reused existing structures where possible

---

## See Also

- [YAML Config Reference](../technical-reference/yaml-config-reference.md) - Complete YAML syntax
- [Mapping Engine Design](../technical-reference/mapping-engine-design.md) - How config-driven system works
- [XCCDF Styles Comparison](../technical-reference/xccdf-styles.md) - All available styles
- [MappingEngine User Guide](mapping-engine-guide.md) - Using the mapping engine

---

**Remember:** Configuration is code. The YAML file **is** your implementation. The system handles the rest automatically.
