"""Tests for scripts/generate_xccdf_models.py, which generates the XCCDF model packages from the
XCCDF schemas with xsdata and the project's ruff, or checks that the committed packages match.

The tests generate a small local schema (no network) inside a temporary project that holds a
copy of this project's pyproject.toml and .xsdata.xml, so the script's xsdata and ruff runs use
the real configuration.

These tests are for project development utilities, not the cis-bench package.
Run with: pytest tests/scripts (the plain test run leaves this folder out)
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "generate_xccdf_models.py"

_spec = importlib.util.spec_from_file_location("generate_xccdf_models", SCRIPT)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gen
_spec.loader.exec_module(gen)

BOX_SCHEMA = """<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns="urn:example:box" targetNamespace="urn:example:box"
            elementFormDefault="qualified">
  <xsd:element name="Box">
    <xsd:complexType>
      <xsd:sequence>
        <xsd:element name="label" type="xsd:string"/>
      </xsd:sequence>
      <xsd:attribute name="id" type="xsd:string" use="required"/>
    </xsd:complexType>
  </xsd:element>
</xsd:schema>
"""

# An enumeration value named "pass": ruff's S105 reports it as a possible password, which the
# project's per-file ignores allow only for the XCCDF model packages.
VERDICT_SCHEMA = """<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns="urn:example:verdict" targetNamespace="urn:example:verdict"
            elementFormDefault="qualified">
  <xsd:simpleType name="verdictType">
    <xsd:restriction base="xsd:string">
      <xsd:enumeration value="pass"/>
      <xsd:enumeration value="fail"/>
    </xsd:restriction>
  </xsd:simpleType>
  <xsd:element name="verdict" type="verdictType"/>
</xsd:schema>
"""

BOX = gen.Model(schema=Path("schemas/box.xsd"), package="example.models.box")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copy(REPO / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copy(REPO / ".xsdata.xml", tmp_path / ".xsdata.xml")
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "box.xsd").write_text(BOX_SCHEMA, encoding="utf-8")
    (tmp_path / "schemas" / "verdict.xsd").write_text(VERDICT_SCHEMA, encoding="utf-8")
    return tmp_path


def box_package(project: Path) -> Path:
    return project / "src" / "example" / "models" / "box"


def ruff(project: Path, *args: str, path: Path, text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args, "--stdin-filename", str(path), "-"],
        input=text,
        capture_output=True,
        text=True,
        cwd=project,
        check=False,
    )


def test_a_schema_is_generated_into_the_named_package_and_formatted(project: Path):
    rendered = gen.render(BOX, project)

    package = box_package(project)
    assert set(rendered) == {package / "__init__.py", package / "box.py"}
    assert "class Box:" in rendered[package / "box.py"]
    for path, text in rendered.items():
        assert ruff(project, "format", "--check", path=path, text=text).returncode == 0, path
        assert ruff(project, "check", path=path, text=text).returncode == 0, path
    # Rendering only reads: the package is written by generating.
    assert not (project / "src").exists()


def test_generating_writes_the_package_and_check_then_passes(project: Path, capsys):
    assert gen.main([], root=project, models=(BOX,)) == 0
    assert (box_package(project) / "box.py").is_file()

    assert gen.main(["--check"], root=project, models=(BOX,)) == 0
    assert "match" in capsys.readouterr().out


def test_check_reports_a_changed_module_and_writes_nothing(project: Path, capsys):
    gen.main([], root=project, models=(BOX,))
    module = box_package(project) / "box.py"
    module.write_text(module.read_text(encoding="utf-8") + "# edited\n", encoding="utf-8")
    edited = module.read_text(encoding="utf-8")
    capsys.readouterr()

    assert gen.main(["--check"], root=project, models=(BOX,)) == 1

    assert "src/example/models/box/box.py" in capsys.readouterr().out
    assert module.read_text(encoding="utf-8") == edited


def test_check_reports_a_missing_module_and_one_the_generator_does_not_write(project: Path, capsys):
    gen.main([], root=project, models=(BOX,))
    package = box_package(project)
    (package / "box.py").unlink()
    (package / "leftover.py").write_text("X = 1\n", encoding="utf-8")
    capsys.readouterr()

    assert gen.main(["--check"], root=project, models=(BOX,)) == 1

    out = capsys.readouterr().out
    assert "src/example/models/box/box.py" in out
    assert "src/example/models/box/leftover.py" in out
    assert not (package / "box.py").exists()


def test_generating_removes_a_module_the_generator_no_longer_writes(project: Path):
    gen.main([], root=project, models=(BOX,))
    package = box_package(project)
    (package / "leftover.py").write_text("X = 1\n", encoding="utf-8")
    parent_init = project / "src" / "example" / "__init__.py"
    parent_init.write_text('"""Not generated."""\n', encoding="utf-8")

    assert gen.main([], root=project, models=(BOX,)) == 0

    assert not (package / "leftover.py").exists()
    assert (package / "box.py").is_file()
    assert parent_init.read_text(encoding="utf-8") == '"""Not generated."""\n'


def test_a_schema_the_generator_cannot_read_is_an_error_and_nothing_is_written(
    project: Path, capsys
):
    missing = gen.Model(schema=Path("schemas/missing.xsd"), package="example.models.missing")

    assert gen.main([], root=project, models=(missing,)) == 2

    assert "schemas/missing.xsd" in capsys.readouterr().err
    assert not (project / "src").exists()


def test_a_lint_finding_ruff_cannot_fix_is_an_error_and_nothing_is_written(project: Path, capsys):
    verdict = gen.Model(schema=Path("schemas/verdict.xsd"), package="example.models.verdict")

    assert gen.main([], root=project, models=(verdict,)) == 2

    assert "S105" in capsys.readouterr().err
    assert not (project / "src").exists()
