"""Generate _index.md files for every directory in the CC vault + a root HOME.md.

Non-destructive: only creates index files, never modifies existing files.
Safe to re-run — overwrites only the generated index files.

Usage:
    python scripts/index_cc_vault.py [--vault "C:/path/to/vault"]
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

SKIP_DIRS = {
    ".obsidian", ".trash", ".git", "__pycache__", ".pytest_cache",
    "node_modules", ".venv", ".claude", ".superpowers",
    "src", "tests", "scripts", "config", "data", "logs", "cache",
}
GENERATED_FILENAMES = {"_index.md", "HOME.md"}


def _wikilink(path: Path, base: Path) -> str:
    """[[section/subsection/stem]] relative to vault root."""
    parts = list(path.relative_to(base).parts)
    parts[-1] = path.stem
    return "[[" + "/".join(parts) + "]]"


def _title(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()


def main() -> None:
    parser = argparse.ArgumentParser(description="Index all files in an Obsidian vault.")
    parser.add_argument(
        "--vault",
        default="C:/Users/alexa/Downloads/AI Operations Command Center",
        help="Path to the Obsidian vault root.",
    )
    args = parser.parse_args()

    vault = Path(args.vault)
    if not vault.exists():
        print(f"Vault not found: {vault}")
        sys.exit(1)

    # Collect all .md files, skip generated indexes and hidden dirs
    all_files: list[Path] = []
    for md in sorted(vault.rglob("*.md")):
        parts = md.relative_to(vault).parts
        if any(p in SKIP_DIRS for p in parts):
            continue
        if md.name in GENERATED_FILENAMES:
            continue
        all_files.append(md)

    # Split into root-level files vs directory-grouped files
    root_files: list[Path] = []
    groups: dict[str, list[Path]] = defaultdict(list)

    for f in all_files:
        parts = f.relative_to(vault).parts
        if len(parts) == 1:
            root_files.append(f)
        else:
            groups[parts[0]].append(f)

    written: list[Path] = []

    # Write _index.md for each top-level directory
    for top_dir, files in sorted(groups.items()):
        dir_path = vault / top_dir
        index_path = dir_path / "_index.md"

        # Sub-group by immediate subdirectory within top_dir
        sub_groups: dict[str, list[Path]] = defaultdict(list)
        for f in sorted(files):
            rel_parts = f.relative_to(dir_path).parts
            sub_key = rel_parts[0] if len(rel_parts) > 1 else "_root"
            sub_groups[sub_key].append(f)

        lines = [
            f"# {_title(top_dir)}",
            "",
            f"*Index — {len(files)} files*",
            "",
        ]

        # _root files first (files directly in top_dir)
        if "_root" in sub_groups:
            for f in sub_groups["_root"]:
                lines.append(f"- {_wikilink(f, vault)}")
            lines.append("")

        # Then subdirectory groups
        for sub, sub_files in sorted((k, v) for k, v in sub_groups.items() if k != "_root"):
            lines += [f"## {_title(sub)}", ""]
            for f in sorted(sub_files):
                lines.append(f"- {_wikilink(f, vault)}")
            lines.append("")

        index_path.write_text("\n".join(lines), encoding="utf-8")
        written.append(index_path)

    # Write root HOME.md
    home_path = vault / "HOME.md"
    home_lines = [
        "# Command Center — Home",
        "",
        f"*Master index — {len(all_files)} files across {len(groups)} sections*",
        "",
    ]

    if root_files:
        home_lines += ["## Root Files", ""]
        for f in sorted(root_files):
            home_lines.append(f"- {_wikilink(f, vault)}")
        home_lines.append("")

    home_lines += ["## Sections", ""]
    for top_dir in sorted(groups.keys()):
        count = len(groups[top_dir])
        home_lines.append(f"- [[{top_dir}/_index]] — {count} files")
    home_lines.append("")

    home_path.write_text("\n".join(home_lines), encoding="utf-8")
    written.append(home_path)

    print(f"Indexed {len(all_files)} files, wrote {len(written)} index files")
    for w in written:
        print(f"  {w.relative_to(vault)}")


if __name__ == "__main__":
    main()
