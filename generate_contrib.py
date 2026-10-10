"""Gera dist/contrib-bear.svg: um ursinho que passeia pelo gráfico de
contribuições comendo os quadradinhos (no estilo do "snake", mas com a
paleta marrom do README).

Uso:
    GH_USERNAME=... GITHUB_TOKEN=... python generate_contrib.py
    python generate_contrib.py --demo    # dados sintéticos, para preview local
"""
import datetime
import os
import random
import sys

from generate_stats import BG, BORDER, TITLE, TEXT, MUTED, gh_graphql

# ---------- Paleta das células (vazio -> mais contribuições) ----------
EMPTY = "#2A1F18"
LEVEL_COLORS = [EMPTY, "#5C3A21", "#8B5E3C", "#C08552", "#E3B47C"]
LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

# ---------- Urso ----------
FUR = "#C69C6D"
FUR_DARK = "#8B5E3C"
SNOUT = "#EDE0D4"
INK = BG

# ---------- Layout ----------
CELL, GAP = 11, 3
PITCH = CELL + GAP
PAD_X = 25
GRID_TOP = 62
MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
FONT = "Segoe UI, Helvetica, Arial, sans-serif"

# ---------- Tempo (segundos) ----------
STEP = 0.09          # tempo para andar uma célula
INTRO = 0.8          # urso aparece
HOLD = 1.2           # pausa depois de comer tudo
FADE_OUT = 0.5
REFILL = 2.4         # onda que "replanta" as contribuições
IDLE = 0.8
EAT = 0.35           # a célula "derrete" enquanto o urso come


