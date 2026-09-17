#!/usr/bin/env python3
"""
experiment_life_math.py -- ONE-OFF content generator for the 2026-09-17
"life math" manual content experiment (see PROJECT8 audit notes). This is
NOT part of the automated daily pipeline: it writes fixed, owner-approved
data/script.json + data/today_stat.json, and renders assets/chart.png, for
exactly one of two hardcoded variants (A or B). It does not read
fetch_stat.py or render_chart.py, and it never touches recency_history.json.

Usage: experiment_life_math.py <A|B>
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BRAND_BG = "#0b0e14"
BRAND_TEXT = "#eef0f2"
DIM_SHADE = "#3a4250"
LIFE_ACCENT = "#4fd1c5"

CONTENT = {
    "A": {
        "stat": {
            "pillar": "life",
            "country": "GLOBAL",
            "indicator_code": "experiment-years-at-work",
            "indicator_label": "Years Of A 43-Year Career Spent At Work",
            "source": "Illustrative calculation (40h/week x 47 weeks/year x 43 years), not an official statistic",
        },
        "script": {
            "hook": "If you work 40 hours a week from 22 to 65, here's how much of your real life goes to work.",
            "narration": "Work 40 hours a week, 47 weeks a year, for 43 years, and that adds up to 80,840 hours on the job. Stretched into one continuous block, with no sleep and no days off, that is about 9 point 2 years of your life spent entirely at work. That is longer than your whole childhood, from the day you were born until you turned 9. This is not an official statistic. It's simple math, using a standard 40 hour work week as the assumption. Comment your age and job below, and we will help you find your own number.",
            "title": "9 Years Of Your Life Go To This",
            "thumbnail_text": "9.2 YEARS",
            "description": "A simple calculation: 40 hours a week, 47 working weeks a year, for 43 years, equals about 9.2 continuous years of your life spent at work. This is an illustrative calculation based on a standard 40-hour work week assumption, not an official government or research statistic. Comment your age and job and we'll estimate yours.",
        },
        "chart": {"kind": "hero", "value": "9.2", "unit_label": "YEARS OF YOUR LIFE\nAT WORK"},
    },
    "B": {
        "stat": {
            "pillar": "life",
            "country": "GLOBAL",
            "indicator_code": "experiment-work-vs-sleep",
            "indicator_label": "Years Spent At Work Vs. Years Spent Asleep",
            "source": "Illustrative calculation (40h/week work, 8h/night sleep), not an official statistic",
        },
        "script": {
            "hook": "9 years of your life. That's how much work takes. Here's what it's up against.",
            "narration": "If you work a standard 40 hour week for 43 years, that is about 9 point 2 continuous years of your life at work. Now compare that to sleep. At 8 hours a night, over a similar lifetime, that is roughly 26 years spent asleep. Work takes a huge chunk of your waking life, but it's still less than a third of what sleep takes. This is simple math, not an official statistic, just a standard 40 hour week and 8 hours of sleep a night as the assumptions. Want your real number? Comment your age and job below.",
            "title": "Work Vs Sleep: Years Of Your Life",
            "thumbnail_text": "WORK VS SLEEP",
            "description": "A simple comparison: about 9.2 continuous years of a 43-year working life (40 hours/week) versus roughly 26 years spent asleep (8 hours/night). These are illustrative calculations based on standard assumptions, not official statistics. Comment your age and job and we'll estimate your own numbers.",
        },
        "chart": {"kind": "bars", "labels": ["WORK", "SLEEP"], "values": [9.2, 26], "unit": "yrs"},
    },
}

def draw_hero(fig, value, unit_label):
    fig.text(0.5, 0.74, "GLOBAL", ha="center", color=BRAND_TEXT, fontsize=26, fontweight="bold")
    fig.text(0.5, 0.52, value, ha="center", va="center", color=LIFE_ACCENT, fontsize=140, fontweight="bold")
    fig.text(0.5, 0.38, unit_label, ha="center", color=BRAND_TEXT, fontsize=22, wrap=True)


def draw_bars(fig, labels, values, unit):
    ax = fig.add_axes([0.20, 0.34, 0.60, 0.36])
    ax.set_facecolor(BRAND_BG)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(labels, color=BRAND_TEXT, fontsize=20, fontweight="bold")
    ax.set_yticks([])
    colors = [LIFE_ACCENT, DIM_SHADE]
    bars = ax.bar([0, 1], values, width=0.5, color=colors)
    vmax = max(values)
    ax.set_ylim(0, vmax * 1.3)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + vmax * 0.04,
                f"{val:g} {unit}", ha="center", color=BRAND_TEXT, fontsize=18, fontweight="bold")
    fig.text(0.5, 0.76, "A 43-Year Working Life", ha="center", color=BRAND_TEXT, fontsize=20)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in CONTENT:
        print("Usage: experiment_life_math.py <A|B>", file=sys.stderr)
        sys.exit(1)
    variant = sys.argv[1]
    data = CONTENT[variant]

    os.makedirs("data", exist_ok=True)
    with open("data/today_stat.json", "w", encoding="utf-8") as f:
        json.dump(data["stat"], f, ensure_ascii=False, indent=2)
    with open("data/script.json", "w", encoding="utf-8") as f:
        json.dump(data["script"], f, ensure_ascii=False, indent=2)

    fig = plt.figure(figsize=(1080 / 150, 1920 / 150), dpi=150)
    fig.patch.set_facecolor(BRAND_BG)
    chart = data["chart"]
    if chart["kind"] == "hero":
        draw_hero(fig, chart["value"], chart["unit_label"])
    else:
        draw_bars(fig, chart["labels"], chart["values"], chart["unit"])

    source = data["stat"]["source"]
    fig.text(0.5, 0.05, source, ha="center", color=BRAND_TEXT, fontsize=11, alpha=0.75, wrap=True)

    os.makedirs("assets", exist_ok=True)
    fig.savefig("assets/chart.png", facecolor=BRAND_BG)
    plt.close(fig)
    print(f"[experiment_life_math] Wrote data/today_stat.json, data/script.json, assets/chart.png for variant {variant}")


if __name__ == "__main__":
    main()
