#!/usr/bin/env python3
"""
collect_stats.py

Queries the GitHub REST API to build a stats.json summarising:
  - Public repos owned by GH_USERNAME (full metadata)
  - Contributions across private org repos (aggregated counts only —
    no repo names, commit messages, or code content are written to disk)

Required environment variables:
  GH_STATS_TOKEN  Classic PAT with scopes: repo, read:org, read:user
  GH_USERNAME     Your GitHub login (e.g. frogriguez)
  GH_ORGS         Comma-separated list of org names (e.g. org1,org2,org3,org4)

Output: stats.json in the repo root.
"""

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests
from dateutil.relativedelta import relativedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOKEN    = os.environ["GH_STATS_TOKEN"]
USERNAME = os.environ["GH_USERNAME"].strip()
ORGS     = [o.strip() for o in os.environ["GH_ORGS"].split(",") if o.strip()]

API      = "https://api.github.com"
HEADERS  = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Only count activity in the rolling 12-month window
SINCE = (datetime.now(timezone.utc) - relativedelta(months=12)).isoformat()

# Languages to skip (markup, config, data — not code)
SKIP_LANGS = {
    "Markdown", "HTML", "CSS", "Jupyter Notebook",
    "YAML", "JSON", "TOML", "XML", "Text", "Shell",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get(url: str, params: dict | None = None) -> dict | list:
    """GET with simple rate-limit backoff."""
    for attempt in range(5):
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (403, 429):
            reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait  = max(reset - time.time(), 1) + 2
            print(f"  Rate-limited. Sleeping {wait:.0f}s …", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Failed GET {url} after 5 attempts")


def paginate(url: str, params: dict | None = None) -> list:
    """Follow GitHub pagination and return all items."""
    params = dict(params or {})
    params.setdefault("per_page", 100)
    results = []
    page = 1
    while True:
        params["page"] = page
        batch = get(url, params)
        if not batch:
            break
        results.extend(batch)
        if len(batch) < params["per_page"]:
            break
        page += 1
    return results


def lang_bytes_for_repo(repo_full_name: str) -> dict[str, int]:
    """Return {language: bytes} for a repo."""
    try:
        return get(f"{API}/repos/{repo_full_name}/languages")
    except Exception:
        return {}


def commit_stats_for_repo(
    repo_full_name: str, author: str, since: str
) -> tuple[int, int, int]:
    """Return (commit_count, lines_added, lines_deleted) for `author` since `since`."""
    commits = paginate(
        f"{API}/repos/{repo_full_name}/commits",
        {"author": author, "since": since},
    )
    added = deleted = 0
    for c in commits:
        sha = c["sha"]
        try:
            detail = get(f"{API}/repos/{repo_full_name}/commits/{sha}")
            stats  = detail.get("stats", {})
            added   += stats.get("additions", 0)
            deleted += stats.get("deletions", 0)
        except Exception:
            pass   # best-effort; skip commits we can't read
    return len(commits), added, deleted


# ---------------------------------------------------------------------------
# Public repos
# ---------------------------------------------------------------------------

def _repo_to_record(repo: dict, owner: str) -> dict:
    """Convert a GitHub repo object to a stats record."""
    full  = repo["full_name"]
    langs = lang_bytes_for_repo(full)
    primary_lang = max(langs, key=langs.get) if langs else repo.get("language") or "Unknown"
    return {
        "name":         repo["name"],
        "full_name":    full,
        "description":  repo.get("description") or "",
        "url":          repo["html_url"],
        "stars":        repo["stargazers_count"],
        "forks":        repo["forks_count"],
        "primary_lang": primary_lang,
        "languages":    langs,
        "pushed_at":    repo.get("pushed_at"),
        "topics":       repo.get("topics", []),
        "archived":     repo.get("archived", False),
        "owner":        owner,
    }


def collect_public() -> list[dict]:
    print("Collecting public repos …")
    results = []

    # Personal repos
    personal_repos = paginate(
        f"{API}/users/{USERNAME}/repos",
        {"type": "public", "sort": "pushed"},
    )
    for repo in personal_repos:
        if repo.get("fork"):
            continue
        results.append(_repo_to_record(repo, "personal"))
    print(f"  {len(results)} personal public repos")

    # Public repos in each org
    for org in ORGS:
        print(f"  Collecting public repos for org: {org} …")
        try:
            org_repos = paginate(
                f"{API}/orgs/{org}/repos",
                {"type": "public", "sort": "pushed"},
            )
        except Exception as e:
            print(f"    Could not list repos for {org}: {e}", file=sys.stderr)
            continue
        before = len(results)
        for repo in org_repos:
            if repo.get("fork"):
                continue
            results.append(_repo_to_record(repo, org))
        print(f"    {len(results) - before} public repos in {org}")

    print(f"  {len(results)} total public repos found")
    return results


# ---------------------------------------------------------------------------
# Private org contributions (aggregated only)
# ---------------------------------------------------------------------------

def collect_private_orgs() -> dict:
    """
    Iterate over all repos in each org, sum commit counts and LOC for
    commits authored by USERNAME. Returns per-org breakdowns plus an
    "ALL" aggregate. No per-repo names or commit messages are written.
    """
    all_commits  = 0
    all_added    = 0
    all_deleted  = 0
    all_lang_bytes: dict[str, int] = defaultdict(int)
    all_repos_touched = 0

    result: dict[str, dict] = {}

    for org in ORGS:
        print(f"Scanning org: {org} …")
        org_commits = org_added = org_deleted = 0
        org_lang_bytes: dict[str, int] = defaultdict(int)
        org_repos_touched = 0

        try:
            repos = paginate(f"{API}/orgs/{org}/repos", {"type": "all"})
        except Exception as e:
            print(f"  Could not list repos for {org}: {e}", file=sys.stderr)
            continue

        for repo in repos:
            full = repo["full_name"]
            try:
                sample = get(
                    f"{API}/repos/{full}/commits",
                    {"author": USERNAME, "since": SINCE, "per_page": 1},
                )
            except Exception:
                continue
            if not sample:
                continue

            org_repos_touched += 1
            print(f"  Found commits in {full}")

            for lang, nbytes in lang_bytes_for_repo(full).items():
                if lang not in SKIP_LANGS:
                    org_lang_bytes[lang]  += nbytes
                    all_lang_bytes[lang]  += nbytes

            n_commits, added, deleted = commit_stats_for_repo(full, USERNAME, SINCE)
            org_commits  += n_commits
            org_added    += added
            org_deleted  += deleted

        all_commits       += org_commits
        all_added         += org_added
        all_deleted       += org_deleted
        all_repos_touched += org_repos_touched

        org_lang_ranked = sorted(org_lang_bytes.items(), key=lambda x: x[1], reverse=True)
        result[org] = {
            "repos_touched": org_repos_touched,
            "total_commits": org_commits,
            "lines_added":   org_added,
            "lines_deleted": org_deleted,
            "net_lines":     org_added - org_deleted,
            "loc_by_lang":   dict(org_lang_ranked),
        }

    all_lang_ranked = sorted(all_lang_bytes.items(), key=lambda x: x[1], reverse=True)
    result["ALL"] = {
        "repos_touched": all_repos_touched,
        "total_commits": all_commits,
        "lines_added":   all_added,
        "lines_deleted": all_deleted,
        "net_lines":     all_added - all_deleted,
        "loc_by_lang":   dict(all_lang_ranked),
    }

    return result


# ---------------------------------------------------------------------------
# Public language ranking (across all public repos)
# ---------------------------------------------------------------------------

def public_lang_ranking(public_repos: list[dict]) -> list[dict]:
    totals: dict[str, int] = defaultdict(int)
    for repo in public_repos:
        for lang, nbytes in repo.get("languages", {}).items():
            if lang not in SKIP_LANGS:
                totals[lang] += nbytes
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    grand_total = sum(b for _, b in ranked) or 1
    return [
        {"lang": lang, "bytes": nbytes, "pct": round(nbytes / grand_total * 100, 1)}
        for lang, nbytes in ranked[:10]
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Starting stats collection for {USERNAME}")
    print(f"Orgs: {', '.join(ORGS)}")
    print(f"Activity window: {SINCE} → now\n")

    public_repos    = collect_public()
    private_summary = collect_private_orgs()
    pub_lang_rank   = public_lang_ranking(public_repos)

    stats = {
        "updated_at":     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "activity_since": SINCE,
        "public": {
            "repo_count": len(public_repos),
            "repos":      public_repos,
        },
        "private_orgs": private_summary,
        "languages_public_ranked": pub_lang_rank,
    }

    out_path = "stats.json"
    with open(out_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nWrote {out_path}")

    # Quick sanity print
    all_summary = private_summary.get("ALL", {})
    print(f"  Public repos:     {len(public_repos)}")
    print(f"  Private commits:  {all_summary.get('total_commits', 0)}")
    print(f"  Private LOC net:  +{all_summary.get('net_lines', 0)}")


if __name__ == "__main__":
    main()