def fetch_calendar(username: str, token: str):
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date weekday contributionLevel } }
          }
        }
      }
    }
    """
    cal = gh_graphql(query, {"login": username}, token)["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [
        [(d["weekday"], d["date"], LEVELS[d["contributionLevel"]]) for d in w["contributionDays"]]
        for w in cal["weeks"]
    ]
    return cal["totalContributions"], weeks


def demo_calendar(seed: int = 7):
    """Ano sintético com semanas mais/menos ativas, para testar o visual."""
    rng = random.Random(seed)
    today = datetime.date.today()
    start = today - datetime.timedelta(days=364)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)  # domingo
    weeks, total, day = [], 0, start
    while day <= today:
        week = []
        intensity = rng.random()
        for _ in range(7):
            if day > today:
                break
            weekday = (day.weekday() + 1) % 7
            p = 0.25 + 0.6 * intensity - (0.25 if weekday in (0, 6) else 0)
            level = 0
            if rng.random() < p:
                level = rng.choices([1, 2, 3, 4], weights=[4, 3, 2, 1])[0]
                total += level * rng.randint(1, 4)
            week.append((weekday, day.isoformat(), level))
            day += datetime.timedelta(days=1)
        weeks.append(week)
    return total, weeks


def plan_route(cells: dict, start: tuple):
    """Vizinho mais próximo (Manhattan), andando em L de célula em célula.

    Retorna a lista de posições visitadas e o passo em que cada célula foi comida.
    """
    remaining = {pos for pos, lvl in cells.items() if lvl > 0}
    pos, path, eaten_at = start, [start], {}
    while remaining:
        target = min(
            remaining,
            key=lambda c: (abs(c[0] - pos[0]) + abs(c[1] - pos[1]), -cells[c], c[0], c[1]),
        )
        x, y = pos
        while (x, y) != target:
            if x != target[0]:
                x += 1 if target[0] > x else -1
            else:
                y += 1 if target[1] > y else -1
            path.append((x, y))
            if (x, y) in remaining:
                remaining.discard((x, y))
                eaten_at[(x, y)] = len(path) - 1
        pos = target
    return path, eaten_at


def cell_center(x, y):
    return PAD_X + x * PITCH + CELL / 2, GRID_TOP + y * PITCH + CELL / 2


def pct(t, total):
    return f"{100 * t / total:.3f}%"


def bear_svg() -> str:
    return f'''
      <ellipse cx="0" cy="8" rx="6" ry="1.6" fill="#000" opacity="0.35"/>
      <circle cx="-5.2" cy="-5" r="2.9" fill="{FUR}" stroke="{INK}" stroke-width="1"/>
      <circle cx="5.2" cy="-5" r="2.9" fill="{FUR}" stroke="{INK}" stroke-width="1"/>
      <circle cx="-5.2" cy="-5" r="1.3" fill="{FUR_DARK}"/>
      <circle cx="5.2" cy="-5" r="1.3" fill="{FUR_DARK}"/>
      <circle cx="0" cy="0" r="6.8" fill="{FUR}" stroke="{INK}" stroke-width="1"/>
      <ellipse cx="0" cy="2.3" rx="3.4" ry="2.5" fill="{SNOUT}"/>
      <ellipse cx="0" cy="1.3" rx="1.3" ry="0.85" fill="{INK}"/>
      <circle cx="-2.5" cy="-1.6" r="0.95" fill="{INK}"/>
      <circle cx="2.5" cy="-1.6" r="0.95" fill="{INK}"/>'''


def render_svg(username: str, total: int, weeks) -> str:
    n_weeks = len(weeks)
    width = PAD_X * 2 + n_weeks * PITCH - GAP
    height = GRID_TOP + 7 * PITCH - GAP + 42

    cells = {}
    for x, week in enumerate(weeks):
        for weekday, _, level in week:
            cells[(x, weekday)] = level

    start = (-1, 3)
    path, eaten_at = plan_route(cells, start)
    steps = len(path) - 1

    t_travel0 = INTRO
    t_travel1 = t_travel0 + steps * STEP
    t_fade = t_travel1 + HOLD
    t_refill0 = t_fade + FADE_OUT
    t_refill1 = t_refill0 + REFILL
    T = t_refill1 + IDLE

    css, rects = [], []

    # Células: somem quando o urso passa e voltam numa onda da esquerda p/ direita.
    for (x, y), level in sorted(cells.items()):
        cx, cy = PAD_X + x * PITCH, GRID_TOP + y * PITCH
        color = LEVEL_COLORS[level]
        if (x, y) not in eaten_at:
            rects.append(f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" rx="2.5" fill="{color}"/>')
            continue
        t_eat = t_travel0 + eaten_at[(x, y)] * STEP
        t_back = t_refill0 + REFILL * 0.75 * x / max(1, n_weeks - 1)
        name = f"c{x}_{y}"
        css.append(
            f"@keyframes {name}{{0%,{pct(t_eat, T)}{{fill:{color}}}"
            f"{pct(t_eat + EAT, T)},{pct(t_back, T)}{{fill:{EMPTY}}}"
            f"{pct(t_back + REFILL * 0.25, T)},100%{{fill:{color}}}}}"
            f".{name}{{animation:{name} {T:.2f}s linear infinite}}"
        )
        rects.append(f'<rect class="{name}" x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" rx="2.5" fill="{color}"/>')

    # Urso: keyframes só nas curvas (o movimento linear entre elas é uniforme).
    corners = [0] + [
        i for i in range(1, steps)
        if (path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
        != (path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1])
    ] + [steps]
    sx, sy = cell_center(*path[0])
    frames = [f"0%{{transform:translate({sx:.1f}px,{sy:.1f}px)}}"]
    for i in corners:
        px, py = cell_center(*path[i])
        frames.append(f"{pct(t_travel0 + i * STEP, T)}{{transform:translate({px:.1f}px,{py:.1f}px)}}")
    frames.append(f"{pct(t_refill0, T)}{{transform:translate({px:.1f}px,{py:.1f}px)}}")
    frames.append(f"{pct(t_refill0 + 0.01, T)},100%{{transform:translate({sx:.1f}px,{sy:.1f}px)}}")
    css.append(f"@keyframes walk{{{''.join(frames)}}}.walk{{animation:walk {T:.2f}s linear infinite}}")
    css.append(
        f"@keyframes fade{{0%{{opacity:0}}{pct(INTRO * 0.8, T)},{pct(t_fade, T)}{{opacity:1}}"
        f"{pct(t_refill0, T)},100%{{opacity:0}}}}.fade{{animation:fade {T:.2f}s linear infinite}}"
    )
    css.append(
        f"@keyframes bob{{0%,100%{{transform:translateY(0) rotate(-4deg)}}50%{{transform:translateY(-1.2px) rotate(4deg)}}}}"
        f".bob{{animation:bob {STEP * 4:.2f}s ease-in-out infinite}}"
    )

    # Rótulos dos meses (primeira semana de cada mês).
    labels, last_month = [], None
    for x, week in enumerate(weeks):
        month = int(week[0][1][5:7])
        if month != last_month and x < n_weeks - 2:
            if last_month is not None or week[0][1][8:10] <= "07":
                labels.append(
                    f'<text x="{PAD_X + x * PITCH}" y="{GRID_TOP - 7}" fill="{MUTED}" font-size="9" font-family="{FONT}">{MONTHS[month - 1]}</text>'
                )
            last_month = month

    legend_y = GRID_TOP + 7 * PITCH - GAP + 18
    legend_x = width - PAD_X - 5 * PITCH - 28
    legend = [f'<text x="{legend_x - 6}" y="{legend_y + 9}" fill="{MUTED}" font-size="10" font-family="{FONT}" text-anchor="end">Menos</text>']
    for i, color in enumerate(LEVEL_COLORS):
        legend.append(f'<rect x="{legend_x + i * PITCH}" y="{legend_y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{color}"/>')
    legend.append(f'<text x="{legend_x + 5 * PITCH + 3}" y="{legend_y + 9}" fill="{MUTED}" font-size="10" font-family="{FONT}">Mais</text>')

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Gráfico de contribuições de {username}">
  <style>{"".join(css)}.bob{{transform-box:fill-box;transform-origin:center}}</style>
  <rect x="0.5" y="0.5" rx="12" width="{width - 1}" height="{height - 1}" fill="{BG}" stroke="{BORDER}" stroke-width="1"/>
  <text x="{PAD_X}" y="30" fill="{TITLE}" font-size="17" font-weight="700" font-family="{FONT}">Contribuições</text>
  <text x="{width - PAD_X}" y="30" fill="{TEXT}" font-size="12" font-family="{FONT}" text-anchor="end">{total:,} no último ano</text>
  {"".join(labels)}
  {"".join(rects)}
  {"".join(legend)}
  <g class="walk"><g class="fade" transform="scale(1.2)"><g class="bob">{bear_svg()}
  </g></g></g>
</svg>'''


def main():
    username = os.environ.get("GH_USERNAME", "TiagoSBittencourt")
    if "--demo" in sys.argv:
        total, weeks = demo_calendar()
    else:
        token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("Defina GH_PAT (ou GITHUB_TOKEN), ou rode com --demo.", file=sys.stderr)
            sys.exit(1)
        total, weeks = fetch_calendar(username, token)

    os.makedirs("dist", exist_ok=True)
    with open("dist/contrib-bear.svg", "w", encoding="utf-8") as f:
        f.write(render_svg(username, total, weeks))
    print("Gerado: dist/contrib-bear.svg")


if __name__ == "__main__":
    main()
