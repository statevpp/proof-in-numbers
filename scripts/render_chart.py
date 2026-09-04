#!/usr/bin/env python3
"""
render_chart.py — Renders a branded chart PNG from the REAL numbers in
data/today_stat.json using matplotlib. Deliberately NOT an AI image model —
AI image generators cannot be trusted to draw numerically accurate charts
(they hallucinate values), so this stays 100% deterministic and free.

The small on-screen "Source: ..." caption is intentional, not decorative —
it's the channel's main visible difference from generic AI "fact" channels
that make numbers up: every "Proof in Numbers" video shows exactly where its
number came from. Every template below keeps that caption, plus a country +
indicator title, no matter which visual style is chosen.

VISUAL VARIETY (added 2026-09-04, after the channel moved to 4 videos/day):
publishing 4 videos a day with the exact same chart style made the channel
feel repetitive fast. Two independent things now vary between videos:

1. Accent color by pillar — MONEY_ACCENT (warm gold) for "Money in Your
   Life", LIFE_ACCENT (teal) for "Your Life by the Numbers" — so the two
   pillars are visually distinguishable at a glance, not just by title text.
2. Chart template by (pillar, slot) — daily-short.yml's 4-way matrix means
   there are exactly 4 (pillar, slot) combinations a day; TEMPLATE_BY_SLOT
   below maps each one to a DIFFERENT layout (line trend / hero number /
   before-vs-after bars / proportion grid), so all four of today's videos
   look different from each other, and the same slot uses a different
   template than its sibling slot in the other pillar. SLOT is read from an
   env var (see daily-short.yml's "Render chart" step) — if it's unset
   (e.g. a local manual run), this falls back to the original single-line-
   chart template, so old single-video-per-day usage still works unchanged.

All four templates are pure matplotlib (no AI image calls), so this stays
free and numerically exact regardless of which one gets picked.

Output: assets/chart.png (1080x1920 canvas, portrait, ready to be dropped
straight into the vertical Short by assemble_video.sh). Every template
leaves the top ~300px and very bottom empty — assemble_video.sh burns the
pillar badge + hook caption into the top band, and the "Source: ..." footer
always sits in the bottom band — so no template drawing needs to know
about that overlay; render_chart.py alone keeps everything else compatible
with it.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")  # headless — required on GitHub Actions runners
import matplotlib.pyplot as plt

# ---- Brand style ----
BRAND_BG = "#0b0e14"
BRAND_TEXT = "#eef0f2"
DIM_SHADE = "#3a4250"      # "before" bar / unfilled grid cells — muted, not accent
MONEY_ACCENT = "#e0b04a"   # warm gold — "Money in Your Life"
LIFE_ACCENT = "#4fd1c5"    # teal — "Your Life by the Numbers"
FIG_W_PX, FIG_H_PX = 1080, 1920
DPI = 150

# Full country names for the channel's rotating pool (see fetch_stat.py's
# COUNTRY_POOL) — purely a display nicety so chart titles read "POLAND"
# instead of the raw "PL" ISO2 code used internally. Falls back to the raw
# code for anything not in this list (defensive, should never trigger).
COUNTRY_NAMES = {
    "BG": "Bulgaria", "US": "United States", "DE": "Germany", "JP": "Japan",
    "CN": "China", "IN": "India", "BR": "Brazil", "NG": "Nigeria",
    "FR": "France", "GB": "United Kingdom", "KR": "South Korea",
    "ZA": "South Africa", "MX": "Mexico", "SA": "Saudi Arabia",
    "AU": "Australia", "CA": "Canada", "TR": "Turkey", "PL": "Poland",
    "EG": "Egypt", "VN": "Vietnam",
}


def country_label(stat: dict) -> str:
    return COUNTRY_NAMES.get(stat["country"], stat["country"]).upper()


def _format_number(val: float) -> str:
    """Shared number formatting so every template renders values the same
    way: thousands separators for big numbers, one decimal for small ones."""
    return f"{val:,.0f}" if abs(val) >= 100 else f"{val:,.1f}"


# ---------------------------------------------------------------------------
# Template A — "line": the channel's original style. A trend line across the
# full series, with the overall percent change called out underneath.
# ---------------------------------------------------------------------------
def draw_line_template(fig, stat: dict, accent: str) -> None:
    years = [int(y) for y, _ in stat["series"]]
    values = [v for _, v in stat["series"]]

    ax = fig.add_axes([0.12, 0.35, 0.76, 0.35])
    ax.set_facecolor(BRAND_BG)
    ax.plot(years, values, color=accent, linewidth=4, marker="o", markersize=6)
    ax.fill_between(years, values, min(values), color=accent, alpha=0.12)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=BRAND_TEXT, labelsize=16)
    ax.grid(axis="y", color=BRAND_TEXT, alpha=0.08)

    title = f"{country_label(stat)} — {stat['indicator_label']}"
    fig.text(0.5, 0.74, title, ha="center", color=BRAND_TEXT, fontsize=20, wrap=True)

    change = stat.get("pct_change")
    if change is not None:
        sign = "+" if change >= 0 else ""
        fig.text(
            0.5, 0.27, f"{sign}{change}%  ({stat['first_year']} → {stat['last_year']})",
            ha="center", color=accent, fontsize=28, fontweight="bold",
        )


# ---------------------------------------------------------------------------
# Template B — "hero": one huge number takes center stage, for stats where
# the single latest value is the most striking thing (e.g. a life expectancy
# figure or a dollar amount), rather than the shape of the trend.
# ---------------------------------------------------------------------------
def draw_hero_template(fig, stat: dict, accent: str) -> None:
    fig.text(0.5, 0.74, country_label(stat), ha="center", color=BRAND_TEXT,
              fontsize=26, fontweight="bold")

    num_text = _format_number(stat["last_value"])
    # Long numbers (rare, but e.g. very large currency values) would
    # otherwise overflow the 1080px-wide canvas at full size — shrink in
    # steps rather than let matplotlib clip or overrun the frame.
    fontsize = 100
    if len(num_text) > 6:
        fontsize = 80
    if len(num_text) > 9:
        fontsize = 60
    fig.text(0.5, 0.52, num_text, ha="center", va="center", color=accent,
              fontsize=fontsize, fontweight="bold")

    fig.text(0.5, 0.40, stat["indicator_label"], ha="center", color=BRAND_TEXT,
              fontsize=15, wrap=True)

    change = stat.get("pct_change")
    if change is not None:
        sign = "+" if change >= 0 else ""
        fig.text(
            0.5, 0.28, f"{sign}{change}% since {stat['first_year']}",
            ha="center", color=accent, fontsize=22, fontweight="bold",
        )


# ---------------------------------------------------------------------------
# Template C — "bars": a simple before-vs-after pair of bars, good for
# stats that are really a two-point comparison (e.g. "doubled in 10 years").
# ---------------------------------------------------------------------------
def draw_bars_template(fig, stat: dict, accent: str) -> None:
    title = f"{country_label(stat)} — {stat['indicator_label']}"
    fig.text(0.5, 0.76, title, ha="center", color=BRAND_TEXT, fontsize=18, wrap=True)

    ax = fig.add_axes([0.20, 0.34, 0.60, 0.36])
    ax.set_facecolor(BRAND_BG)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(
        [str(stat["first_year"]), str(stat["last_year"])], color=BRAND_TEXT, fontsize=16
    )
    ax.set_yticks([])

    first_val, last_val = stat["first_value"], stat["last_value"]
    bars = ax.bar([0, 1], [first_val, last_val], width=0.5, color=[DIM_SHADE, accent])

    vmax = max(abs(first_val), abs(last_val), 1e-9)
    ax.set_ylim(min(0, first_val, last_val) - vmax * 0.05, vmax * 1.3)
    for bar, val in zip(bars, [first_val, last_val]):
        ax.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + vmax * 0.04,
            _format_number(val), ha="center", color=BRAND_TEXT, fontsize=16,
            fontweight="bold",
        )

    change = stat.get("pct_change")
    if change is not None:
        sign = "+" if change >= 0 else ""
        fig.text(
            0.5, 0.24, f"{sign}{change}% change", ha="center", color=accent,
            fontsize=26, fontweight="bold",
        )


# ---------------------------------------------------------------------------
# Template D — "pictogram": a 10x10 proportion grid, filled in the accent
# color up to the magnitude of the percent change (capped at 100). A generic
# "visual magnitude" device — it never claims to represent literal people or
# units, the exact numbers are always spelled out in the caption underneath
# and in the spoken narration, matching the channel's always-show-your-work
# rule.
# ---------------------------------------------------------------------------
def draw_pictogram_template(fig, stat: dict, accent: str) -> None:
    title = f"{country_label(stat)} — {stat['indicator_label']}"
    fig.text(0.5, 0.76, title, ha="center", color=BRAND_TEXT, fontsize=18, wrap=True)

    change = stat.get("pct_change")
    magnitude = min(abs(change), 100) if change is not None else 0
    filled = round(magnitude)

    ax = fig.add_axes([0.18, 0.36, 0.64, 0.32])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.axis("off")

    idx = 0
    for row in range(10):
        for col in range(10):
            color = accent if idx < filled else DIM_SHADE
            ax.add_patch(plt.Rectangle(
                (col + 0.08, 9 - row + 0.08), 0.84, 0.84,
                facecolor=color, edgecolor=BRAND_BG, linewidth=1,
            ))
            idx += 1

    if change is not None:
        sign = "+" if change >= 0 else ""
        fig.text(
            0.5, 0.24, f"{sign}{change}% change ({stat['first_year']} → {stat['last_year']})",
            ha="center", color=accent, fontsize=20, fontweight="bold",
        )
    else:
        fig.text(
            0.5, 0.24, f"{stat['first_year']} → {stat['last_year']}",
            ha="center", color=BRAND_TEXT, fontsize=20,
        )


TEMPLATES = {
    "line": draw_line_template,
    "hero": draw_hero_template,
    "bars": draw_bars_template,
    "pictogram": draw_pictogram_template,
}

# Exactly one template per (pillar, slot) combination in the 4-way daily
# matrix — see daily-short.yml — so all four of today's videos look
# different from each other. Unset/unrecognized SLOT (e.g. a local manual
# run with no matrix) falls back to "line", the channel's original look.
TEMPLATE_BY_SLOT = {
    ("money", "1"): "line",
    ("money", "2"): "bars",
    ("life", "1"): "hero",
    ("life", "2"): "pictogram",
}


def main():
    with open("data/today_stat.json", "r", encoding="utf-8") as f:
        stat = json.load(f)

    pillar = stat.get("pillar", "money")
    accent = MONEY_ACCENT if pillar == "money" else LIFE_ACCENT

    slot = os.environ.get("SLOT", "").strip()
    template_name = TEMPLATE_BY_SLOT.get((pillar, slot), "line")

    fig = plt.figure(figsize=(FIG_W_PX / DPI, FIG_H_PX / DPI), dpi=DPI)
    fig.patch.set_facecolor(BRAND_BG)

    TEMPLATES[template_name](fig, stat, accent)

    # Visible source citation — the trust signal that separates this channel
    # from generic AI "fact" channels that don't (or can't) show their work.
    # Drawn once here, outside the per-template functions, so every
    # template guarantees it regardless of which layout was picked above.
    source = stat.get("source", "")
    if source:
        fig.text(
            0.5, 0.05, f"Source: {source}, {stat['last_year']}",
            ha="center", color=BRAND_TEXT, fontsize=13, alpha=0.75,
        )

    os.makedirs("assets", exist_ok=True)
    out_path = "assets/chart.png"
    fig.savefig(out_path, facecolor=BRAND_BG)
    plt.close(fig)
    print(f"[render_chart] Saved {out_path} (pillar={pillar}, slot={slot!r}, "
          f"template={template_name})")


if __name__ == "__main__":
    main()
