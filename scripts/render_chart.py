#!/usr/bin/env python3
"""
render_chart.py — Renders a branded chart PNG from the REAL numbers in
data/today_stat.json using matplotlib. Deliberately NOT an AI image model —
AI image generators cannot be trusted to draw numerically accurate charts
(they hallucinate values), so this stays 100% deterministic and free.

The small on-screen "Source: ..." caption is intentional, not decorative —
it's the channel's main visible difference from generic AI "fact" channels
that make numbers up: every "Proof in Numbers" video shows exactly where its
number came from.

Output: assets/chart.png (1080x1920 canvas, portrait, chart centered — ready
to be dropped straight into the vertical Short by assemble_video.sh).
"""
import json
import os

import matplotlib
matplotlib.use("Agg")  # headless — required on GitHub Actions runners
import matplotlib.pyplot as plt

# ---- Brand style: edit these two lines to re-skin the whole channel ----
BRAND_BG = "#0b0e14"
BRAND_ACCENT = "#e0b04a"
BRAND_TEXT = "#eef0f2"
FIG_W_PX, FIG_H_PX = 1080, 1920
DPI = 150


def main():
    with open("data/today_stat.json", "r", encoding="utf-8") as f:
        stat = json.load(f)

    years = [int(y) for y, _ in stat["series"]]
    values = [v for _, v in stat["series"]]

    fig = plt.figure(figsize=(FIG_W_PX / DPI, FIG_H_PX / DPI), dpi=DPI)
    fig.patch.set_facecolor(BRAND_BG)
    ax = fig.add_axes([0.12, 0.35, 0.76, 0.35])  # chart occupies the middle band
    ax.set_facecolor(BRAND_BG)

    ax.plot(years, values, color=BRAND_ACCENT, linewidth=4, marker="o", markersize=6)
    ax.fill_between(years, values, min(values), color=BRAND_ACCENT, alpha=0.12)

    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=BRAND_TEXT, labelsize=16)
    ax.grid(axis="y", color=BRAND_TEXT, alpha=0.08)

    title = f"{stat['country']} — {stat['indicator_label']}"
    fig.text(0.5, 0.74, title, ha="center", color=BRAND_TEXT, fontsize=20, wrap=True)

    change = stat.get("pct_change")
    if change is not None:
        sign = "+" if change >= 0 else ""
        fig.text(
            0.5, 0.27, f"{sign}{change}%  ({stat['first_year']} → {stat['last_year']})",
            ha="center", color=BRAND_ACCENT, fontsize=28, fontweight="bold",
        )

    # Visible source citation — the trust signal that separates this channel
    # from generic AI "fact" channels that don't (or can't) show their work.
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
    print(f"[render_chart] Saved {out_path}")


if __name__ == "__main__":
    main()
