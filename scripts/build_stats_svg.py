#!/usr/bin/env python3
"""
Build Log — generates stats-light.svg / stats-dark.svg for the GitHub profile
README: repo cards styled like GitHub's own "Popular repositories" boxes,
plus a line explaining why GitHub's public contribution graph (elsewhere on
the same page) shows a lower number than this — instead of duplicating that
graph, which is confusing when the two totals disagree.

Run by .github/workflows/update-build-log.yml on a daily cron. Requires a
STATS_TOKEN env var: a GitHub PAT with read access to every repo in REPOS
(for the GainrsAI org repos, the token must be authorized for that org).
"""
import os
import sys
from urllib.parse import parse_qs, urlparse

import requests

AUTHOR_EMAIL = "tushar.pimple@alumni.ie.edu"
USERNAME = "tusharpimpleie"

# (owner, repo, display name, primary language — drives the GitHub-style language dot)
REPOS = [
    ("GainrsAI", "gainrs-core-app", "gainrs-core-app", "Python"),
    ("GainrsAI", "dashabord.gainrs.ai", "dashabord.gainrs.ai", "TypeScript"),
    ("tusharpimpleie", "research_ideas_trader", "research_ideas_trader", "Python"),
    ("tusharpimpleie", "historical_data", "historical_data", "Python"),
]

# GitHub's actual language-dot colors (github-linguist).
LANG_COLORS = {"Python": "#3572A5", "TypeScript": "#3178c6"}

# GitHub Primer design tokens — matched to the real profile page so this
# blends into the surrounding chrome instead of reading as a separate widget.
PRIMER = {
    "light": {"canvas": "#ffffff", "border": "#d0d7de", "fg": "#1f2328", "fg_muted": "#656d76", "link": "#0969da", "card_bg": "#f6f8fa"},
    "dark":  {"canvas": "#0d1117", "border": "#30363d", "fg": "#e6edf3", "fg_muted": "#7d8590", "link": "#4493f8", "card_bg": "#161b22"},
}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
API = "https://api.github.com"


def count_commits(owner, repo, token):
    """Total commit count by AUTHOR_EMAIL, via the Link header's last page (1 request)."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    params = {"author": AUTHOR_EMAIL, "per_page": 1}
    url = f"{API}/repos/{owner}/{repo}/commits"
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    if resp.status_code == 409:  # empty repo, no commits at all
        return 0
    resp.raise_for_status()
    if "last" in resp.links:
        last_page = parse_qs(urlparse(resp.links["last"]["url"]).query)["page"][0]
        return int(last_page)
    return len(resp.json())


def fetch_public_total(username, token):
    """The number GitHub's own public contribution graph shows for this user
    right now — fetched live so the comparison line never goes stale or
    contradicts the real graph elsewhere on the page. Returns None on any
    failure (e.g. token lacks scope) so the caller can fall back gracefully.
    """
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection { contributionCalendar { totalContributions } }
      }
    }"""
    try:
        resp = requests.post(
            f"{API}/graphql",
            json={"query": query, "variables": {"login": username}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    except Exception:
        return None


def collect():
    token = os.environ.get("STATS_TOKEN")
    if not token:
        sys.exit("STATS_TOKEN env var not set")

    per_repo = {}
    for owner, repo, name, lang in REPOS:
        per_repo[name] = {"owner": owner, "lang": lang, "total": count_commits(owner, repo, token)}

    if not any(info["total"] for info in per_repo.values()):
        sys.exit("No commits found for any configured repo — check STATS_TOKEN scope/org access.")

    public_total = fetch_public_total(USERNAME, token)
    return per_repo, public_total


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(per_repo, public_total, theme):
    p = PRIMER[theme]
    total = sum(info["total"] for info in per_repo.values())
    n_repos = len(per_repo)

    W, pad = 760, 20
    head_y, sub_y, cards_top = 30, 52, 74
    card_h, card_gap = 62, 10
    card_w = (W - pad * 2 - card_gap * (n_repos - 1)) / n_repos
    note_y = cards_top + card_h + 26
    H = note_y + 14

    if public_total is not None:
        sub = f"GitHub's public graph on this page currently shows {public_total} — commits to the private GainrsAI repos aren't counted there."
    else:
        sub = "GitHub's public graph on this page runs lower — commits to the private GainrsAI repos aren't counted there."

    cards, x = [], pad
    for name, info in per_repo.items():
        lang = info["lang"]
        cards.append(f'<rect x="{x:.1f}" y="{cards_top}" width="{card_w:.1f}" height="{card_h}" rx="6" fill="{p["card_bg"]}" stroke="{p["border"]}" />')
        cards.append(f'<text x="{x + 12:.1f}" y="{cards_top + 24}" font-size="13" font-weight="600" fill="{p["link"]}">{esc(name)}</text>')
        cards.append(f'<circle cx="{x + 16:.1f}" cy="{cards_top + 44}" r="4" fill="{LANG_COLORS.get(lang, "#8b949e")}" />')
        cards.append(f'<text x="{x + 26:.1f}" y="{cards_top + 47}" font-size="11" fill="{p["fg_muted"]}">{esc(lang)}</text>')
        cards.append(f'<text x="{x + card_w - 12:.1f}" y="{cards_top + 47}" font-size="11" fill="{p["fg_muted"]}" text-anchor="end">{info["total"]} commits</text>')
        x += card_w + card_gap

    return f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"
     font-family="{FONT}" role="img" aria-label="{total} commits across {n_repos} repositories">
  <rect width="{W}" height="{H}" fill="{p["canvas"]}" />
  <text x="{pad}" y="{head_y}" font-size="16" font-weight="600" fill="{p["fg"]}">{total} commits across {n_repos} repositories</text>
  <text x="{pad}" y="{sub_y}" font-size="12" fill="{p["fg_muted"]}">{esc(sub)}</text>
  {''.join(cards)}
  <text x="{pad}" y="{note_y}" font-size="9" fill="{p["fg_muted"]}">Auto-synced daily via GitHub Actions</text>
</svg>'''


def main():
    per_repo, public_total = collect()
    for theme in ("light", "dark"):
        with open(f"stats-{theme}.svg", "w") as f:
            f.write(render_svg(per_repo, public_total, theme))
    total = sum(i["total"] for i in per_repo.values())
    print(f"Wrote stats-light.svg and stats-dark.svg — {total} commits across {len(per_repo)} repos (public graph: {public_total}).")


if __name__ == "__main__":
    main()
