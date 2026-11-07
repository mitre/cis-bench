"""Diff detail view component."""

from cis_bench.cli.commands.tui.base import DetailView, html_to_markdown


class DiffDetailView(DetailView):
    """Shows detailed field-by-field diff for a selected change."""

    def update_content(
        self,
        change_type: str,
        change_data: dict,
        old_rec: dict | None,
        new_rec: dict | None,
    ):
        """Update the detail view with change information."""
        lines = []

        if change_type == "added":
            lines.append(f"# ✚ ADDED: {change_data['ref']}")
            lines.append(f"**{change_data['title']}**\n")
            if new_rec:
                if new_rec.get("description"):
                    lines.append("## Description")
                    lines.append(html_to_markdown(new_rec["description"]))
                    lines.append("")
                if new_rec.get("rationale"):
                    lines.append("## Rationale")
                    lines.append(html_to_markdown(new_rec["rationale"]))
                    lines.append("")
                if new_rec.get("audit"):
                    lines.append("## Audit")
                    lines.append(html_to_markdown(new_rec["audit"]))
                    lines.append("")
                if new_rec.get("remediation"):
                    lines.append("## Remediation")
                    lines.append(html_to_markdown(new_rec["remediation"]))

        elif change_type == "removed":
            lines.append(f"# ✖ REMOVED: {change_data['ref']}")
            lines.append(f"**{change_data['title']}**\n")
            if old_rec:
                if old_rec.get("description"):
                    lines.append("## Description (was)")
                    lines.append(html_to_markdown(old_rec["description"]))

        elif change_type == "modified":
            lines.append(f"# ⟳ MODIFIED: {change_data['ref']}")
            lines.append(f"**{change_data['title']}**\n")
            lines.append("## Changed Fields\n")

            visible_changes = 0
            for field in change_data.get("fields_changed", []):
                old_val = old_rec.get(field, "") if old_rec else ""
                new_val = new_rec.get(field, "") if new_rec else ""

                # Normalize both values
                old_md = html_to_markdown(str(old_val)) if old_val else ""
                new_md = html_to_markdown(str(new_val)) if new_val else ""

                # Skip if visually identical (encoding/whitespace differences only)
                if old_md.strip() == new_md.strip():
                    continue

                visible_changes += 1
                lines.append(f"### {field.title()}")
                lines.append("")

                if old_md:
                    lines.append("**Before:**")
                    lines.append(
                        f"```diff\n- {old_md[:500]}{'...' if len(old_md) > 500 else ''}\n```"
                    )
                    lines.append("")

                if new_md:
                    lines.append("**After:**")
                    lines.append(
                        f"```diff\n+ {new_md[:500]}{'...' if len(new_md) > 500 else ''}\n```"
                    )
                    lines.append("")

            if visible_changes == 0:
                lines.append("*Only formatting/encoding changes (no visible content difference)*")

        elif change_type == "renumbered":
            lines.append(f"# ↷ RENUMBERED: {change_data['old_ref']} → {change_data['new_ref']}")
            lines.append(f"**{change_data['title']}**\n")
            lines.append(f"Similarity: **{change_data['similarity']}%**\n")
            if new_rec and new_rec.get("description"):
                lines.append("## Description")
                lines.append(html_to_markdown(new_rec["description"]))

        self.set_content("\n".join(lines))
