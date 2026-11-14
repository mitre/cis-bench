# Config-Driven Design Principles

!!! info "Documentation Path"
    **You are here:** Design Documents > Config-Driven Design Principles

    - **For design rationale:** See [Design Philosophy](../about/design-philosophy.md)
    - **For implementation:** See [MappingEngine Guide](../developer-guide/mapping-engine-guide.md)

This document defines the architectural principles that ensure the cis-bench codebase remains maintainable and extensible.

---

## Core Principle: Config-Driven Over Hard-Coded

**From our design philosophy:**

> "XCCDF field mappings defined in YAML configuration files, not Python code."

### Correct Pattern

Adding a new compliance framework (e.g., PCI-DSS) requires **only YAML changes**:

```yaml
# pci_dss_style.yaml - NO CODE CHANGES NEEDED
field_mappings:
  pci_requirements:
    target_element: "ident"
    structure: "ident_from_list"
    source_field: "pci_controls"
    ident_spec:
      system_template: "https://www.pcisecuritystandards.org/pci_dss/v{item.version}"
      value_template: "{item.requirement}"
```

**Time to add:** ~30 minutes (YAML only)

### Incorrect Pattern

Hard-coding in Python violates our principles:

```python
# DON'T DO THIS
def generate_pci_idents(self, recommendation):
    """Generate PCI-DSS ident elements."""
    for control in recommendation.pci_controls:
        ident = IdentType(
            system=f"https://pci.org/v{control.version}",  # HARD-CODED!
            value=control.requirement
        )
```

**Time to add:** 3-5 hours (code + tests + docs)

**Why this is wrong:**

- Violates config-driven principle
- Creates organization-specific methods
- Not DRY (Don't Repeat Yourself)
- Not extensible

---

## Core Principle: An Established Tool Before Our Own Code

For parsing, conversion or format work (HTML, Markdown, XML, YAML, CSV, dates, URLs,
identifiers), an established, tested library is chosen before any code of our own is
written. The card's "Prior art checked" section names the candidates, and for the one
chosen: the version read, the license as read from its repository, its dependency health
(last release, last merged change, archived or not) and the verdict. Our own code is
written only when no library fits, and the card records why.

Hand-written code of this kind met in a card's path (a regex that strips HTML, a loop
that rebuilds an XML element from a marker string, a parser for a format a library
reads) is flagged for replacement on that card or on a linked one; it is not extended.

The reason is the record. Hand-written code in this project cut Dublin Core values at a
marker delimiter and parsed templates with a regex that let an unclosed brace through;
both were replaced by what the project already had (xsdata's own element type, the
standard library's format parser). The hand-written HTML conversions (a tag stripper and
a regex HTML-to-Markdown pass) lost `<user>`-style placeholders from recommendation text;
the epic that wrote this rule replaced them with markdownify where HTML enters and with
no conversion at all where the text is already Markdown, then removed them.

---

## Core Principle: The Store Holds What WorkBench Holds

A benchmark's text fields hold the Markdown WorkBench gives, with every line break as
`\n`: nothing is trimmed from either end, nothing is stripped, no entity is decoded, no
Markdown is rewritten. The fetcher stores a recommendation text field or the overview
whose attribute holds only spaces, tabs and line breaks as absent (`None`), and a blank
profile description loads as absent; an artifact title is the string the payload gives.
A stored copy loads what it holds: the validators change line breaks to `\n` and convert
the HTML a copy's form fields record, nothing else. This covers the recommendation text
fields, the benchmark overview (a page without the overview component falls back to the
text of its headings and paragraphs, the one place the fetcher reads rendered HTML), the
profile descriptions and the artifact titles.

HTML is converted once, by markdownify, where it enters: a copy the v1 scraper saved
holds rendered HTML in its text fields and is converted as it loads; the benchmark page
gives profile descriptions as HTML and they are converted as the page is read; the
artifact payload gives some titles as HTML and they are converted as the payload is
parsed. That conversion is the one place entities are decoded (`&lt;user&gt;` becomes the
placeholder `<user>`) and the blank lines at either end of the HTML are left out, because
its output is the Markdown WorkBench would have given. Which form a stored copy holds is
recorded on the copy (`text_format`, `artifact_title_format`) and read from there, never
guessed from the text: in Markdown a placeholder such as `<user>` looks like a tag, and an
HTML parser run on it drops it.

Presentation changes live at export, by a library or by the style. The Markdown export
writes the stored text as it is, and markdown-it-py decides where a `<` in prose must be
written `&lt;` so a renderer shows the placeholder, and where a fence a field leaves open
must be closed before the next field. The XCCDF exports write the stored Markdown as the
text of their elements; a style may name a transform for a field (the CIS style reads the
references field as one `ident` per line through `lines`), and every transform is Python
registered in `TransformRegistry` and named in the YAML, never a rule hidden in an
exporter. Rendering the Markdown to XHTML for the CIS XCCDF is planned, with
markdown-it-py; until it lands, the XCCDF text elements carry Markdown. No exporter trims,
filters or rewrites a value beyond what the style names and the parser decides.

The check, before any transform of stored text is built: probe the real pages for what
they carry (the attribute, the padding, the entities), run the change over every cached
benchmark and read what changes, and for a conversion that runs at load, show that a
value already converted passes through unchanged. A unit test built from a small sample
matches the assumption, not the data.

