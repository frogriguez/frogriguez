#!/usr/bin/env python3
"""
render_readme.py

Reads stats.json and rewrites the tagged sections in README.md:
  <!-- STATS_START --> … <!-- STATS_END -->
  <!-- LANG_CHART_START --> … <!-- LANG_CHART_END -->
  <!-- PUBLIC_REPOS_START --> … <!-- PUBLIC_REPOS_END -->
"""

import json
import re
import sys
from pathlib import Path

STATS_FILE  = Path("stats.json")
README_FILE = Path("README.md")


def load_stats() -> dict:
    if not STATS_FILE.exists():
        print("stats.json not found — skipping README render", file=sys.stderr)
        sys.exit(0)
    with open(STATS_FILE) as f:
        return json.load(f)


def fmt_num(n: int | None) -> str:
    if n is None:
        return "—"
    return f"{n:,}"


def replace_section(text: str, tag: str, content: str) -> str:
    pattern = rf"(<!-- {tag}_START -->).*?(<!-- {tag}_END -->)"
    replacement = rf"\1\n{content}\n\2"
    result, count = re.subn(pattern, replacement, text, flags=re.DOTALL)
    if count == 0:
        print(f"  Warning: marker {tag}_START/END not found in README", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def build_stats_table(stats: dict) -> str:
    priv  = stats.get("private_orgs", {})
    pub   = stats.get("public", {})
    langs = stats.get("languages_public_ranked", [])

    pub_top_lang  = langs[0]["lang"] if langs else "—"
    priv_loc      = priv.get("loc_by_lang", {})
    priv_top_lang = next(iter(priv_loc), "—") if priv_loc else "—"

    updated = stats.get("updated_at", "unknown")[:10]

    lines = [
        f"*Last updated: {updated} · Rolling 12-month window*",
        "",
        "| | Public repos | Private org repos |",
        "|---|---|---|",
        f"| **Repos / repos touched** | {fmt_num(pub.get('repo_count'))} | {fmt_num(priv.get('repos_touched'))} |",
        f"| **Commits** | — | {fmt_num(priv.get('total_commits'))} |",
        f"| **Lines added** | — | {fmt_num(priv.get('lines_added'))} |",
        f"| **Lines deleted** | — | {fmt_num(priv.get('lines_deleted'))} |",
        f"| **Net lines** | — | {fmt_num(priv.get('net_lines'))} |",
        f"| **Top language** | {pub_top_lang} | {priv_top_lang} |",
    ]
    return "\n".join(lines)


def build_lang_chart(stats: dict) -> str:
    priv_loc = stats.get("private_orgs", {}).get("loc_by_lang", {})
    if not priv_loc:
        return "*No language data yet.*"

    total = sum(priv_loc.values()) or 1
    bar_width = 30
    lines = ["| Language | Share | |", "|---|---|---|"]
    for lang, nbytes in list(priv_loc.items())[:10]:
        pct   = nbytes / total * 100
        filled = round(pct / 100 * bar_width)
        bar   = "█" * filled + "░" * (bar_width - filled)
        lines.append(f"| {lang} | {pct:.1f}% | `{bar}` |")
    return "\n".join(lines)


def build_public_repos(stats: dict) -> str:
    repos = stats.get("public", {}).get("repos", [])
    if not repos:
        return "*No public repositories found.*"

    blocks = []
    for repo in repos:
        if repo.get("archived"):
            continue
        name  = repo["name"]
        url   = repo["url"]
        desc  = repo.get("description") or "*No description.*"
        lang  = repo.get("primary_lang", "Unknown")
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)
        pushed = (repo.get("pushed_at") or "")[:10]

        topics = repo.get("topics", [])
        topic_str = " ".join(f"`{t}`" for t in topics) if topics else ""

        lines = [
            f"### [{name}]({url})",
            f"{desc}",
        ]
        if topic_str:
            lines.append(topic_str)
        lines.append(
            f"**{lang}** &nbsp;·&nbsp; ★ {stars} &nbsp;·&nbsp; "
            f"⑂ {forks} &nbsp;·&nbsp; last push {pushed}"
        )
        lines.append("")
        blocks.append("\n".join(lines))

    return "\n---\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    stats  = load_stats()
    readme = README_FILE.read_text()

    readme = replace_section(readme, "STATS",        build_stats_table(stats))
    readme = replace_section(readme, "LANG_CHART",   build_lang_chart(stats))
    readme = replace_section(readme, "PUBLIC_REPOS", build_public_repos(stats))

    README_FILE.write_text(readme)
    print("README.md updated")


if __name__ == "__main__":
    main()
