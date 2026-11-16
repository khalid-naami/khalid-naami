#!/usr/bin/env python3
"""
Generates custom dark/light SVGs for Khalid Naami's GitHub Profile README:
  1. quant_dark.svg / quant_light.svg       ($KHALID Quant Terminal: OHLC Candles, Portfolio Telemetry, Ticker Tape)
  2. vol_surface_dark.svg / vol_surface_light.svg (Animated 3D Isometric Volatility Surface + GEX Pulse)
  3. osint_hud_dark.svg / osint_hud_light.svg   (Live OSINT / Macro Signal Radar HUD: SPY, SPX, GOLD, BTC-USD, Code Pulse)

Uses Python standard library only.
"""

from __future__ import annotations

import csv
import datetime
import html
import io
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape


GRAPHQL_URL = "https://api.github.com/graphql"
DEFAULT_USER = "khalid-naami"

FALLBACK_LANG_COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "Rust": "#DEA584",
    "Dart": "#00B4AB",
    "Java": "#B07219",
    "HTML": "#E34C26",
    "CSS": "#563D7C",
    "Shell": "#89E051",
    "Jupyter Notebook": "#DA5B0B",
}

LANG_DISPLAY_NAMES = {
    "Jupyter Notebook": "Jupyter",
    "Objective-C++": "Obj-C++",
    "Objective-C": "Obj-C",
}

THEMES = {
    "dark": {
        "bg_outer": "#0d1117",
        "bg_panel": "#161b22",
        "border": "#30363d",
        "grid": "#21262d",
        "text_primary": "#f0f6fc",
        "text_secondary": "#8b949e",
        "text_muted": "#6e7681",
        "accent": "#7c6ef6",
        "accent_pill_bg": "#27214d",
        "accent_pill_text": "#c4b5fd",
        "bull": "#3fb950",
        "bull_soft": "#238636",
        "bear": "#f85149",
        "bear_soft": "#da3633",
        "warn": "#d29922",
        "ma_line": "#a371f7",
        "vol_cyan": "#58a6ff",
        "ticker_bg": "#0b0f14",
    },
    "light": {
        "bg_outer": "#ffffff",
        "bg_panel": "#f6f8fa",
        "border": "#d0d7de",
        "grid": "#eaeef2",
        "text_primary": "#1f2328",
        "text_secondary": "#57606a",
        "text_muted": "#6e7781",
        "accent": "#6A5ACD",
        "accent_pill_bg": "#eeecfb",
        "accent_pill_text": "#5544b8",
        "bull": "#1a7f37",
        "bull_soft": "#2da44e",
        "bear": "#cf222e",
        "bear_soft": "#e5534b",
        "warn": "#9a6700",
        "ma_line": "#6A5ACD",
        "vol_cyan": "#0969da",
        "ticker_bg": "#f0f3f6",
    },
}


def http_get_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "application/json,text/csv,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def graphql_request(query: str, variables: dict, token: str) -> dict:
    """Executes a GitHub GraphQL v4 request using stdlib urllib."""
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "khalid-naami-quant-profile",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "errors" in payload and not payload.get("data"):
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]


def extract_blog_titles(readme_path: str = "README.md", limit: int = 4) -> list[str]:
    """Reads latest blog article titles from README.md blog table."""
    if not os.path.exists(readme_path):
        return []
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []

    matches = re.findall(
        r'<a\s+href="https://khalidnaami\.com/blog/[^"]+">\s*([^<]+?)\s*</a>',
        content,
        flags=re.DOTALL,
    )
    titles = []
    for raw in matches:
        clean = " ".join(html.unescape(raw).split())
        clean = re.sub(r"^[^A-Za-z0-9$]+", "", clean).strip()
        if clean:
            titles.append(clean)
        if len(titles) >= limit:
            break
    return titles


def fetch_github_stats(username: str, token: str) -> dict:
    """Fetches 1-year contribution calendar, repositories, stars, followers, languages, and recent public projects."""
    query_user = """
    query($login: String!, $cursor: String, $includeRecent: Boolean!) {
      user(login: $login) {
        followers {
          totalCount
        }
        recentProjects: repositories(
          first: 8
          ownerAffiliations: OWNER
          isFork: false
          privacy: PUBLIC
          orderBy: {field: PUSHED_AT, direction: DESC}
        ) @include(if: $includeRecent) {
          nodes {
            name
            stargazerCount
          }
        }
        repositories(
          first: 100
          after: $cursor
          ownerAffiliations: OWNER
          isFork: false
          orderBy: {field: STARGAZERS, direction: DESC}
        ) {
          totalCount
          pageInfo {
            endCursor
            hasNextPage
          }
          nodes {
            name
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node {
                  name
                  color
                }
              }
            }
          }
        }
        contributionsCollection {
          totalCommitContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
      }
    }
    """
    data = graphql_request(
        query_user,
        {"login": username, "cursor": None, "includeRecent": True},
        token,
    )
    user = data["user"]
    repos_conn = user["repositories"]
    repo_nodes = list(repos_conn["nodes"])

    recent_projects = []
    for r in user.get("recentProjects", {}).get("nodes", []):
        rname = r.get("name", "")
        if rname and rname.lower() != username.lower():
            recent_projects.append({"name": rname, "stars": int(r.get("stargazerCount", 0))})
        if len(recent_projects) >= 4:
            break

    while repos_conn["pageInfo"]["hasNextPage"]:
        next_data = graphql_request(
            query_user,
            {"login": username, "cursor": repos_conn["pageInfo"]["endCursor"], "includeRecent": False},
            token,
        )
        repos_conn = next_data["user"]["repositories"]
        repo_nodes.extend(repos_conn["nodes"])

    total_repos = repos_conn["totalCount"]
    total_stars = sum(r.get("stargazerCount", 0) for r in repo_nodes)
    followers = user["followers"]["totalCount"]

    lang_totals: dict[str, int] = {}
    lang_colors: dict[str, str] = {}
    for repo in repo_nodes:
        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            size = int(edge["size"])
            color = edge["node"].get("color") or FALLBACK_LANG_COLORS.get(name, "#8b949e")
            lang_totals[name] = lang_totals.get(name, 0) + size
            lang_colors[name] = color

    contrib = user["contributionsCollection"]
    calendar = contrib["contributionCalendar"]
    total_commits = int(contrib["totalCommitContributions"]) + int(contrib["restrictedContributionsCount"])
    total_contributions = int(calendar["totalContributions"])

    weeks = []
    days_flat = []
    for w in calendar["weeks"]:
        day_counts = [int(d["contributionCount"]) for d in w["contributionDays"]]
        weeks.append(day_counts)
        days_flat.extend(w["contributionDays"])

    longest_streak = 0
    running = 0
    active_days = 0
    for d in days_flat:
        c = int(d["contributionCount"])
        if c > 0:
            active_days += 1
            running += 1
            longest_streak = max(longest_streak, running)
        else:
            running = 0

    current_streak = 0
    rev_days = list(reversed(days_flat))
    if rev_days and int(rev_days[0]["contributionCount"]) == 0:
        rev_days = rev_days[1:]
    for d in rev_days:
        if int(d["contributionCount"]) > 0:
            current_streak += 1
        else:
            break

    last7_days = [int(d["contributionCount"]) for d in days_flat[-7:]]

    total_bytes = sum(lang_totals.values())
    sorted_langs = sorted(lang_totals.items(), key=lambda kv: kv[1], reverse=True)
    top_langs = []
    if total_bytes > 0:
        top4 = sorted_langs[:4]
        used_bytes = sum(sz for _, sz in top4)
        for name, sz in top4:
            top_langs.append(
                {
                    "name": LANG_DISPLAY_NAMES.get(name, name),
                    "pct": round((sz / total_bytes) * 100.0, 1),
                    "color": lang_colors.get(name, "#8b949e"),
                }
            )
        if len(sorted_langs) > 4 and total_bytes > used_bytes:
            top_langs.append(
                {
                    "name": "Other",
                    "pct": round(((total_bytes - used_bytes) / total_bytes) * 100.0, 1),
                    "color": "#8b949e",
                }
            )

    return {
        "username": username,
        "synced_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "live": True,
        "total_commits": total_commits,
        "total_contributions": total_contributions,
        "total_repos": total_repos,
        "total_stars": total_stars,
        "followers": followers,
        "active_days": active_days,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "weeks": weeks,
        "last7_days": last7_days,
        "languages": top_langs,
        "recent_projects": recent_projects,
        "blog_titles": extract_blog_titles(),
    }


