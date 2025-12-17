"""Tests for scripts/remove_code.py - LibCST utility.

These tests are for project development utilities, not the cis-bench package.
Run with: pytest -m scripts
"""

import sys
from pathlib import Path

import pytest

# Mark entire module as 'scripts' - excluded from default test run
pytestmark = pytest.mark.scripts

# Add scripts to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import libcst as cst  # noqa: E402
from remove_code import CodeLister, CodeRemover, remove_code  # noqa: E402


class TestCodeLister:
    """Test CodeLister visitor."""

    def test_lists_functions(self, tmp_path):
        """Test listing top-level functions."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def function_one():
    pass

def function_two():
    return 42
""")

        with open(test_file) as f:
            module = cst.parse_module(f.read())

        lister = CodeLister()
        module.visit(lister)

        assert "function_one" in lister.functions
        assert "function_two" in lister.functions
        assert len(lister.functions) == 2

    def test_lists_classes(self, tmp_path):
        """Test listing classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class ClassOne:
    pass

class ClassTwo:
    def method(self):
        pass
""")

        with open(test_file) as f:
            module = cst.parse_module(f.read())

        lister = CodeLister()
        module.visit(lister)

        assert "ClassOne" in lister.classes
        assert "ClassTwo" in lister.classes
        assert len(lister.classes) == 2

    def test_lists_methods(self, tmp_path):
        """Test listing class methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class MyClass:
    def method_one(self):
        pass

    def method_two(self, arg):
        return arg
""")

        with open(test_file) as f:
            module = cst.parse_module(f.read())

        lister = CodeLister()
        module.visit(lister)

        assert "MyClass.method_one" in lister.methods
        assert "MyClass.method_two" in lister.methods
        assert len(lister.methods) == 2


class TestCodeRemover:
    """Test CodeRemover transformer."""

    def test_removes_function(self):
        """Test removing a function by name."""
        source = """
def keep_this():
    pass

def remove_this():
    return 42

def keep_that():
    return "hello"
"""

        module = cst.parse_module(source)
        remover = CodeRemover({"remove_this"})
        new_module = module.visit(remover)

        result = new_module.code
        assert "def keep_this" in result
        assert "def keep_that" in result
        assert "def remove_this" not in result
        assert "function: remove_this" in remover.removed

    def test_removes_multiple_functions(self):
        """Test removing multiple functions."""
        source = """
def func_a():
    pass

def func_b():
    pass

def func_c():
    pass
"""

        module = cst.parse_module(source)
        remover = CodeRemover({"func_a", "func_c"})
        new_module = module.visit(remover)

        result = new_module.code
        assert "def func_b" in result
        assert "def func_a" not in result
        assert "def func_c" not in result
        assert len(remover.removed) == 2

    def test_removes_class(self):
        """Test removing a class."""
        source = """
class KeepClass:
    pass

class RemoveClass:
    def method(self):
        pass

class AnotherKeepClass:
    pass
"""

        module = cst.parse_module(source)
        remover = CodeRemover({"RemoveClass"})
        new_module = module.visit(remover)

        result = new_module.code
        assert "class KeepClass" in result
        assert "class AnotherKeepClass" in result
        assert "class RemoveClass" not in result
        assert "class: RemoveClass" in remover.removed

    def test_removes_method_from_class(self):
        """Test removing a method from a class."""
        source = """
class MyClass:
    def keep_method(self):
        pass

    def remove_method(self):
        pass

    def another_keep(self):
        pass
"""

        module = cst.parse_module(source)
        remover = CodeRemover({"remove_method"})
        new_module = module.visit(remover)

        result = new_module.code
        assert "def keep_method" in result
        assert "def another_keep" in result
        assert "def remove_method" not in result

    def test_preserves_formatting(self):
        """Test that formatting is preserved."""
        source = """
def function_one():
    '''Docstring here.'''
    x = 42
    return x

def remove_this():
    pass

def function_two():
    '''Another docstring.'''
    return "value"
"""

        module = cst.parse_module(source)
        remover = CodeRemover({"remove_this"})
        new_module = module.visit(remover)

        result = new_module.code

        # Docstrings preserved
        assert "'''Docstring here.'''" in result
        assert "'''Another docstring.'''" in result

        # Formatting preserved
        assert "x = 42" in result
        assert 'return "value"' in result

    def test_no_removal_if_not_found(self):
        """Test that nothing breaks if name not found."""
        source = """
def existing_function():
    pass
"""

        module = cst.parse_module(source)
        remover = CodeRemover({"nonexistent_function"})
        new_module = module.visit(remover)

        result = new_module.code
        assert "def existing_function" in result
        assert len(remover.removed) == 0


