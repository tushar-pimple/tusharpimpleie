#!/usr/bin/env python3
"""
Build Log — generates stats-light.svg / stats-dark.svg for the GitHub profile
README, by pulling commit history for AUTHOR_EMAIL across the repos in REPOS
via the GitHub REST API.

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

# (owner, repo, display name, color key into COLORS)
REPOS = [
    ("GainrsAI", "gainrs-core-app", "gainrs-core-app", "accent"),
    ("GainrsAI", "dashabord.gainrs.ai", "dashabord.gainrs.ai", "teal"),
    ("tusharpimpleie", "research_ideas_trader", "research_ideas_trader", "plum"),
    ("tusharpimpleie", "historical_data", "historical_data", "sand"),
]

COLORS = {
    "light": {
        "accent": "#A65A25", "teal": "#2F6B5F", "plum": "#6D4160", "sand": "#8C733A",
        "paper": "#EDF0EA", "ink": "#1A1F1B", "ink_dim": "#5B615C", "line": "#C7CCC1",
    },
    "dark": {
        "accent": "#E0964F", "teal": "#62B39F", "plum": "#C083AE", "sand": "#CBAE66",
        "paper": "#14181A", "ink": "#E9ECE4", "ink_dim": "#9BA39C", "line": "#2B3234",
    },
}

API = "https://api.github.com"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"


def fetch_commit_months(owner, repo, token):
    """Return a list of 'YYYY-MM' strings, one per commit by AUTHOR_EMAIL."""
    months = []
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
        months.extend(c["commit"]["author"]["date"][:7] for c in batch)
        if len(batch) < params["per_page"]:
            break
        params["page"] += 1
    return months


def month_range(start_ym, end_ym):
    (y, m), (ey, em) = start_ym, end_ym
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            m, y = 1, y + 1
    return out


def collect():
    token = os.environ.get("STATS_TOKEN")
    if not token:
        sys.exit("STATS_TOKEN env var not set")

    per_repo = {}
    seen_months = set()
    for owner, repo, name, color_key in REPOS:
        months = fetch_commit_months(owner, repo, token)
        per_repo[name] = {"owner": owner, "color_key": color_key, "months": months, "total": len(months)}
        seen_months.update(months)

    if not seen_months:
        sys.exit("No commits found for any configured repo — check STATS_TOKEN scope/org access.")

    start = tuple(int(x) for x in min(seen_months).split("-"))
    today = datetime.date.today()
    months = month_range(start, (today.year, today.month))

    monthly = {name: {mo: 0 for mo in months} for name in per_repo}
    for name, info in per_repo.items():
        for mo in info["months"]:
            if mo in monthly[name]:
                monthly[name][mo] += 1

    return per_repo, monthly, months


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(per_repo, monthly, months, theme):
    c = COLORS[theme]
    W, H = 820, 480
    pad = 40
    total = sum(info["total"] for info in per_repo.values())
    n_repos = len(per_repo)
    today_str = datetime.date.today().strftime("%d %b %Y")

    chart_x, chart_y, chart_w, chart_h = pad, 190, W - pad * 2, 130
    n = len(months)
    col_w = chart_w / n
    gap = 6
    bar_w = col_w - gap
    max_total = max((sum(monthly[name][mo] for name in monthly) for mo in months), default=1) or 1

    bars, labels = [], []
    for i, mo in enumerate(months):
        x = chart_x + i * col_w + gap / 2
        y_cursor = chart_y + chart_h
        month_total = 0
        for name, info in per_repo.items():
            v = monthly[name][mo]
            month_total += v
            if v == 0:
                continue
            h = (v / max_total) * chart_h
            y_cursor -= h
            bars.append(
                f'<rect x="{x:.1f}" y="{y_cursor:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                f'fill="{c[info["color_key"]]}" />'
            )
        month_label = calendar.month_abbr[int(mo.split("-")[1])]
        if mo == months[-1]:
            month_label += "*"
        labels.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{chart_y + chart_h + 18}" font-family="{MONO}" '
            f'font-size="10" fill="{c["ink_dim"]}" text-anchor="middle">{esc(month_label)}</text>'
        )
        labels.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{chart_y + chart_h + 32}" font-family="{MONO}" '
            f'font-size="9" font-weight="600" fill="{c["ink"]}" text-anchor="middle">{month_total}</text>'
        )

    legend, lx, ly = [], pad, 440
    for name, info in per_repo.items():
        legend.append(f'<rect x="{lx}" y="{ly - 9}" width="9" height="9" fill="{c[info["color_key"]]}" />')
        legend.append(
            f'<text x="{lx + 14}" y="{ly}" font-family="{MONO}" font-size="11" fill="{c["ink_dim"]}">'
            f'{esc(name)} <tspan font-weight="700" fill="{c["ink"]}">{info["total"]}</tspan></text>'
        )
        lx += 30 + len(name) * 6.4 + len(str(info["total"])) * 7

    return f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"
     role="img" aria-label="Build log: {total} commits across {n_repos} repos">
  <rect width="{W}" height="{H}" fill="{c["paper"]}" />
  <text x="{pad}" y="52" font-family="{MONO}" font-size="11" letter-spacing="2" fill="{c["ink_dim"]}">
    BUILD LOG &#8212; GIT HISTORY, NOT A R&#201;SUM&#201;
  </text>
  <text x="{pad}" y="98" font-family="{MONO}" font-size="34" font-weight="700" fill="{c["ink"]}">
    <tspan fill="{c["accent"]}">{total}</tspan> commits across <tspan fill="{c["accent"]}">{n_repos}</tspan> repos
  </text>
  <text x="{pad}" y="128" font-family="{MONO}" font-size="12" fill="{c["ink_dim"]}">
    tushar.pimple@alumni.ie.edu &#183; updated {esc(today_str)}
  </text>
  <line x1="{pad}" y1="150" x2="{W - pad}" y2="150" stroke="{c["line"]}" stroke-width="1" />
  {''.join(bars)}
  {''.join(labels)}
  <text x="{pad}" y="{chart_y + chart_h + 50}" font-family="{MONO}" font-size="9" fill="{c["ink_dim"]}">
    *current month, partial
  </text>
  <line x1="{pad}" y1="410" x2="{W - pad}" y2="410" stroke="{c["line"]}" stroke-width="1" />
  {''.join(legend)}
</svg>'''


def main():
    per_repo, monthly, months = collect()
    for theme in ("light", "dark"):
        with open(f"stats-{theme}.svg", "w") as f:
            f.write(render_svg(per_repo, monthly, months, theme))
    total = sum(i["total"] for i in per_repo.values())
    print(f"Wrote stats-light.svg and stats-dark.svg — {total} total commits across {len(per_repo)} repos.")


if __name__ == "__main__":
    main()