def fetch_yahoo_ticker(symbol: str) -> dict | None:
    """Fetches latest price, 1d % change, and 10d closes from Yahoo Finance chart API."""
    encoded = urllib.parse.quote(symbol, safe="")
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{encoded}?range=1mo&interval=1d"
        try:
            payload = json.loads(http_get_text(url, timeout=12))
            res = payload["chart"]["result"][0]
            meta = res["meta"]
            raw_closes = res["indicators"]["quote"][0].get("close") or []
            closes = [float(x) for x in raw_closes if x is not None][-10:]
            price = meta.get("regularMarketPrice")
            if price is None and closes:
                price = closes[-1]
            if price is None:
                continue
            price = float(price)
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if len(closes) >= 2:
                prev = closes[-2]
            pct = ((price - float(prev)) / float(prev)) * 100.0 if prev else 0.0
            return {"price": price, "pct": pct, "history": closes}
        except Exception:
            continue
    return None


def fetch_stooq_ticker(symbol: str) -> dict | None:
    """Fallback daily closes from Stooq CSV for symbols like spy.us, ^spx, xauusd."""
    try:
        encoded = urllib.parse.quote(symbol, safe="")
        raw = http_get_text(f"https://stooq.com/q/d/l/?s={encoded}&i=d", timeout=12)
        rows = list(csv.DictReader(io.StringIO(raw)))
        closes = [float(r["Close"]) for r in rows if r.get("Close")][-10:]
        if not closes:
            return None
        price = closes[-1]
        pct = ((price - closes[-2]) / closes[-2]) * 100.0 if len(closes) >= 2 and closes[-2] else 0.0
        return {"price": price, "pct": pct, "history": closes}
    except Exception:
        return None


def fetch_btc_fallback() -> dict | None:
    """Fallback for BTC-USD via CoinGecko / Coinbase."""
    try:
        data = json.loads(
            http_get_text(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true",
                timeout=12,
            )
        )
        btc = data["bitcoin"]
        return {"price": float(btc["usd"]), "pct": float(btc.get("usd_24h_change", 0.0)), "history": []}
    except Exception:
        pass
    try:
        data = json.loads(http_get_text("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=10))
        return {"price": float(data["data"]["amount"]), "pct": 0.0, "history": []}
    except Exception:
        return None


def fetch_macro_signals() -> dict:
    """Fetches SPY, SPX (^GSPC), GOLD (GC=F / XAUUSD), and BTC-USD from free public market endpoints."""
    spy = fetch_yahoo_ticker("SPY") or fetch_stooq_ticker("spy.us")
    spx = fetch_yahoo_ticker("^GSPC") or fetch_stooq_ticker("^spx")
    gold = fetch_yahoo_ticker("GC=F") or fetch_yahoo_ticker("XAUUSD=X") or fetch_stooq_ticker("xauusd")
    btc = fetch_yahoo_ticker("BTC-USD") or fetch_btc_fallback()
    return {"spy": spy, "spx": spx, "gold": gold, "btc": btc}


def empty_initial_stats(username: str) -> dict:
    """Safe zero-state baseline before the first GitHub Actions sync runs."""
    return {
        "username": username,
        "synced_at": "AWAITING SYNC",
        "live": False,
        "total_commits": 0,
        "total_contributions": 0,
        "total_repos": 0,
        "total_stars": 0,
        "followers": 0,
        "active_days": 0,
        "current_streak": 0,
        "longest_streak": 0,
        "weeks": [[0] * 7 for _ in range(20)],
        "last7_days": [0] * 7,
        "languages": [],
        "recent_projects": [],
        "blog_titles": extract_blog_titles(),
    }


def ema_series(values: list[float], period: int = 5) -> list[float]:
    """Computes an Exponential Moving Average series."""
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [float(values[0])]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1.0 - k))
    return out


def build_ohlc_candles(weeks: list[list[int]], count: int = 20) -> tuple[list[dict], list[float]]:
    """
    Converts weekly contribution lists into OHLC candles for the last `count` weeks
    aligned with the 5-week EMA. Periods with commits >= EMA (and > 0) are bullish green;
    quiet or below-average periods are bearish red.
    """
    if not weeks:
        weeks = [[0] * 7 for _ in range(count)]
    slice_weeks = weeks[-count:]
    weekly_totals = [sum(w) for w in slice_weeks]
    ema_vals = ema_series([float(v) for v in weekly_totals], period=5)

    prev_close = sum(weeks[-count - 1]) if len(weeks) > count else weekly_totals[0]
    candles = []
    for idx, day_counts in enumerate(slice_weeks):
        total = weekly_totals[idx]
        peak_day = max(day_counts) if day_counts else 0
        o_val = prev_close
        c_val = total
        h_val = max(o_val, c_val) + max(1, int(round(peak_day * 0.55))) if (o_val or c_val or peak_day) else 0
        l_val = max(0, min(o_val, c_val) - max(1, int(round(peak_day * 0.25)))) if (o_val or c_val) else 0
        is_bull = c_val > 0 and c_val >= ema_vals[idx]
        candles.append(
            {
                "open": o_val,
                "high": h_val,
                "low": l_val,
                "close": c_val,
                "volume": peak_day,
                "bull": is_bull,
                "zero": (o_val == 0 and c_val == 0),
            }
        )
        prev_close = c_val
    return candles, ema_vals