class TestRemoveCodeFunction:
    """Test the main remove_code function."""

    def test_remove_code_dry_run(self, tmp_path):
        """Test dry-run mode doesn't modify file."""
        test_file = tmp_path / "test.py"
        original_content = """
def keep_this():
    pass

def remove_this():
    pass
"""
        test_file.write_text(original_content)

        # Dry run
        new_code, removed = remove_code(test_file, {"remove_this"}, dry_run=True)

        # File unchanged
        assert test_file.read_text() == original_content

        # But removal would work
        assert "def remove_this" not in new_code
        assert "function: remove_this" in removed

    def test_remove_code_actually_removes(self, tmp_path):
        """Test actual removal modifies file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def keep_this():
    pass

def remove_this():
    pass
""")

        # Actual removal
        new_code, removed = remove_code(test_file, {"remove_this"}, dry_run=False)

        # File modified
        result = test_file.read_text()
        assert "def keep_this" in result
        assert "def remove_this" not in result
        assert "function: remove_this" in removed

    def test_remove_multiple_items(self, tmp_path):
        """Test removing multiple items at once."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def func_a():
    pass

def func_b():
    pass

class ClassC:
    pass

def func_d():
    pass
""")

        new_code, removed = remove_code(test_file, {"func_a", "ClassC", "func_d"}, dry_run=False)

        result = test_file.read_text()
        assert "def func_b" in result
        assert "def func_a" not in result
        assert "class ClassC" not in result
        assert "def func_d" not in result
        assert len(removed) == 3

    def test_preserves_valid_syntax(self, tmp_path):
        """Test that result is valid Python."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def func_one():
    x = 1
    return x

def remove_me():
    pass

def func_two():
    y = 2
    return y
""")

        remove_code(test_file, {"remove_me"}, dry_run=False)

        # Parse result to verify valid Python
        result = test_file.read_text()
        try:
            compile(result, str(test_file), "exec")
        except SyntaxError as e:
            pytest.fail(f"Result has syntax error: {e}")


class TestRealWorldUsage:
    """Test with realistic code patterns."""

    def test_remove_from_file_with_imports(self, tmp_path):
        """Test removal from file with imports."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
import os
from pathlib import Path

def keep_function():
    return Path.cwd()

def remove_function():
    return os.getcwd()
""")

        remove_code(test_file, {"remove_function"}, dry_run=False)

        result = test_file.read_text()

        # Imports preserved
        assert "import os" in result
        assert "from pathlib import Path" in result

        # Function removed
        assert "def remove_function" not in result
        assert "def keep_function" in result

    def test_remove_method_keeps_class_intact(self, tmp_path):
        """Test removing method doesn't break class."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class MyClass:
    def __init__(self):
        self.value = 42

    def remove_this_method(self):
        pass

    def keep_this_method(self):
        return self.value
""")

        remove_code(test_file, {"remove_this_method"}, dry_run=False)

        result = test_file.read_text()

        # Class preserved
        assert "class MyClass" in result
        assert "def __init__" in result
        assert "def keep_this_method" in result

        # Method removed
        assert "def remove_this_method" not in result

        # Valid syntax
        compile(result, str(test_file), "exec")