The reason is the record. The benchmark overview was once passed through a tag stripper,
which deleted a `<path>` placeholder and decoded the page's entities. The first fix
trimmed the text with `str.strip`, which removed the indentation of an overview opening
with an indented code block, so a renderer read it as a paragraph. The second trimmed the
blank lines at either end by CommonMark's rule, which dropped a trailing blank line inside
an open fence and the final line break. Each trim lost something at an edge, and each cost
a review round, until a probe of the cached pages showed that the attribute carries no
padding at all: the answer was no trim. The recommendation fields had the same trim and
the same answer after a probe of several hundred pages. The artifact titles were first
converted unconditionally every time a copy loaded, which emptied a title holding a
placeholder on its second load; the form field on the copy replaced that.

---

## Red Flags to Avoid

### Hand-Written Parsing or Conversion

```python
# Bad - our own rule for what a tag is
text = re.sub(r"<[^>]+>", "", html)

# Good - a tested parser, chosen on the card with its prior-art check
text = BeautifulSoup(html, "html.parser").get_text()
```

The contrast is the point, not the recipe: a parser reads HTML as HTML. Text that mixes
Markdown-like placeholders (`<user>`) with HTML needs the library chosen for that input
after the card's prior-art check, not a tag-stripping call; `get_text()` drops such
placeholders too.

### Trimming or Normalising Stored Text at Ingest

```python
# Bad - a boundary rule of our own on the text WorkBench gives
description = attribute_text(component, "text").strip()

# Good - the text as the page writes it, line breaks as \n
description = unix_line_breaks(attribute_text(component, "text"))
```

Every trim or normalisation of stored text is a transform, and a transform on this data
loses something at an edge: indentation, a blank line inside a fence, a final line break,
a placeholder. The pages are probed first; if they carry nothing to remove, nothing is
removed.

### Organization Names in Method Names

```python
# Bad - organization-specific
def build_cis_controls()
def generate_mitre_idents()
def create_pci_metadata()

# Good - generic
def generate_idents_from_config()
def generate_metadata_from_config()
def generate_profiles_from_rules()
```

### Hard-Coded URIs in Code

```python
# Bad - hard-coded
system = f"http://cisecurity.org/controls/v{version}"

# Good - from config
system = VariableSubstituter.substitute(
    config["system_template"],
    {"item": item}
)
```

### Structure Logic in Python

```python
# Bad - structure hard-coded in code
for version in versions:
    framework = Framework(urn=..., safeguard=...)

# Good - structure from config
group_spec = metadata_spec.get("group_element")
element_name = group_spec.get("element")
attrs = group_spec.get("attributes")
```

### Organization-Specific Branching

```python
# Bad - branching by organization
if framework == "cis":
    build_cis_structure()
elif framework == "pci":
    build_pci_structure()

# Good - generic, no branching
metadata_elem = generate_metadata_from_config(rec, field_mapping)
```

---

## The Generic Handler Library

All XCCDF generation uses these three generic handlers:

### 1. ident_from_list

**Use for:** CCIs, CIS Controls, MITRE ATT&CK, PCI-DSS, ISO 27001, HIPAA

```yaml
framework_controls:
  structure: "ident_from_list"
  source_field: "controls"
  ident_spec:
    system_template: "https://org.com/v{item.version}"
    value_template: "{item.id}"
```

### 2. metadata_from_config

**Use for:** CIS Controls metadata, PCI-DSS hierarchies, ISO 27001 families

```yaml
framework_metadata:
  target_element: "metadata"
  structure: "metadata_from_config"
  metadata_spec:
    root_element: "framework_controls"
    namespace_prefix: "org"  # declared in benchmark.namespaces
    group_by: "item.version"
    group_element:
      element: "family"
      attributes:
        id: "{group_key}"
      item_element:
        element: "control"
        # ... structure from config
```

### 3. generate_profiles_from_rules

**Use for:** CIS Levels, DISA MAC, PCI-DSS tiers

```yaml
profiles:
  generate_from_rules: true
  id_template: "{profile.title|slug:-}"  # every Profile id, from its title
  profile_mappings:

    - match: "Tier 1"
      title: "Tier 1"
```

---

## Code Review Checklist

Before committing any handler code, verify:

- [ ] Method name is generic (no "cis", "mitre", "pci" in name)
- [ ] No hard-coded URIs in the code
- [ ] All structure comes from YAML config
- [ ] Uses VariableSubstituter for templates
- [ ] Adding new framework requires zero code changes
- [ ] Parsing, conversion or format work uses an established library named in the card's
      prior-art check; any new code of our own for such work records why no library fits

- [ ] No hand-written parsing or conversion met in the change was extended instead of
      flagged for replacement

- [ ] Stored text is written as WorkBench gives it: no trim, strip or rewrite at ingest
      beyond `\n` line breaks and the one markdownify conversion where HTML enters; a
      transform of stored text was run over the real cache before it was built

---

## Testing Extensibility

To verify the architecture is correct:

```bash
# Create mock PCI-DSS config (YAML only)
# Export should work without code changes
uv run cis-bench export benchmark.json --format xccdf --style pci-dss
```

If this requires Python changes, the architecture is violated.

---

## Related Documentation

- [Design Philosophy](../about/design-philosophy.md) - Rationale behind these decisions
- [MappingEngine Guide](../developer-guide/mapping-engine-guide.md) - How to use generic handlers
- [Adding PCI-DSS](../developer-guide/adding-pci-dss.md) - Complete example of config-only addition
