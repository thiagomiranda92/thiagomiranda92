"""Gera profile/stats.svg com os dados públicos do perfil no GitHub."""

import json
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

OUTPUT = Path("profile/stats.svg")

QUERY = """
query ($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

WIDTH = 840
PADDING = 24
CELL = 12
STEP = 15
HEATMAP_TOP = 176

BACKGROUND = "#050505"
BORDER = "#1C262C"
ACCENT = "#00D9FF"
TEXT = "#E6EDF3"
MUTED = "#8B98A5"
LEVELS = ["#12191D", "#064B5C", "#0A7A94", "#00A8C8", ACCENT]
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
SANS = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Consolas, Menlo, monospace"


def fetch_data(login, token):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])

    user = payload["data"]["user"]
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [
        {"date": day["date"], "count": day["contributionCount"]}
        for week in weeks
        for day in week["contributionDays"]
    ]

    languages = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            entry = languages.setdefault(
                name, {"name": name, "size": 0, "color": edge["node"]["color"] or MUTED}
            )
            entry["size"] += edge["size"]
    return days, list(languages.values())


def streaks(days):
    """Retorna (atual, melhor); hoje sem contribuição ainda não quebra a sequência."""
    best = run = 0
    for day in days:
        run = run + 1 if day["count"] else 0
        best = max(best, run)

    pending = days[:-1] if days and not days[-1]["count"] else days
    current = 0
    for day in reversed(pending):
        if not day["count"]:
            break
        current += 1
    return current, best


def level(count, peak):
    if not count:
        return 0
    return min(4, 1 + (count - 1) * 4 // max(peak, 1))


def stat(x, value, unit, label):
    suffix = f'<tspan class="unit" dx="5">{unit}</tspan>' if unit else ""
    return (
        f'<text x="{x}" y="112" class="value">{value}{suffix}</text>'
        f'<text x="{x}" y="132" class="label">{label}</text>'
    )


def days_unit(value):
    return "dia" if value == 1 else "dias"


def heatmap(days):
    peak = max((day["count"] for day in days), default=0)
    first = date.fromisoformat(days[0]["date"])
    origin = first - timedelta(days=(first.weekday() + 1) % 7)

    cells, labels = [], []
    last_month, last_label_x = None, -100
    for day in days:
        current = date.fromisoformat(day["date"])
        column = (current - origin).days // 7
        row = (current.weekday() + 1) % 7
        x = PADDING + column * STEP
        y = HEATMAP_TOP + row * STEP

        if row == 0 or day is days[0]:
            if current.month != last_month:
                last_month = current.month
                if x - last_label_x >= 30:
                    labels.append(f'<text x="{x}" y="{HEATMAP_TOP - 8}" class="month">{MONTHS[current.month - 1]}</text>')
                    last_label_x = x

        fill = LEVELS[level(day["count"], peak)]
        delay = column * 18
        cells.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="{fill}" '
            f'style="animation-delay:{delay}ms"/>'
        )
    return "".join(labels) + "".join(cells)


def language_bar(languages, top):
    ranked = sorted(languages, key=lambda item: item["size"], reverse=True)
    total = sum(item["size"] for item in ranked)
    shown = ranked[:5]
    rest = total - sum(item["size"] for item in shown)
    if rest > 0:
        shown.append({"name": "Outras", "size": rest, "color": MUTED})

    usable = WIDTH - 2 * PADDING
    parts = [f'<clipPath id="bar"><rect x="{PADDING}" y="{top}" width="{usable}" height="8" rx="4"/></clipPath><g clip-path="url(#bar)">']
    legend = []
    x = float(PADDING)
    legend_x = PADDING
    for item in shown:
        share = item["size"] / total
        width = usable * share
        parts.append(f'<rect x="{x:.1f}" y="{top}" width="{width:.1f}" height="8" fill="{item["color"]}"/>')
        x += width

        name = escape(item["name"])
        percent = f"{share * 100:.0f}%" if share >= 0.01 else "&lt;1%"
        legend.append(
            f'<circle cx="{legend_x + 4}" cy="{top + 26}" r="4" fill="{item["color"]}"/>'
            f'<text x="{legend_x + 14}" y="{top + 30}" class="label">{name} <tspan class="percent">{percent}</tspan></text>'
        )
        legend_x += 14 + int(len(item["name"]) * 7.2) + 58
    parts.append("</g>")
    return "".join(parts) + "".join(legend)


def render(login, days, languages, today):
    total = sum(day["count"] for day in days)
    active = sum(1 for day in days if day["count"])
    current, best = streaks(days)

    bar_top = HEATMAP_TOP + 7 * STEP + 16
    height = bar_top + 54 if languages else bar_top + 8
    bar = language_bar(languages, bar_top) if languages else ""
    summary = f"{total} contribuições e {active} dias ativos nos últimos 12 meses; melhor sequência de {best} dias."

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="title desc">
<title id="title">Estatísticas do GitHub de {escape(login)}</title>
<desc id="desc">{summary}</desc>
<style>
text {{ font-family: {SANS}; }}
.prompt {{ font: 600 14px {MONO}; fill: {ACCENT}; }}
.meta {{ font: 12px {MONO}; fill: {MUTED}; }}
.value {{ font: 700 36px {MONO}; fill: {TEXT}; }}
.unit {{ font: 400 14px {MONO}; fill: {MUTED}; }}
.label {{ font-size: 12px; fill: {MUTED}; }}
.percent {{ fill: {TEXT}; }}
.month {{ font-size: 11px; fill: {MUTED}; }}
rect[style] {{ animation: appear .4s ease-out both; }}
@keyframes appear {{ from {{ opacity: 0; }} }}
@media (prefers-reduced-motion: reduce) {{ rect[style] {{ animation: none; }} }}
</style>
<rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="14" fill="{BACKGROUND}" stroke="{BORDER}"/>
<text x="{PADDING}" y="42" class="prompt">~/{escape(login)} $ git log --last-year</text>
<text x="{WIDTH - PADDING}" y="42" class="meta" text-anchor="end">atualizado em {today:%d/%m/%Y}</text>
{stat(PADDING, total, "", "contribuições")}
{stat(PADDING + 198, active, days_unit(active), "ativos no ano")}
{stat(PADDING + 396, current, days_unit(current), "sequência atual")}
{stat(PADDING + 594, best, days_unit(best), "melhor sequência")}
{heatmap(days)}
{bar}
</svg>
"""


def main():
    login = os.environ["GITHUB_REPOSITORY_OWNER"]
    days, languages = fetch_data(login, os.environ["GITHUB_TOKEN"])
    today = datetime.now(timezone(timedelta(hours=-3))).date()
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(render(login, days, languages, today), encoding="utf-8")


if __name__ == "__main__":
    main()
