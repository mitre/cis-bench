"""Tests for scripts/fix_markdown_lists.py, the pre-commit hook that puts a blank line before
a list that follows a text line (Python-Markdown, which builds the docs, otherwise renders the
list as part of the paragraph).

These tests are for project development utilities, not the cis-bench package.
Run with: pytest tests/scripts (the plain test run leaves this folder out)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from fix_markdown_lists import fix_list_formatting  # noqa: E402


def fixed(text: str) -> str:
    return fix_list_formatting(text)[0]


def test_a_bullet_list_after_a_text_line_gets_a_blank_line():
    assert fix_list_formatting("**Check:**\n- one\n- two\n") == (
        "**Check:**\n\n- one\n- two\n",
        1,
    )


def test_a_numbered_list_after_a_text_line_gets_a_blank_line():
    assert fix_list_formatting("**Check:**\n1. one\n2. two\n3) three\n") == (
        "**Check:**\n\n1. one\n2. two\n3) three\n",
        1,
    )


def test_a_list_after_a_blank_line_or_another_item_is_left_alone():
    text = "Text.\n\n- one\n- two\n  - nested\n1. first\n"
    assert fix_list_formatting(text) == (text, 0)


def test_an_item_after_the_wrapped_lines_of_the_item_before_it_is_left_alone():
    text = (
        "Steps:\n\n"
        "1. Collect every CCI, primary first, each\n"
        "   once.\n"
        "2. Cite the controls:\n"
        "   ```yaml\n"
        "   - CM-7\n"
        "   ```\n"
        "3. Done\n"
        "- a\n"
        "lazy continuation of a\n"
        "- b\n"
    )
    assert fix_list_formatting(text) == (text, 0)


def test_list_lines_inside_a_backtick_fence_are_left_alone():
    text = "```console\n$ cis-bench find x -o yaml\n- benchmark_id: '1'\n  matched_fields:\n  - title\n```\n"
    assert fix_list_formatting(text) == (text, 0)


def test_list_lines_inside_a_tilde_fence_are_left_alone():
    text = "~~~yaml\nkeys:\n- a\n~~~\n"
    assert fix_list_formatting(text) == (text, 0)


def test_a_fence_indented_under_an_admonition_is_left_alone_and_the_text_after_it_is_checked():
    text = '!!! note "Example"\n    ```yaml\n    keys:\n    - a\n    ```\n    Then:\n    - b\n'
    assert fixed(text) == (
        '!!! note "Example"\n    ```yaml\n    keys:\n    - a\n    ```\n    Then:\n\n    - b\n'
    )


def test_a_shorter_fence_inside_a_longer_one_does_not_close_it():
    text = "````markdown\n```\nnot closed\n```\nText\n- inside\n````\n"
    assert fix_list_formatting(text) == (text, 0)


def test_a_fence_closes_only_on_its_own_character():
    text = "```\n~~~\nText\n- inside\n```\nAfter:\n- outside\n"
    assert fixed(text) == "```\n~~~\nText\n- inside\n```\nAfter:\n\n- outside\n"


def test_yaml_front_matter_is_left_alone():
    text = "---\ntags:\n- cli\n---\n\n# Title\n"
    assert fix_list_formatting(text) == (text, 0)


def test_a_second_run_changes_nothing():
    once = fixed("Text\n- a\n```\nx\n- y\n```\nMore\n1. z\n")
    assert fix_list_formatting(once) == (once, 0)
