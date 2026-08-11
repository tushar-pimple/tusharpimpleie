#!/usr/bin/env python3
"""
Build Log — generates stats-light.svg / stats-dark.svg for the GitHub profile
README: a GitHub-native-styled contribution heatmap + repo cards, built from
commit history for AUTHOR_EMAIL across the repos in REPOS, pulled via the
GitHub REST API.

Run by .github/workflows/update-build-log.yml on a daily cron. Requires a
STATS_TOKEN env var: a GitHub PAT with read access to every repo in REPOS
(for the GainrsAI org repos, the token must be authorized for that org).
"""
import calendar
import datetime
import os
import sys

import requests

AUTHOR_EMAIL = "tushar.pimple@alumni.ie.edu"

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
    "light": {
        "canvas": "#ffffff",
        "border": "#d0d7de",
        "fg": "#1f2328",
        "fg_muted": "#656d76",
        "link": "#0969da",
        "card_bg": "#f6f8fa",
        "green": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    },
    "dark": {
        "canvas": "#0d1117",
        "border": "#30363d",
        "fg": "#e6edf3",
        "fg_muted": "#7d8590",
        "link": "#4493f8",
        "card_bg": "#161b22",
        "green": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
    },
}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
API = "https://api.github.com"


def fetch_commit_days(owner, repo, token):
    """Return a list of 'YYYY-MM-DD' strings, one per commit by AUTHOR_EMAIL."""
    days = []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    params = {"author": AUTHOR_EMAIL, "per_page": 100, "page": 1}
    url = f"{API}/repos/{owner}/{repo}/commits"
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 409:  # empty repo, no commits at all
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        days.extend(c["commit"]["author"]["date"][:10] for c in batch)
        if len(batch) < params["per_page"]:
            break
        params["page"] += 1
    return days


def sunday_on_or_before(d):
    return d - datetime.timedelta(days=(d.weekday() + 1) % 7)


def collect():
    token = os.environ.get("STATS_TOKEN")
    if not token:
        sys.exit("STATS_TOKEN env var not set")

    per_repo = {}
    all_days = []
    for owner, repo, name, lang in REPOS:
        days = fetch_commit_days(owner, repo, token)
        per_repo[name] = {"owner": owner, "lang": lang, "total": len(days)}
        all_days.extend(days)

    if not all_days:
        sys.exit("No commits found for any configured repo — check STATS_TOKEN scope/org access.")

    today = datetime.date.today()
    grid_start = sunday_on_or_before(today - datetime.timedelta(days=364))

    day_counts = {}
    for d in all_days:
        day = datetime.date.fromisoformat(d)
        if grid_start <= day <= today:
            day_counts[d] = day_counts.get(d, 0) + 1

    return per_repo, day_counts, grid_start, today


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def level(count, max_count):
    if count == 0:
        return 0
    if max_count <= 1:
        return 4
    frac = count / max_count
    return 1 if frac <= 0.25 else 2 if frac <= 0.5 else 3 if frac <= 0.75 else 4


def render_svg(per_repo, day_counts, grid_start, today, theme):
    p = PRIMER[theme]
    total_year = sum(day_counts.values())
    n_repos = len(per_repo)
    max_day = max(day_counts.values(), default=0)

    cell, gap = 10, 3
    step = cell + gap
    cols = (today - grid_start).days // 7 + 1
    left_label_w = 28
    pad = 20
    heat_w = cols * step - gap
    W = max(pad * 2 + left_label_w + heat_w, 760)

    head_y, sub_y, month_y, heat_top = 30, 50, 74, 84
    heat_h = 7 * step - gap
    legend_y = heat_top + heat_h + 26
    cards_top = legend_y + 22
    card_h = 62
    card_gap = 10
    card_w = (W - pad * 2 - card_gap * (n_repos - 1)) / n_repos
    H = cards_top + card_h + pad

    squares = []
    for offset in range((today - grid_start).days + 1):
        day = grid_start + datetime.timedelta(days=offset)
        col, row = offset // 7, (day.weekday() + 1) % 7
        cnt = day_counts.get(day.isoformat(), 0)
        x, y = pad + left_label_w + col * step, heat_top + row * step
        squares.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" '
            f'fill="{p["green"][level(cnt, max_day)]}"><title>{cnt} commits on {day.isoformat()}</title></rect>'
        )

    day_labels = [
        f'<text x="{pad}" y="{heat_top + row * step + cell}" font-size="9" fill="{p["fg_muted"]}">{lbl}</text>'
        for row, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri"))
    ]

    month_labels, last_month = [], None
    for col in range(cols):
        day = grid_start + datetime.timedelta(days=col * 7)
        if day.month != last_month:
            x = pad + left_label_w + col * step
            month_labels.append(
                f'<text x="{x}" y="{month_y}" font-size="9" fill="{p["fg_muted"]}">{calendar.month_abbr[day.month]}</text>'
            )
            last_month = day.month

    legend_w = 5 * (cell + 4) + 70
    lx = W - pad - legend_w
    legend = [f'<text x="{lx}" y="{legend_y + cell}" font-size="9" fill="{p["fg_muted"]}">Less</text>']
    for i, col_color in enumerate(p["green"]):
        legend.append(f'<rect x="{lx + 30 + i * (cell + 4)}" y="{legend_y}" width="{cell}" height="{cell}" rx="2" fill="{col_color}" />')
    legend.append(f'<text x="{lx + 30 + 5 * (cell + 4) + 6}" y="{legend_y + cell}" font-size="9" fill="{p["fg_muted"]}">More</text>')

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
     font-family="{FONT}" role="img" aria-label="{total_year} contributions in the last year across {n_repos} repositories">
  <rect width="{W}" height="{H}" fill="{p["canvas"]}" />
  <text x="{pad}" y="{head_y}" font-size="16" font-weight="600" fill="{p["fg"]}">{total_year} contributions in the last year</text>
  <text x="{pad}" y="{sub_y}" font-size="12" fill="{p["fg_muted"]}">Across {n_repos} repositories, including private org work not reflected above</text>
  {''.join(month_labels)}
  {''.join(day_labels)}
  {''.join(squares)}
  {''.join(legend)}
  {''.join(cards)}
</svg>'''


def main():
    per_repo, day_counts, grid_start, today = collect()
    for theme in ("light", "dark"):
        with open(f"stats-{theme}.svg", "w") as f:
            f.write(render_svg(per_repo, day_counts, grid_start, today, theme))
    total = sum(v for v in day_counts.values())
    print(f"Wrote stats-light.svg and stats-dark.svg — {total} contributions in the last year across {len(per_repo)} repos.")


if __name__ == "__main__":
    main()
