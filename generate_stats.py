import os
import sys
import requests

# ---------- Paleta (marrom, mesma do README) ----------
BG = "#1a1410"       # fundo escuro amarronzado
BORDER = "#5C3A21"   # borda marrom média
TITLE = "#C69C6D"    # título em marrom claro (destaque)
TEXT = "#EDE0D4"     # texto off-white quente
MUTED = "#9C7B5A"    # texto secundário marrom acinzentado
# tons do mais claro ao mais escuro, base no #8B5E3C do README
BAR_SHADES = ["#D9A56B", "#C08552", "#A66E3E", "#8B5E3C", "#6E472B", "#5C3A21"]

GRAPHQL_URL = "https://api.github.com/graphql"

# Limiares para os selos de "Conquistas" (trophies).
THRESHOLDS = {
    "total_commits": 1000,
    "total_prs": 50,
    "total_reviews": 50,
    "total_issues": 25,
    "total_stars": 50,
    "followers": 50,
}
TIERS = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
TIER_CUTOFFS = [0.90, 0.80, 0.65, 0.50, 0.40, 0.30, 0.20, 0.10, 0.0]


def letter_grade(ratio: float):
    ratio = max(0.0, min(1.0, ratio))
    for tier, cutoff in zip(TIERS, TIER_CUTOFFS):
        if ratio >= cutoff:
            idx = TIERS.index(tier)
            color = BAR_SHADES[min(idx, len(BAR_SHADES) - 1)]
            return tier, color
    return "C", BAR_SHADES[-1]


def gh_graphql(query: str, variables: dict, token: str) -> dict:
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def fetch_profile(username: str, token: str) -> dict:
    query = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes { stargazerCount }
        }
      }
    }
    """
    data = gh_graphql(query, {"login": username}, token)["user"]

    import datetime
    created = datetime.datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
    now = datetime.datetime.now(datetime.timezone.utc)

    total_commits = 0
    total_prs = 0
    total_issues = 0
    total_reviews = 0

    year_query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalPullRequestReviewContributions
        }
      }
    }
    """
    year = created.year
    while year <= now.year:
        frm = max(created, datetime.datetime(year, 1, 1, tzinfo=datetime.timezone.utc))
        to = min(now, datetime.datetime(year, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc))
        yr = gh_graphql(
            year_query,
            {"login": username, "from": frm.isoformat(), "to": to.isoformat()},
            token,
        )["user"]["contributionsCollection"]
        total_commits += yr["totalCommitContributions"]
        total_prs += yr["totalPullRequestContributions"]
        total_issues += yr["totalIssueContributions"]
        total_reviews += yr["totalPullRequestReviewContributions"]
        year += 1

    repos = data["repositories"]["nodes"]
    total_stars = sum(r["stargazerCount"] for r in repos)

    return {
        "followers": data["followers"]["totalCount"],
        "total_stars": total_stars,
        "total_commits": total_commits,
        "total_prs": total_prs,
        "total_issues": total_issues,
        "total_reviews": total_reviews,
    }


def render_trophies_svg(username: str, s: dict) -> str:
    categories = [
        ("Estrelas", "total_stars"),
        ("Commits", "total_commits"),
        ("Pull Reqs", "total_prs"),
        ("Issues", "total_issues"),
        ("Revisões", "total_reviews"),
        ("Seguidores", "followers"),
    ]

    box_w, box_h, gap, top_pad = 72, 90, 8, 55
    width = len(categories) * box_w + (len(categories) - 1) * gap + 50
    height = top_pad + box_h + 20

    body = []
    for i, (label, key) in enumerate(categories):
        ratio = min(1.0, s[key] / THRESHOLDS[key])
        tier, color = letter_grade(ratio)
        x = 25 + i * (box_w + gap)
        y = top_pad
        body.append(f'''
        <g transform="translate({x}, {y})">
          <rect x="0" y="0" width="{box_w}" height="{box_h}" rx="10" fill="none" stroke="{color}" stroke-width="1.5" opacity="0.7"/>
          <text x="{box_w/2}" y="34" fill="{color}" font-size="22" font-weight="800" font-family="Segoe UI, Helvetica, Arial, sans-serif" text-anchor="middle">{tier}</text>
          <text x="{box_w/2}" y="56" fill="{TEXT}" font-size="11" font-family="Segoe UI, Helvetica, Arial, sans-serif" text-anchor="middle">{label}</text>
          <text x="{box_w/2}" y="74" fill="{MUTED}" font-size="10" font-family="Segoe UI, Helvetica, Arial, sans-serif" text-anchor="middle">{s[key]:,}</text>
        </g>''')

    svg = f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Conquistas de {username}">
  <rect x="0.5" y="0.5" rx="12" width="{width - 1}" height="{height - 1}" fill="{BG}" stroke="{BORDER}" stroke-width="1"/>
  <text x="25" y="30" fill="{TITLE}" font-size="17" font-weight="700" font-family="Segoe UI, Helvetica, Arial, sans-serif">Conquistas</text>
  {''.join(body)}
</svg>'''
    return svg


def main():
    username = os.environ.get("GH_USERNAME")
    token = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    if not username or not token:
        print("Defina GH_USERNAME e GH_PAT (ou GITHUB_TOKEN) como variaveis de ambiente.", file=sys.stderr)
        sys.exit(1)

    stats = fetch_profile(username, token)

    os.makedirs("dist", exist_ok=True)
    with open("dist/trophies.svg", "w", encoding="utf-8") as f:
        f.write(render_trophies_svg(username, stats))

    print("Gerado: dist/trophies.svg")


if __name__ == "__main__":
    main()