def smooth_svg_path(points: list[tuple[float, float]]) -> str:
    """Creates a smooth cubic Bezier SVG path through points."""
    if not points:
        return ""
    if len(points) == 1:
        return f"M {points[0][0]:.1f} {points[0][1]:.1f}"
    parts = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for i in range(len(points) - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < len(points) else points[i + 1]
        cp1x = p1[0] + (p2[0] - p0[0]) / 6.0
        cp1y = p1[1] + (p2[1] - p0[1]) / 6.0
        cp2x = p2[0] - (p3[0] - p1[0]) / 6.0
        cp2y = p2[1] - (p3[1] - p1[1]) / 6.0
        parts.append(f"C {cp1x:.1f} {cp1y:.1f}, {cp2x:.1f} {cp2y:.1f}, {p2[0]:.1f} {p2[1]:.1f}")
    return " ".join(parts)


def render_vol_surface_curves(x0: float, y0: float, width: float, height: float, t: dict) -> str:
    """Renders 5 layered 3D-perspective volatility smile / gamma curves strictly inside bounds."""
    layers = []
    num_slices = 5
    num_pts = 28
    for s in range(num_slices):
        depth = s / (num_slices - 1)
        y_base = y0 + 10.0 + depth * (height - 18.0)
        x_shift = (1.0 - depth) * 16.0
        amp = 11.0 + depth * 6.0
        pts = []
        for i in range(num_pts):
            u = i / (num_pts - 1)
            px = x0 + x_shift + u * (width - 20.0)
            smile = ((u - 0.48) * 2.0) ** 2 * 0.50
            gamma_wave = math.exp(-((u - 0.52) ** 2) / 0.045) * 0.90
            ripple = math.sin(u * math.pi * 3.0 + s * 0.65) * 0.12
            py = y_base - (gamma_wave - smile * 0.35 + ripple) * amp
            py = max(y0 - 2.0, min(y0 + height + 2.0, py))
            pts.append((px, py))
        path_d = smooth_svg_path(pts)
        opacity = 0.25 + depth * 0.70
        stroke = t["vol_cyan"] if s % 2 == 0 else t["ma_line"]
        if s == num_slices - 1:
            stroke = t["bull"]
        sw = 1.15 + depth * 0.95
        dur = 4.2 + (s % 2) * 1.4
        layers.append(
            f'<path d="{path_d}" fill="none" stroke="{stroke}" '
            f'stroke-width="{sw:.2f}" stroke-opacity="{opacity:.2f}">'
            f'<animate attributeName="stroke-opacity" values="{opacity:.2f};{max(0.15, opacity * 0.55):.2f};{opacity:.2f}" '
            f'dur="{dur:.1f}s" repeatCount="indefinite"/>'
            f'</path>'
        )
    return "\n    ".join(layers)


def format_num(val: int) -> str:
    return f"{val:,}"


def render_quant_svg(stats: dict, theme_name: str) -> str:
    """Feature #1: Renders the 920x440 $KHALID Quant Terminal SVG for dark or light mode."""
    t = THEMES[theme_name]
    candles, ema_vals = build_ohlc_candles(stats["weeks"], 20)
    closes = [c["close"] for c in candles]
    best_week = max((sum(w) for w in stats["weeks"]), default=0)

    signal_index = (
        stats["total_contributions"]
        + stats["total_stars"] * 12
        + stats["total_repos"] * 15
        + stats["current_streak"] * 8
    )

    last_close = closes[-1] if closes else 0
    prev_close = closes[-2] if len(closes) > 1 else 0
    if prev_close > 0:
        delta_pct = ((last_close - prev_close) / prev_close) * 100.0
        delta_sign = "+" if delta_pct >= 0 else ""
        delta_str = f"{delta_sign}{delta_pct:.1f}% WoW"
        delta_up = delta_pct >= 0
    elif last_close > 0:
        delta_str = f"+{last_close} THIS WK"
        delta_up = True
    else:
        delta_str = "READY" if not stats["live"] else "0.0% WoW"
        delta_up = True

    delta_fg = t["bull"] if delta_up else t["bear"]

    plot_x = 38.0
    plot_y = 104.0
    plot_w = 482.0
    plot_h = 152.0
    plot_bot = plot_y + plot_h  # 256.0
    vol_base_y = 291.0
    vol_max_h = 25.0

    max_hi = max([c["high"] for c in candles] + ema_vals + [1.0])
    log_max = math.log1p(max_hi)
    max_vol = max([c["volume"] for c in candles] + [1])

    def y_map(val: float) -> float:
        if val <= 0:
            return plot_bot
        norm = math.log1p(val) / log_max
        return max(plot_y, min(plot_bot, plot_bot - norm * plot_h))

    grid_parts = []
    for step in range(4):
        frac = step / 3.0
        gy = plot_bot - frac * plot_h
        gval = int(round(math.expm1(frac * log_max))) if stats["live"] else 0
        grid_parts.append(
            f'<line x1="{plot_x:.1f}" y1="{gy:.1f}" x2="{plot_x + plot_w:.1f}" y2="{gy:.1f}" '
            f'stroke="{t["grid"]}" stroke-width="1" stroke-dasharray="3,4"/>'
        )
        grid_parts.append(
            f'<text x="{plot_x + plot_w + 8:.1f}" y="{gy + 3:.1f}" fill="{t["text_muted"]}" '
            f'font-size="10" class="mono">{gval}</text>'
        )

    grid_parts.append(
        f'<line x1="{plot_x:.1f}" y1="264.0" x2="{plot_x + plot_w:.1f}" y2="264.0" '
        f'stroke="{t["grid"]}" stroke-width="1"/>'
    )
    grid_parts.append(
        f'<text x="{plot_x + plot_w + 8:.1f}" y="286.0" fill="{t["text_muted"]}" '
        f'font-size="9" class="mono">VOL</text>'
    )

    candle_parts = []
    ema_points = []
    step_x = plot_w / len(candles)
    body_w = 11.0
    has_any_commits = any(c["high"] > 0 for c in candles)

    if has_any_commits:
        for idx, c in enumerate(candles):
            cx = plot_x + (idx + 0.5) * step_x
            yh = y_map(c["high"])
            yl = y_map(c["low"])
            yo = y_map(c["open"])
            yc = y_map(c["close"])

            col = t["bull"] if c["bull"] else t["bear"]
            col_soft = t["bull_soft"] if c["bull"] else t["bear_soft"]

            if c["zero"]:
                candle_parts.append(
                    f'<rect x="{cx - body_w / 2:.1f}" y="{plot_bot - 2.5:.1f}" width="{body_w:.1f}" '
                    f'height="2.5" rx="1" fill="{t["bear"]}" fill-opacity="0.45"/>'
                )
                candle_parts.append(
                    f'<rect x="{cx - body_w / 2:.1f}" y="{vol_base_y - 2.0:.1f}" width="{body_w:.1f}" '
                    f'height="2.0" rx="1" fill="{t["bear"]}" fill-opacity="0.16"/>'
                )
            else:
                top_b = min(yo, yc)
                bot_b = max(yo, yc)
                bh = max(4.0, bot_b - top_b)
                if top_b + bh > plot_bot:
                    top_b = plot_bot - bh

                if c["volume"] > 0:
                    vh = max(3.0, (math.log1p(c["volume"]) / math.log1p(max_vol)) * vol_max_h)
                else:
                    vh = 2.0
                candle_parts.append(
                    f'<rect x="{cx - body_w / 2:.1f}" y="{vol_base_y - vh:.1f}" width="{body_w:.1f}" '
                    f'height="{vh:.1f}" rx="1.5" fill="{col}" fill-opacity="0.30"/>'
                )
                candle_parts.append(
                    f'<line x1="{cx:.1f}" y1="{yh:.1f}" x2="{cx:.1f}" y2="{yl:.1f}" '
                    f'stroke="{col}" stroke-width="1.6" stroke-linecap="round"/>'
                )
                candle_parts.append(
                    f'<rect x="{cx - body_w / 2:.1f}" y="{top_b:.1f}" width="{body_w:.1f}" '
                    f'height="{bh:.1f}" rx="2" fill="{col}" stroke="{col_soft}" stroke-width="0.6"/>'
                )

            if idx == len(candles) - 1:
                cy_dot = min(plot_bot - 2.0, yc)
                candle_parts.append(
                    f'<circle cx="{cx:.1f}" cy="{cy_dot:.1f}" r="4.5" fill="{col}" fill-opacity="0.32">'
                    f'<animate attributeName="r" values="3.5;7.5;3.5" dur="2.2s" repeatCount="indefinite"/>'
                    f'<animate attributeName="fill-opacity" values="0.45;0.1;0.45" dur="2.2s" repeatCount="indefinite"/>'
                    f'</circle>'
                    f'<circle cx="{cx:.1f}" cy="{cy_dot:.1f}" r="2.3" fill="{col}"/>'
                )
            ema_points.append((cx, y_map(ema_vals[idx])))

        ema_d = smooth_svg_path(ema_points)
        area_d = f"{ema_d} L {ema_points[-1][0]:.1f} {plot_bot:.1f} L {ema_points[0][0]:.1f} {plot_bot:.1f} Z"
        ema_svg = (
            f'<path d="{area_d}" fill="url(#emaArea)"/>\n    '
            f'<path d="{ema_d}" fill="none" stroke="{t["ma_line"]}" stroke-width="2.1" stroke-linecap="round"/>'
        )
    else:
        baseline_y = plot_bot - 8.0
        ema_svg = (
            f'<line x1="{plot_x:.1f}" y1="{baseline_y:.1f}" x2="{plot_x + plot_w:.1f}" y2="{baseline_y:.1f}" '
            f'stroke="{t["accent"]}" stroke-width="1.6" stroke-dasharray="5,5" stroke-opacity="0.65"/>\n    '
            f'<rect x="{plot_x + 115:.1f}" y="{plot_y + 52:.1f}" width="252" height="28" rx="6" '
            f'fill="{t["accent_pill_bg"]}" stroke="{t["border"]}" stroke-width="1"/>\n    '
            f'<text x="{plot_x + 241:.1f}" y="{plot_y + 70:.1f}" text-anchor="middle" '
            f'fill="{t["accent_pill_text"]}" font-size="11" font-weight="600" class="mono">'
            f'PUSH TO SYNC LIVE GITHUB CANDLES</text>'
        )

    langs = stats["languages"]
    bar_x = 600.0
    bar_y = 228.0
    bar_w = 284.0
    bar_h = 10.0

    lang_bar_parts = []
    lang_legend_parts = []
    if langs:
        cur_x = bar_x
        for i, lang in enumerate(langs):
            seg_w = max(4.0, (lang["pct"] / 100.0) * bar_w)
            if i == len(langs) - 1:
                seg_w = max(2.0, (bar_x + bar_w) - cur_x)
            lang_bar_parts.append(
                f'<rect x="{cur_x:.1f}" y="{bar_y:.1f}" width="{seg_w:.1f}" height="{bar_h:.1f}" fill="{lang["color"]}"/>'
            )
            cur_x += seg_w

        for i, lang in enumerate(langs[:4]):
            col_idx = i % 2
            row_idx = i // 2
            lx = 600.0 + col_idx * 145.0
            ly = 262.0 + row_idx * 22.0
            lname = escape(lang["name"][:11])
            lang_legend_parts.append(
                f'<circle cx="{lx + 4:.1f}" cy="{ly - 4:.1f}" r="4" fill="{lang["color"]}"/>'
                f'<text x="{lx + 14:.1f}" y="{ly:.1f}" fill="{t["text_primary"]}" font-size="11.5" class="mono">{lname}</text>'
                f'<text x="{lx + 134:.1f}" y="{ly:.1f}" text-anchor="end" fill="{t["text_secondary"]}" font-size="11" class="mono">{lang["pct"]:.1f}%</text>'
            )
    else:
        lang_bar_parts.append(
            f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{t["grid"]}"/>'
        )
        lang_legend_parts.append(
            f'<text x="742" y="272" text-anchor="middle" fill="{t["text_muted"]}" font-size="11" class="mono">'
            f'AWAITING REPO ALLOCATION SYNC</text>'
        )

    vol_curves = render_vol_surface_curves(434.0, 322.0, 452.0, 56.0, t)

    top_stack = " / ".join(f"{l['name'].upper()} {l['pct']:.0f}%" for l in langs[:3]) if langs else "PYTHON / JS / RUST"
    projects = stats.get("recent_projects") or []
    if projects:
        proj_str = " · ".join(
            f"{p['name']}" + (f" ★{p['stars']}" if p["stars"] > 0 else "")
            for p in projects[:3]
        )
    else:
        proj_str = "Dashboard Options · Quant AI Systems"

    blogs = stats.get("blog_titles") or []
    blog_str = " · ".join(blogs[:3]) if blogs else "Financial Intelligence · Market Research"
    status_tag = "LIVE" if stats["live"] else "STANDBY"

    ticker_msg = (
        f"▲ $KHALID   •   "
        f"COMMITS: {format_num(stats['total_commits'])}   •   "
        f"REPOS: {format_num(stats['total_repos'])}   •   "
        f"STARS: {format_num(stats['total_stars'])}   •   "
        f"STACK: {top_stack}   •   "
        f"PROJECTS: {proj_str}   •   "
        f"BLOG: {blog_str}   •   "
        f"STATUS: {status_tag}   •   "
    )
    ticker_escaped = escape(ticker_msg)
    ticker_px = max(900, int(round(len(ticker_msg) * 7.0 + 48)))
    ticker_dur = max(24, int(round(ticker_px / 48.0)))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 440" width="920" height="440" role="img" aria-label="Khalid Naami Quantitative GitHub Terminal">
  <style>
    .mono {{ font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace; }}
  </style>

  <defs>
    <linearGradient id="emaArea" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{t['ma_line']}" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="{t['ma_line']}" stop-opacity="0.0"/>
    </linearGradient>
    <clipPath id="allocClip">
      <rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="5"/>
    </clipPath>
    <clipPath id="tickerClip">
      <rect x="114" y="394" width="778" height="32" rx="6"/>
    </clipPath>
  </defs>

  <rect x="0.5" y="0.5" width="919" height="439" rx="14" fill="{t['bg_outer']}" stroke="{t['border']}" stroke-width="1"/>

  <circle cx="30" cy="30" r="7" fill="{t['bull']}" fill-opacity="0.24">
    <animate attributeName="r" values="4;9;4" dur="2.4s" repeatCount="indefinite"/>
    <animate attributeName="fill-opacity" values="0.40;0.10;0.40" dur="2.4s" repeatCount="indefinite"/>
  </circle>
  <circle cx="30" cy="30" r="3.5" fill="{t['bull']}"/>
  <text x="46" y="36" fill="{t['text_primary']}" font-size="20" font-weight="800" class="mono">$KHALID</text>
  <rect x="142" y="19" width="124" height="20" rx="5" fill="{t['accent_pill_bg']}" stroke="{t['accent']}" stroke-width="0.7" stroke-opacity="0.5"/>
  <text x="204" y="33" text-anchor="middle" fill="{t['accent_pill_text']}" font-size="10" font-weight="700" class="mono">QUANT · AI · OSINT</text>
  <text x="46" y="54" fill="{t['text_secondary']}" font-size="10.5" class="mono">KHALID NAAMI  //  EXECUTION &amp; VOLATILITY TELEMETRY</text>

  <text x="720" y="25" text-anchor="end" fill="{t['text_muted']}" font-size="9.5" font-weight="600" class="mono">SIGNAL INDEX</text>
  <text x="720" y="47" text-anchor="end" fill="{t['text_primary']}" font-size="19" font-weight="800" class="mono">{format_num(signal_index)}</text>

  <rect x="734" y="16" width="166" height="40" rx="8" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <text x="817" y="32" text-anchor="middle" fill="{delta_fg}" font-size="11.5" font-weight="700" class="mono">{escape(delta_str)}</text>
  <text x="817" y="48" text-anchor="middle" fill="{t['text_muted']}" font-size="9.5" class="mono">SYNC: {escape(stats['synced_at'])}</text>

  <rect x="20" y="72" width="550" height="230" rx="10" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <text x="36" y="93" fill="{t['text_primary']}" font-size="11.5" font-weight="700" class="mono">20W COMMIT VELOCITY · OHLC (LOG)</text>
  <circle cx="430" cy="89" r="3.5" fill="{t['bull']}"/>
  <text x="438" y="93" fill="{t['text_secondary']}" font-size="10" class="mono">BULL</text>
  <circle cx="476" cy="89" r="3.5" fill="{t['bear']}"/>
  <text x="484" y="93" fill="{t['text_secondary']}" font-size="10" class="mono">BEAR</text>
  <line x1="518" y1="89" x2="532" y2="89" stroke="{t['ma_line']}" stroke-width="2"/>
  <text x="537" y="93" fill="{t['text_secondary']}" font-size="10" class="mono">EMA5</text>

  <g>
    {chr(10) + "    ".join(grid_parts)}
    {ema_svg}
    {chr(10) + "    ".join(candle_parts)}
  </g>

  <rect x="584" y="72" width="316" height="110" rx="10" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <text x="600" y="92" fill="{t['text_secondary']}" font-size="10.5" font-weight="700" class="mono">PORTFOLIO TELEMETRY</text>
  <line x1="600" y1="100" x2="884" y2="100" stroke="{t['grid']}" stroke-width="1"/>

  <text x="600" y="118" fill="{t['text_muted']}" font-size="9.5" class="mono">COMMITS (1Y)</text>
  <text x="600" y="137" fill="{t['text_primary']}" font-size="17" font-weight="700" class="mono">{format_num(stats['total_commits'])}</text>

  <text x="748" y="118" fill="{t['text_muted']}" font-size="9.5" class="mono">REPOSITORIES</text>
  <text x="748" y="137" fill="{t['text_primary']}" font-size="17" font-weight="700" class="mono">{format_num(stats['total_repos'])}</text>

  <text x="600" y="156" fill="{t['text_muted']}" font-size="9.5" class="mono">STARS EARNED</text>
  <text x="600" y="174" fill="{t['accent']}" font-size="17" font-weight="700" class="mono">{format_num(stats['total_stars'])}</text>

  <text x="748" y="156" fill="{t['text_muted']}" font-size="9.5" class="mono">FOLLOWERS</text>
  <text x="748" y="174" fill="{t['text_primary']}" font-size="17" font-weight="700" class="mono">{format_num(stats['followers'])}</text>

  <rect x="584" y="194" width="316" height="108" rx="10" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <text x="600" y="215" fill="{t['text_secondary']}" font-size="10.5" font-weight="700" class="mono">PORTFOLIO ALLOCATION</text>
  <g clip-path="url(#allocClip)">
    {chr(10) + "    ".join(lang_bar_parts)}
  </g>
  {chr(10) + "  ".join(lang_legend_parts)}

  <rect x="20" y="314" width="880" height="68" rx="10" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <text x="36" y="333" fill="{t['text_secondary']}" font-size="10" font-weight="700" class="mono">GEX // VOLATILITY SURFACE &amp; STREAK</text>

  <text x="36" y="352" fill="{t['text_muted']}" font-size="9.5" class="mono">CURRENT STREAK</text>
  <text x="36" y="370" fill="{t['bull']}" font-size="15" font-weight="700" class="mono">{stats['current_streak']}d</text>

  <text x="144" y="352" fill="{t['text_muted']}" font-size="9.5" class="mono">BEST STREAK</text>
  <text x="144" y="370" fill="{t['text_primary']}" font-size="15" font-weight="700" class="mono">{stats['longest_streak']}d</text>

  <text x="242" y="352" fill="{t['text_muted']}" font-size="9.5" class="mono">ACTIVE DAYS</text>
  <text x="242" y="370" fill="{t['text_primary']}" font-size="15" font-weight="700" class="mono">{stats['active_days']}/365</text>

  <text x="336" y="352" fill="{t['text_muted']}" font-size="9.5" class="mono">PEAK WK</text>
  <text x="336" y="370" fill="{t['accent']}" font-size="15" font-weight="700" class="mono">{best_week}</text>

  <line x1="418" y1="326" x2="418" y2="372" stroke="{t['grid']}" stroke-width="1"/>
  {vol_curves}

  <rect x="20" y="394" width="880" height="32" rx="8" fill="{t['ticker_bg']}" stroke="{t['border']}" stroke-width="1"/>
  <rect x="26" y="399" width="82" height="22" rx="5" fill="{t['accent_pill_bg']}"/>
  <text x="67" y="414" text-anchor="middle" fill="{t['accent_pill_text']}" font-size="10" font-weight="700" class="mono">LIVE TAPE</text>

  <g clip-path="url(#tickerClip)">
    <g>
      <animateTransform attributeName="transform" type="translate" from="0 0" to="-{ticker_px} 0" dur="{ticker_dur}s" repeatCount="indefinite"/>
      <text x="120" y="414" fill="{t['text_secondary']}" font-size="11" class="mono">{ticker_escaped}</text>
      <text x="{120 + ticker_px}" y="414" fill="{t['text_secondary']}" font-size="11" class="mono">{ticker_escaped}</text>
    </g>
  </g>
</svg>
"""


def render_vol_surface_banner(theme_name: str) -> str:
    """Feature #2: Renders an animated 3D Isometric Volatility Surface + GEX Pulse SVG (920x210)."""
    t = THEMES[theme_name]
    cols = 22
    rows = 11

    def surface_pt(i: int, j: int) -> tuple[float, float]:
        u = i / (cols - 1)  # Strike Moneyness K/S
        v = j / (rows - 1)  # Time to Expiry T
        skew = ((u - 0.52) ** 2) / (0.28 + 0.72 * v)
        gamma_wall = math.exp(-(((u - 0.50) ** 2) + ((v - 0.38) ** 2)) / 0.085)
        z = 0.14 + 0.54 * skew + 0.48 * gamma_wall
        px = 266.0 + u * 450.0 + v * 164.0
        py = 192.0 - v * 90.0 - z * 185.0
        return (px, py)

    grid_2d = [[surface_pt(i, j) for i in range(cols)] for j in range(rows)]
    mesh_parts = []

    # 3D isometric floor reference axes
    fl_00 = (266.0, 192.0)
    fl_10 = (266.0 + 450.0, 192.0)
    fl_11 = (266.0 + 450.0 + 164.0, 192.0 - 90.0)
    fl_01 = (266.0 + 164.0, 192.0 - 90.0)
    mesh_parts.append(
        f'<polygon points="{fl_00[0]:.1f},{fl_00[1]:.1f} {fl_10[0]:.1f},{fl_10[1]:.1f} '
        f'{fl_11[0]:.1f},{fl_11[1]:.1f} {fl_01[0]:.1f},{fl_01[1]:.1f}" '
        f'fill="{t["bg_panel"]}" fill-opacity="0.45" stroke="{t["grid"]}" stroke-width="1" stroke-dasharray="3,4"/>'
    )

    # Longitudinal ribs (constant strike lines)
    for i in range(0, cols, 2):
        pts = [grid_2d[j][i] for j in range(rows)]
        d = smooth_svg_path(pts)
        mesh_parts.append(
            f'<path d="{d}" fill="none" stroke="{t["accent"]}" stroke-width="1.0" stroke-opacity="0.26"/>'
        )

    # Transverse expiry smile curves with subtle breathing animation
    for j in range(rows):
        depth = j / (rows - 1)
        d = smooth_svg_path(grid_2d[j])
        if j == rows - 1:
            stroke = t["bull"]
            op = 0.94
            sw = 2.2
        elif j >= rows // 2:
            stroke = t["ma_line"]
            op = 0.48 + depth * 0.40
            sw = 1.55
        else:
            stroke = t["vol_cyan"]
            op = 0.30 + depth * 0.36
            sw = 1.25
        dur = 3.6 + (j % 3) * 1.1
        mesh_parts.append(
            f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw:.2f}" stroke-opacity="{op:.2f}">'
            f'<animate attributeName="stroke-opacity" values="{op:.2f};{max(0.16, op * 0.48):.2f};{op:.2f}" '
            f'dur="{dur:.1f}s" repeatCount="indefinite"/>'
            f'</path>'
        )

    # Pulsing GEX gamma nodes along the peak ridge
    mid_col = cols // 2
    nodes = [
        (grid_2d[2][mid_col], t["vol_cyan"], "2.4s"),
        (grid_2d[5][mid_col], t["ma_line"], "2.9s"),
        (grid_2d[8][mid_col], t["ma_line"], "2.6s"),
        (grid_2d[rows - 1][mid_col], t["bull"], "2.1s"),
    ]
    node_parts = []
    for (nx, ny), ncol, ndur in nodes:
        node_parts.append(
            f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="5.5" fill="{ncol}" fill-opacity="0.28">'
            f'<animate attributeName="r" values="3.8;9;3.8" dur="{ndur}" repeatCount="indefinite"/>'
            f'<animate attributeName="fill-opacity" values="0.48;0.08;0.48" dur="{ndur}" repeatCount="indefinite"/>'
            f'</circle>'
            f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="2.6" fill="{ncol}"/>'
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 210" width="920" height="210" role="img" aria-label="Animated 3D Volatility Surface and GEX Pulse">
  <style>
    .mono {{ font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace; }}
  </style>
  <rect x="0.5" y="0.5" width="919" height="209" rx="14" fill="{t['bg_outer']}" stroke="{t['border']}" stroke-width="1"/>
  <rect x="16" y="16" width="228" height="178" rx="10" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>

  <rect x="30" y="30" width="144" height="20" rx="5" fill="{t['accent_pill_bg']}" stroke="{t['accent']}" stroke-width="0.7" stroke-opacity="0.5"/>
  <text x="102" y="44" text-anchor="middle" fill="{t['accent_pill_text']}" font-size="10" font-weight="700" class="mono">3D VOL SURFACE · GEX</text>

  <text x="30" y="74" fill="{t['text_primary']}" font-size="13" font-weight="800" class="mono">IV(K, T) TOPOGRAPHY</text>
  <text x="30" y="95" fill="{t['text_secondary']}" font-size="10.5" class="mono">σ = σ₀ + α·skew² + β·Γ(T)</text>

  <line x1="30" y1="112" x2="230" y2="112" stroke="{t['grid']}" stroke-width="1"/>
  <text x="30" y="131" fill="{t['text_muted']}" font-size="9.5" class="mono">AXES: STRIKE (K/S) × EXPIRY</text>
  <text x="30" y="149" fill="{t['text_muted']}" font-size="9.5" class="mono">MODEL: SKEW + GAMMA WALL</text>

  <circle cx="36" cy="173" r="4" fill="{t['bull']}">
    <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite"/>
  </circle>
  <text x="48" y="177" fill="{t['bull']}" font-size="10" font-weight="700" class="mono">GAMMA PULSE ACTIVE</text>

  <g>
    {chr(10) + "    ".join(mesh_parts)}
    {chr(10) + "    ".join(node_parts)}
  </g>
  <text x="490" y="203" text-anchor="middle" fill="{t['text_muted']}" font-size="9.5" class="mono">STRIKE MONEYNESS (K/S)</text>
  <text x="888" y="156" text-anchor="end" fill="{t['text_muted']}" font-size="9.5" class="mono">EXPIRY (T)</text>
</svg>
"""


def sparkline_svg(values: list[float], x0: float, y0: float, w: float, h: float, color: str, grad_id: str) -> str:
    """Renders a crisp mini sparkline with subtle gradient fill."""
    if len(values) < 2:
        mid = y0 + h / 2.0
        return f'<line x1="{x0:.1f}" y1="{mid:.1f}" x2="{x0 + w:.1f}" y2="{mid:.1f}" stroke="{color}" stroke-width="1.4" stroke-dasharray="3,3" stroke-opacity="0.6"/>'
    vmin = min(values)
    vmax = max(values)
    span = max(1e-9, vmax - vmin)
    pts = []
    for i, val in enumerate(values):
        px = x0 + (i / (len(values) - 1)) * w
        py = y0 + h - ((val - vmin) / span) * (h - 4.0) - 2.0
        pts.append((px, py))
    d = smooth_svg_path(pts)
    area = f"{d} L {pts[-1][0]:.1f} {y0 + h:.1f} L {pts[0][0]:.1f} {y0 + h:.1f} Z"
    return (
        f'<path d="{area}" fill="url(#{grad_id})"/>'
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.3" fill="{color}"/>'
    )


def render_osint_hud(stats: dict, macro: dict, theme_name: str) -> str:
    """Feature #4: Renders the 920x184 OSINT // Macro Signal HUD SVG with animated radar + SPY, SPX, GOLD, BTC, $KHALID."""
    t = THEMES[theme_name]
    spy = macro.get("spy")
    spx = macro.get("spx")
    gold = macro.get("gold")
    btc = macro.get("btc")

    has_macro = any(m and m.get("price") is not None for m in (spy, spx, gold, btc))
    if stats["live"] and has_macro:
        regime, regime_col = "HUD: LIVE", t["bull"]
    elif stats["live"]:
        regime, regime_col = "HUD: ACTIVE", t["accent"]
    else:
        regime, regime_col = "HUD: STANDBY", t["accent"]

    card_w = 135.0
    spark_w = card_w - 24.0  # 111.0

    def fmt_ticker_card(
        x: float,
        label: str,
        sub: str,
        data: dict | None,
        prefix: str,
        decimals: int,
        grad_id: str,
    ) -> str:
        if data and data.get("price") is not None:
            val_str = f"{prefix}{data['price']:,.{decimals}f}"
            pct = float(data.get("pct", 0.0))
            sign = "+" if pct >= 0 else ""
            pct_str = f"{sign}{pct:.2f}%"
            col = t["bull"] if pct >= 0 else t["bear"]
            spark = sparkline_svg(data.get("history") or [], x + 12.0, 128.0, spark_w, 28.0, col, grad_id)
        else:
            val_str = "--"
            pct_str = "AWAITING"
            col = t["text_muted"]
            spark = sparkline_svg([], x + 12.0, 128.0, spark_w, 28.0, col, grad_id)

        return f"""  <rect x="{x:.1f}" y="42" width="{card_w:.0f}" height="126" rx="9" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <text x="{x + 12:.1f}" y="61" fill="{t['text_primary']}" font-size="11" font-weight="800" class="mono">{escape(label)}</text>
  <text x="{x + card_w - 12:.1f}" y="61" text-anchor="end" fill="{t['text_muted']}" font-size="8.5" class="mono">{escape(sub)}</text>
  <line x1="{x + 12:.1f}" y1="69" x2="{x + card_w - 12:.1f}" y2="69" stroke="{t['grid']}" stroke-width="1"/>
  <text x="{x + 12:.1f}" y="93" fill="{t['text_primary']}" font-size="14.5" font-weight="800" class="mono">{escape(val_str)}</text>
  <text x="{x + 12:.1f}" y="112" fill="{col}" font-size="10.5" font-weight="700" class="mono">{escape(pct_str)}</text>
  {spark}"""

    # Card 5: $KHALID 7D Code Velocity (x=765, width=135 -> ends at 900)
    c5_x = 765.0
    last7 = [float(v) for v in (stats.get("last7_days") or [0] * 7)]
    sum7 = int(sum(last7))
    code_col = t["bull"] if sum7 > 0 else t["text_muted"]
    code_spark = sparkline_svg(last7, c5_x + 12.0, 128.0, spark_w, 28.0, t["accent"], "gradCode")
    card5 = f"""  <rect x="{c5_x:.1f}" y="42" width="{card_w:.0f}" height="126" rx="9" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <text x="{c5_x + 12:.1f}" y="61" fill="{t['text_primary']}" font-size="11" font-weight="800" class="mono">$KHALID</text>
  <text x="{c5_x + card_w - 12:.1f}" y="61" text-anchor="end" fill="{t['text_muted']}" font-size="8.5" class="mono">7D PULSE</text>
  <line x1="{c5_x + 12:.1f}" y1="69" x2="{c5_x + card_w - 12:.1f}" y2="69" stroke="{t['grid']}" stroke-width="1"/>
  <text x="{c5_x + 12:.1f}" y="93" fill="{t['text_primary']}" font-size="14.5" font-weight="800" class="mono">+{sum7} CMTS</text>
  <text x="{c5_x + 12:.1f}" y="112" fill="{code_col}" font-size="10.5" font-weight="700" class="mono">STREAK: {stats['current_streak']}D</text>
  {code_spark}"""

    c1 = fmt_ticker_card(181.0, "SPY", "ETF", spy, "$", 2, "gradSpy")
    c2 = fmt_ticker_card(327.0, "SPX", "S&P 500", spx, "", 2, "gradSpx")
    c3 = fmt_ticker_card(473.0, "GOLD", "XAU/OZ", gold, "$", 2, "gradGold")
    c4 = fmt_ticker_card(619.0, "BTC", "CRYPTO", btc, "$", 0, "gradBtc")

    # Radar panel: x=20..169 (width=149), center (94.5, 105), radius 44
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 920 184" width="920" height="184" role="img" aria-label="OSINT Macro Signal HUD">
  <style>
    .mono {{ font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Consolas, monospace; }}
  </style>
  <defs>
    <linearGradient id="radarBeam" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{t['bull']}" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="{t['bull']}" stop-opacity="0.02"/>
    </linearGradient>
    <linearGradient id="gradSpy" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{t['bull']}" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="{t['bull']}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="gradSpx" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{t['vol_cyan']}" stop-opacity="0.24"/>
      <stop offset="100%" stop-color="{t['vol_cyan']}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="gradGold" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{t['warn']}" stop-opacity="0.26"/>
      <stop offset="100%" stop-color="{t['warn']}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="gradBtc" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{t['vol_cyan']}" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="{t['vol_cyan']}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="gradCode" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{t['accent']}" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="{t['accent']}" stop-opacity="0"/>
    </linearGradient>
  </defs>

  <rect x="0.5" y="0.5" width="919" height="183" rx="14" fill="{t['bg_outer']}" stroke="{t['border']}" stroke-width="1"/>

  <!-- Top HUD Header -->
  <circle cx="30" cy="24" r="3.5" fill="{regime_col}">
    <animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite"/>
  </circle>
  <text x="42" y="28" fill="{t['text_primary']}" font-size="11.5" font-weight="800" class="mono">OSINT // MACRO &amp; GEOPOLITICAL SIGNAL HUD</text>
  <rect x="380" y="14" width="112" height="18" rx="4" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="0.8"/>
  <text x="436" y="27" text-anchor="middle" fill="{regime_col}" font-size="9.5" font-weight="700" class="mono">{escape(regime)}</text>
  <text x="900" y="28" text-anchor="end" fill="{t['text_muted']}" font-size="9.5" class="mono">FEEDS: SPY · SPX · GOLD · BTC · GITHUB  //  {escape(stats['synced_at'])}</text>

  <!-- Left Tactical Radar Panel -->
  <rect x="20" y="42" width="149" height="126" rx="9" fill="{t['bg_panel']}" stroke="{t['border']}" stroke-width="1"/>
  <circle cx="94.5" cy="105" r="44" fill="none" stroke="{t['grid']}" stroke-width="1.2"/>
  <circle cx="94.5" cy="105" r="29" fill="none" stroke="{t['grid']}" stroke-width="1" stroke-dasharray="2,3"/>
  <circle cx="94.5" cy="105" r="14" fill="none" stroke="{t['grid']}" stroke-width="1"/>
  <line x1="46.5" y1="105" x2="142.5" y2="105" stroke="{t['grid']}" stroke-width="0.9"/>
  <line x1="94.5" y1="57" x2="94.5" y2="153" stroke="{t['grid']}" stroke-width="0.9"/>

  <g>
    <animateTransform attributeName="transform" type="rotate" from="0 94.5 105" to="360 94.5 105" dur="5.5s" repeatCount="indefinite"/>
    <path d="M 94.5 105 L 94.5 61 A 44 44 0 0 1 132.6 83 Z" fill="url(#radarBeam)"/>
    <line x1="94.5" y1="105" x2="94.5" y2="61" stroke="{t['bull']}" stroke-width="1.5" stroke-opacity="0.85"/>
  </g>

  <circle cx="116" cy="86" r="2.5" fill="{t['bull']}">
    <animate attributeName="opacity" values="0.2;1;0.2" dur="2.7s" repeatCount="indefinite"/>
  </circle>
  <circle cx="74" cy="118" r="2.2" fill="{t['accent']}">
    <animate attributeName="opacity" values="0.2;1;0.2" dur="3.4s" repeatCount="indefinite"/>
  </circle>
  <circle cx="119" cy="124" r="2.1" fill="{t['vol_cyan']}">
    <animate attributeName="opacity" values="0.15;0.95;0.15" dur="4.1s" repeatCount="indefinite"/>
  </circle>
  <circle cx="94.5" cy="105" r="2.6" fill="{t['bull']}"/>

{c1}
{c2}
{c3}
{c4}
{card5}
</svg>
"""


def main() -> int:
    username = os.environ.get("USER_NAME") or DEFAULT_USER
    token = (os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()

    if "--offline" in sys.argv or not token:
        if not token and "--offline" not in sys.argv:
            print("No ACCESS_TOKEN or GITHUB_TOKEN found; generating baseline SVGs.", file=sys.stderr)
        stats = empty_initial_stats(username)
        macro = {"spy": None, "spx": None, "gold": None, "btc": None}
    else:
        stats = fetch_github_stats(username, token)
        macro = fetch_macro_signals()

    for theme_name in ("dark", "light"):
        outputs = (
            (f"quant_{theme_name}.svg", render_quant_svg(stats, theme_name)),
            (f"vol_surface_{theme_name}.svg", render_vol_surface_banner(theme_name)),
            (f"osint_hud_{theme_name}.svg", render_osint_hud(stats, macro, theme_name)),
        )
        for filename, content in outputs:
            with open(filename, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print(f"Wrote {filename}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
