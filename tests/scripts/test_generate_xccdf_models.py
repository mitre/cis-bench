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

# Imports a schema that does not exist: xsdata warns, still exits 0, and generates the rest.
CRATE_SCHEMA = """<?xml version="1.0" encoding="UTF-8"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema"
            xmlns="urn:example:crate" targetNamespace="urn:example:crate"
            elementFormDefault="qualified">
  <xsd:import namespace="urn:example:parts" schemaLocation="parts.xsd"/>
  <xsd:element name="Crate">
    <xsd:complexType>
      <xsd:sequence>
        <xsd:element name="label" type="xsd:string"/>
      </xsd:sequence>
    </xsd:complexType>
  </xsd:element>
</xsd:schema>
"""

BOX = gen.Model(schema=Path("schemas/box.xsd"), package="example.models.box")
CRATE = gen.Model(schema=Path("schemas/crate.xsd"), package="example.models.crate")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    shutil.copy(REPO / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copy(REPO / ".xsdata.xml", tmp_path / ".xsdata.xml")
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "box.xsd").write_text(BOX_SCHEMA, encoding="utf-8")
    (tmp_path / "schemas" / "verdict.xsd").write_text(VERDICT_SCHEMA, encoding="utf-8")
    (tmp_path / "schemas" / "crate.xsd").write_text(CRATE_SCHEMA, encoding="utf-8")
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
    # The project's ruff settings decide the format. xsdata formats its output with ruff's
    # defaults (double quotes), so a project that asks for single quotes only gets them if the
    # script formats with the project's settings.
    pyproject = project / "pyproject.toml"
    settings = pyproject.read_text(encoding="utf-8")
    assert "[tool.ruff.format]" not in settings
    pyproject.write_text(
        settings + '\n[tool.ruff.format]\nquote-style = "single"\n', encoding="utf-8"
    )

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


def test_an_import_xsdata_cannot_read_is_an_error_and_nothing_is_written(project: Path, capsys):
    # A later model's failure leaves an earlier model's package as it was.
    gen.main([], root=project, models=(BOX,))
    module = box_package(project) / "box.py"
    module.write_text("# committed\n", encoding="utf-8")

    assert gen.main([], root=project, models=(BOX, CRATE)) == 2

    err = capsys.readouterr().err
    assert "schemas/crate.xsd" in err
    assert "parts.xsd" in err
    assert module.read_text(encoding="utf-8") == "# committed\n"
    assert not (project / "src" / "example" / "models" / "crate").exists()


def test_an_import_listed_as_known_missing_is_accepted(project: Path):
    crate = gen.Model(
        schema=Path("schemas/crate.xsd"),
        package="example.models.crate",
        known_missing=("parts.xsd",),
    )

    assert gen.main([], root=project, models=(crate,)) == 0

    assert (project / "src" / "example" / "models" / "crate" / "crate.py").is_file()


def test_a_known_missing_import_xsdata_no_longer_reports_is_an_error(project: Path, capsys):
    box = gen.Model(
        schema=Path("schemas/box.xsd"), package="example.models.box", known_missing=("gone.xsd",)
    )

    assert gen.main([], root=project, models=(box,)) == 2

    assert "gone.xsd" in capsys.readouterr().err
    assert not (project / "src").exists()


def test_a_module_that_is_a_symbolic_link_is_not_written_through(
    project: Path, tmp_path_factory: pytest.TempPathFactory
):
    gen.main([], root=project, models=(BOX,))
    outside = tmp_path_factory.mktemp("outside") / "target.py"
    outside.write_text("# not ours\n", encoding="utf-8")
    module = box_package(project) / "box.py"
    module.unlink()
    module.symlink_to(outside)

    assert gen.main([], root=project, models=(BOX,)) == 2

    assert outside.read_text(encoding="utf-8") == "# not ours\n"
    assert module.is_symlink()


def test_a_package_folder_that_is_a_symbolic_link_is_not_written_through(
    project: Path, tmp_path_factory: pytest.TempPathFactory
):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "keep.py").write_text("# not ours\n", encoding="utf-8")
    package = box_package(project)
    package.parent.mkdir(parents=True)
    package.symlink_to(outside, target_is_directory=True)

    assert gen.main([], root=project, models=(BOX,)) == 2

    assert sorted(p.name for p in outside.iterdir()) == ["keep.py"]
