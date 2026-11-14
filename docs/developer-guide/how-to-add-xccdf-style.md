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
- Executing the transforms a mapping names (`none` for text, `strip_version_prefix`, filters)
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

# Benchmark-level configuration
benchmark:
  id_template: "xccdf_org.pcisecuritystandards_benchmark_{version}_{title_slug}"
  # The namespaces this style's documents use (prefix -> URI). The serializer declares all
  # of them on the root; "default" is the default namespace. List each URI once: a second
  # prefix for the XCCDF namespace would replace the default namespace with that prefix.
  # A style that extends another inherits its parent's and cannot drop one.
  namespaces:
    default: "http://checklists.nist.gov/xccdf/1.2"
    dc: "http://purl.org/dc/elements/1.1/"
    pci: "http://pci-dss.org/xccdf/1.0"  # Your custom namespace
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
    transform: "none"

  description:
    target_element: "description"
    source_field: "description"
    transform: "none"

  # Use generic metadata handler for CIS Controls
  cis_controls_metadata:
    target_element: "metadata"
    structure: "metadata_from_config"
    source_field: "cis_controls"
    metadata_spec:
      root_element: "cis_controls"
      namespace_prefix: "controls"  # declared in benchmark.namespaces
      group_by: "item.version"
      # ... (see configs/styles/cis.yaml for the full spec)
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

### Validate the Output

```bash
cis-bench validate output.xml
```

The command picks the schema (XCCDF 1.1 or 1.2) from the document's root namespace and uses the schemas shipped with cis-bench; no xmllint, no network.

**Success looks like:**
```
✓ output.xml: valid XCCDF 1.2
```

**Failure looks like (exit code 2):**
```
✗ output.xml: invalid XCCDF 1.2 (1 error)
    line 42: Element '{http://checklists.nist.gov/xccdf/1.2}description': This element is not expected. Expected is ( {http://checklists.nist.gov/xccdf/1.2}title ).
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
from cis_bench.validators.xccdf_schema import validate_xccdf

def test_pci_dss_xsd_validation(sample_benchmark, tmp_path):
    """Verify output validates against the XCCDF 1.2 schema."""
    output_file = tmp_path / "pci_dss_validation.xml"
    exporter = ExporterFactory.create("xccdf", style="pci-dss")
    exporter.export(sample_benchmark, output_file)

    result = validate_xccdf(output_file)

    assert result.version == "1.2"
    assert result.is_valid, result.errors
```

`validate_xccdf` reads a file. For a document still in memory, `check_xccdf(content, source)` takes the serialized bytes and returns the same result; `source` names the document in messages.

A style built on the DISA style also has to pass the DISA conventions check, which runs on the document the shared check parsed:

```python
from cis_bench.validators.disa_conventions import DISAConventionsValidator
from cis_bench.validators.xccdf_schema import read_xccdf

def test_my_disa_style_follows_the_conventions(sample_benchmark, tmp_path):
    output_file = tmp_path / "my_disa_style.xml"
    ExporterFactory.create("xccdf", style="my-disa-style").export(sample_benchmark, output_file)

    is_valid, errors, warnings = DISAConventionsValidator(read_xccdf(output_file)).validate()

    assert is_valid, errors
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
cis-bench validate output.xml

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
  target_element: "metadata"
  structure: "metadata_from_config"
  source_field: "controls"
  metadata_spec:
    # Define structure in YAML
```

### 4. Always Validate Output

Before committing:

```bash
# XSD validation (must pass)
cis-bench validate output.xml

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
- [ ] **XSD validation passes:** `cis-bench validate output.xml`
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