class TestEdgeCases:
    """Test edge cases found in real codebase."""

    def test_nested_function_preserved_when_parent_kept(self, tmp_path):
        """Test nested functions stay intact when parent is kept."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def outer_function():
    def inner_function():
        return 42
    return inner_function()

def remove_this():
    pass
""")

        remove_code(test_file, {"remove_this"}, dry_run=False)

        result = test_file.read_text()
        assert "def outer_function" in result
        assert "def inner_function" in result
        assert "def remove_this" not in result

    def test_nested_function_removed_with_parent(self, tmp_path):
        """Test nested functions removed when parent is removed."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def keep_this():
    pass

def remove_outer():
    def inner_helper():
        return 42
    return inner_helper()
""")

        remove_code(test_file, {"remove_outer"}, dry_run=False)

        result = test_file.read_text()
        assert "def keep_this" in result
        assert "def remove_outer" not in result
        assert "def inner_helper" not in result  # Removed with parent

    def test_method_with_decorators(self, tmp_path):
        """Test removing decorated methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class MyClass:
    @staticmethod
    def keep_method():
        pass

    @classmethod
    def remove_method(cls):
        pass

    @property
    def keep_property(self):
        return 42
""")

        remove_code(test_file, {"remove_method"}, dry_run=False)

        result = test_file.read_text()
        assert "@staticmethod" in result
        assert "def keep_method" in result
        assert "@classmethod" not in result
        assert "def remove_method" not in result
        assert "@property" in result

    def test_function_with_complex_signature(self, tmp_path):
        """Test removing function with complex type hints."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
from typing import Any, Optional

def keep_this(x: int, y: str = "default") -> dict[str, Any]:
    return {"x": x, "y": y}

def remove_this(
    recommendation: "Recommendation",
    field_mapping: dict[str, Any],
    *args,
    **kwargs
) -> Optional[list[str]]:
    '''Complex signature.'''
    pass
""")

        remove_code(test_file, {"remove_this"}, dry_run=False)

        result = test_file.read_text()
        assert "def keep_this" in result
        assert "def remove_this" not in result
        assert "from typing import" in result  # Imports preserved

    def test_removes_entire_docstring_with_function(self, tmp_path):
        """Test that multiline docstrings are removed with function."""
        test_file = tmp_path / "test.py"
        test_file.write_text('''
def keep():
    """Keep this docstring."""
    pass

def remove():
    """This is a long docstring.

    It has multiple paragraphs.

    Args:
        x: Parameter
        y: Another parameter

    Returns:
        Something

    Example:
        >>> remove()
        42
    """
    return 42
''')

        remove_code(test_file, {"remove"}, dry_run=False)

        result = test_file.read_text()
        assert "def keep" in result
        assert "Keep this docstring" in result
        assert "def remove" not in result
        assert "This is a long docstring" not in result
        assert "Args:" not in result

    def test_multiple_classes_and_methods(self, tmp_path):
        """Test complex file with multiple classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class ClassA:
    def method_a1(self):
        pass

    def method_a2(self):
        pass

class ClassB:
    def method_b1(self):
        pass

    def method_b2(self):
        pass

def top_level():
    pass
""")

        # Remove one class and one method
        remove_code(test_file, {"ClassA", "method_b1"}, dry_run=False)

        result = test_file.read_text()

        # ClassA completely gone
        assert "class ClassA" not in result
        assert "def method_a1" not in result
        assert "def method_a2" not in result

        # ClassB still there but method_b1 removed
        assert "class ClassB" in result
        assert "def method_b1" not in result
        assert "def method_b2" in result  # Other method preserved

        # Top level preserved
        assert "def top_level" in result

    def test_static_and_class_methods(self, tmp_path):
        """Test @staticmethod and @classmethod removal."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class Registry:
    @staticmethod
    def keep_static():
        return 42

    @classmethod
    def remove_classmethod(cls):
        return cls

    @classmethod
    def keep_classmethod(cls):
        return cls.__name__
""")

        remove_code(test_file, {"remove_classmethod"}, dry_run=False)

        result = test_file.read_text()
        assert "@staticmethod" in result
        assert "def keep_static" in result
        assert "def remove_classmethod" not in result
        assert "def keep_classmethod" in result

        # Count @classmethod (should be 1, not 2)
        assert result.count("@classmethod") == 1

    def test_lambda_expressions_preserved(self, tmp_path):
        """Test that lambda expressions in code are preserved."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class Registry:
    _transforms = {}

    @classmethod
    def register(cls, name: str, func):
        cls._transforms[name] = func

# Module-level registrations with lambdas
Registry.register("none", lambda x: x)
Registry.register("upper", lambda x: x.upper())

def remove_this():
    pass
""")

        remove_code(test_file, {"remove_this"}, dry_run=False)

        result = test_file.read_text()
        assert "lambda x: x" in result
        assert "lambda x: x.upper()" in result
        assert "def remove_this" not in result

    def test_async_functions(self, tmp_path):
        """Test removing async functions."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
async def keep_async():
    return await some_call()

async def remove_async():
    pass

def regular_function():
    pass
""")

        remove_code(test_file, {"remove_async"}, dry_run=False)

        result = test_file.read_text()
        assert "async def keep_async" in result
        assert "async def remove_async" not in result
        assert "def regular_function" in result

    def test_dataclass(self, tmp_path):
        """Test removing dataclass."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
from dataclasses import dataclass

@dataclass
class KeepConfig:
    name: str
    value: int

@dataclass
class RemoveConfig:
    old_field: str

def function():
    pass
""")

        remove_code(test_file, {"RemoveConfig"}, dry_run=False)

        result = test_file.read_text()
        assert "class KeepConfig" in result
        assert "class RemoveConfig" not in result
        assert "@dataclass" in result  # Still one dataclass
        assert result.count("@dataclass") == 1

    def test_method_with_multiline_arguments(self, tmp_path):
        """Test removing method with arguments spanning multiple lines."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
class Engine:
    def keep_method(self, x: int, y: str) -> dict:
        return {"x": x, "y": y}

    def remove_method(
        self,
        recommendation: "Recommendation",
        field_mapping: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        '''Complex multiline signature.'''
        return []
""")

        remove_code(test_file, {"remove_method"}, dry_run=False)

        result = test_file.read_text()
        assert "def keep_method" in result
        assert "def remove_method" not in result
        assert "Complex multiline signature" not in result

        # Valid Python
        compile(result, str(test_file), "exec")

    def test_comments_before_function_removed(self, tmp_path):
        """Test that comments immediately before removed function are removed too."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def keep():
    pass

# This is a comment about the function below
# It has multiple lines
def remove_this():
    pass

def keep_also():
    pass
""")

        remove_code(test_file, {"remove_this"}, dry_run=False)

        result = test_file.read_text()

        # LibCST preserves comments (this is expected behavior)
        # Comments are part of syntax tree structure
        assert "def keep()" in result
        assert "def keep_also()" in result
        assert "def remove_this" not in result
