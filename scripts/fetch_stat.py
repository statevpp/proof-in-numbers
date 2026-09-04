#!/usr/bin/env python3
"""
fetch_stat.py — Pulls a handful of candidate stats for "Proof in Numbers" from
free, unlimited public data sources, then asks Gemini to pick the single most
"surprising" one for today's Short. Fully automatic, no human input required.

The channel has exactly two content pillars (see 00_Project_Overview.md):
- "money" -> "Money in Your Life"       (World Bank Open Data)
- "life"  -> "Your Life by the Numbers" (World Bank + Our World in Data)

The channel publishes FOUR Shorts a day — two per pillar (see daily-short.yml,
which runs this whole pipeline as a 4-way matrix: money/1, money/2, life/1,
life/2). Two env vars, both optional, control that:

- FORCE_PILLAR ("money" or "life") — restricts every candidate this run
  considers to that one pillar, instead of picking randomly across both.
- SLOT ("1" or "2") — splits COUNTRY_POOL into two disjoint halves (even vs
  odd entries) so that the two same-pillar runs on the same day can never
  land on the same country, even though each matrix job's random state is
  otherwise completely independent of the other's. This is a cheap,
  deterministic way to guarantee two visibly different videos per pillar per
  day without any cross-job coordination (each matrix job is a separate,
  isolated GitHub Actions runner with no shared state).

Leaving both env vars unset reproduces the original single-video-per-day
behaviour exactly (fully random pillar + full country pool) — kept for local
testing / manual one-off runs.

Every candidate carries a "pillar" tag and a "framing_hint" string that tells
generate_script.py how to translate the raw number into something a regular
person feels in 3 seconds (money in their pocket, hours in their week, years
of their life) instead of raw economics/statistics jargon. That translation
rule is the single most important thing about this channel — see the
"mass-appeal filter" section in 00_Project_Overview.md for why it exists.

Free data sources used (all confirmed live and working, checked 2026-09-04):
- World Bank Open Data API  (https://data.worldbank.org/ — no key needed)
- Our World in Data (OWID) grapher CSV exports
  (https://ourworldindata.org/grapher/<slug>.csv — no key needed)

Output: writes data/today_stat.json with the chosen stat + the raw numbers,
so downstream scripts (generate_script.py, render_chart.py, assemble_video.sh,
upload_youtube.py) don't need to re-fetch anything, and can all read the
"pillar" field to stay consistent about which of the two pillars this video
belongs to.
"""
import csv
import io
import json
import os
import random
import sys
import urllib.request

import google_genai_helper as gh

# ---------------------------------------------------------------------------
# Pillar "money" — "Money in Your Life": salaries, prices, taxes, healthcare
# costs. Always translated by generate_script.py into personal money terms
# (never raw econ jargon like "GDP" or "% of GDP" spoken out loud).
# ---------------------------------------------------------------------------
MONEY_INDICATORS = [
    {
        "code": "NY.GDP.PCAP.CD",
        "label": "GDP per capita (current US$)",
        "framing_hint": "Translate as roughly how much money the average "
                         "person here earns in a year — never say 'GDP per "
                         "capita' out loud.",
    },
    {
        "code": "SL.UEM.TOTL.ZS",
        "label": "Unemployment rate (% of labor force)",
        "framing_hint": "Translate as: out of every 100 people who want a "
                         "job here, how many can't find one.",
    },
    {
        "code": "FP.CPI.TOTL.ZG",
        "label": "Inflation, consumer prices (annual %)",
        "framing_hint": "Translate as how much more expensive everyday "
                         "things — groceries, rent, gas — got in one year.",
    },
    {
        "code": "GC.TAX.TOTL.GD.ZS",
        "label": "Tax revenue (% of GDP)",
        "framing_hint": "Translate as roughly how many cents out of every "
                         "dollar earned in the country end up going to the "
                         "government.",
    },
    {
        "code": "SH.XPD.OOPC.CH.ZS",
        "label": "Out-of-pocket health expenditure (% of health spending)",
        "framing_hint": "Translate as how much of the bill YOU would "
                         "personally pay out of your own pocket if you got "
                         "sick here, versus what's covered for you.",
    },
    {
        "code": "GC.DOD.TOTL.GD.ZS",
        "label": "Government debt (% of GDP)",
        "framing_hint": "Translate as roughly how much debt is sitting "
                         "behind every dollar the country earns in a year.",
    },
]

# ---------------------------------------------------------------------------
# Pillar "life" — "Your Life by the Numbers": sleep, happiness, work hours,
# life expectancy. Always translated into years / hours-per-week / a feeling
# on a 0-10 scale a viewer can picture, never a bare index number.
# ---------------------------------------------------------------------------
LIFE_INDICATORS_WB = [
    {
        "code": "SP.DYN.LE00.IN",
        "label": "Life expectancy at birth (years)",
        "framing_hint": "Translate as how many years, on average, someone "
                         "born here today can expect to live.",
    },
]

LIFE_INDICATORS_OWID = [
    {
        "slug": "happiness-cantril-ladder",
        "label": "Self-reported life satisfaction (0-10 scale)",
        "framing_hint": "Translate as how happy people here say they are "
                         "with their lives overall, on a 0 (worst possible "
                         "life) to 10 (best possible life) scale — from the "
                         "World Happiness Report.",
        "source": "Our World in Data (World Happiness Report)",
    },
    {
        "slug": "annual-working-hours-per-worker",
        "label": "Annual working hours per worker",
        "framing_hint": "Divide by ~48 and talk in HOURS PER WEEK, so it's "
                         "something a viewer can picture from their own "
                         "week — never quote the big abstract yearly total "
                         "on its own.",
        "source": "Our World in Data",
    },
]

# A rotating pool of countries so the channel doesn't repeat the same one.
# Maps World Bank's ISO2 code to OWID's ISO3 code for the same country.
COUNTRY_POOL = {
    "BG": "BGR", "US": "USA", "DE": "DEU", "JP": "JPN", "CN": "CHN",
    "IN": "IND", "BR": "BRA", "NG": "NGA", "FR": "FRA", "GB": "GBR",
    "KR": "KOR", "ZA": "ZAF", "MX": "MEX", "SA": "SAU", "AU": "AUS",
    "CA": "CAN", "TR": "TUR", "PL": "POL", "EG": "EGY", "VN": "VNM",
}


def fetch_worldbank_series(country_code: str, indicator: str, years: int = 12):
    """World Bank API: no API key, no rate limit for this volume."""
    url = (
        f"https://api.worldbank.org/v2/country/{country_code}/indicator/"
        f"{indicator}?format=json&per_page={years}&mrnev={years}"
    )
    with urllib.request.urlopen(url, timeout=20) as resp:
        payload = json.load(resp)
    if len(payload) < 2 or not payload[1]:
        return None
    points = [(p["date"], p["value"]) for p in payload[1] if p["value"] is not None]
    points.sort(key=lambda p: p[0])
    return points


_OWID_CSV_CACHE: dict[str, str] = {}


def fetch_owid_series(iso3_code: str, slug: str, years: int = 12):
    """Our World in Data grapher CSV export: no API key. Caches the whole
    CSV per slug for the run so we don't re-download the same file once per
    candidate country."""
    if slug not in _OWID_CSV_CACHE:
        url = f"https://ourworldindata.org/grapher/{slug}.csv"
        with urllib.request.urlopen(url, timeout=30) as resp:
            _OWID_CSV_CACHE[slug] = resp.read().decode("utf-8")

    reader = csv.DictReader(io.StringIO(_OWID_CSV_CACHE[slug]))
    fieldnames = reader.fieldnames or []
    value_col = next((c for c in fieldnames if c not in ("Entity", "Code", "Year")), None)
    if not value_col:
        return None

    points = []
    for row in reader:
        if row.get("Code") != iso3_code:
            continue
        raw_val = row.get(value_col)
        if not raw_val:
            continue
        try:
            points.append((row["Year"], float(raw_val)))
        except ValueError:
            continue
    points.sort(key=lambda p: p[0])
    return points[-years:] if len(points) > years else points


def _finish_candidate(country_iso2: str, spec: dict, series, pillar: str, source: str):
    first_year, first_val = series[0]
    last_year, last_val = series[-1]
    pct_change = None
    if first_val:
        pct_change = round((last_val - first_val) / first_val * 100, 1)
    return {
        "country": country_iso2,
        "indicator_code": spec.get("code") or spec.get("slug"),
        "indicator_label": spec["label"],
        "framing_hint": spec["framing_hint"],
        "pillar": pillar,
        "series": series,
        "first_year": first_year,
        "first_value": first_val,
        "last_year": last_year,
        "last_value": last_val,
        "pct_change": pct_change,
        "source": source,
    }


def build_candidates(n: int = 8):
    """Pull n random candidates that actually have data.

    FORCE_PILLAR ("money"/"life") restricts which pillar's pools are drawn
    from — used by the 4-videos-a-day matrix in daily-short.yml so each
    matrix job produces a video for its assigned pillar instead of a random
    one. SLOT ("1"/"2") splits COUNTRY_POOL into two disjoint halves (even
    vs odd dict entries) so the two same-pillar matrix jobs running the same
    day can never both land on the same country — a cheap way to guarantee
    two visibly different videos per pillar per day without any
    coordination between the (fully independent) matrix job runners.

    Both env vars are optional; leaving them unset reproduces the original
    fully-random, full-country-pool behaviour (one video/day, either
    pillar) — kept for local testing and manual one-off runs.
    """
    candidates = []
    attempts = 0

    force_pillar = os.environ.get("FORCE_PILLAR", "").strip().lower() or None
    slot = os.environ.get("SLOT", "").strip()

    country_items = list(COUNTRY_POOL.items())
    if slot == "1":
        country_items = country_items[0::2]
    elif slot == "2":
        country_items = country_items[1::2]

    if force_pillar or slot:
        print(f"[fetch_stat] FORCE_PILLAR={force_pillar!r} SLOT={slot!r} "
              f"-> country pool size {len(country_items)}")

    while len(candidates) < n and attempts < n * 5:
        attempts += 1
        country_iso2, country_iso3 = random.choice(country_items)

        if force_pillar == "money":
            pool_choice = "money"
        elif force_pillar == "life":
            pool_choice = random.choice(["life_wb", "life_owid"])
        else:
            pool_choice = random.choice(["money", "life_wb", "life_owid"])

        try:
            if pool_choice == "money":
                spec = random.choice(MONEY_INDICATORS)
                series = fetch_worldbank_series(country_iso2, spec["code"])
                source, pillar = "World Bank Open Data", "money"
            elif pool_choice == "life_wb":
                spec = random.choice(LIFE_INDICATORS_WB)
                series = fetch_worldbank_series(country_iso2, spec["code"])
                source, pillar = "World Bank Open Data", "life"
            else:
                spec = random.choice(LIFE_INDICATORS_OWID)
                series = fetch_owid_series(country_iso3, spec["slug"])
                source, pillar = spec.get("source", "Our World in Data"), "life"
        except Exception as exc:  # noqa: BLE001 - one bad fetch must never kill the run
            print(f"[fetch_stat] Fetch failed for {country_iso2}/{pool_choice}: {exc}", file=sys.stderr)
            continue

        if not series or len(series) < 3:
            continue
        candidates.append(_finish_candidate(country_iso2, spec, series, pillar, source))

    return candidates


def pick_most_surprising(candidates):
    """Ask Gemini to rank candidates and pick the most 'surprising' one for a
    30-45 second Short aimed at a GENERAL audience with zero background in
    economics or statistics. Falls back to the candidate with the largest
    absolute percent change if the API call fails (never blocks the pipeline)."""
    try:
        prompt = (
            "You are picking which ONE statistic makes the best 30-45 second "
            "YouTube Shorts hook for \"Proof in Numbers\", a data-storytelling "
            "channel for a GENERAL audience (not economists, not data nerds). "
            "Given this JSON list of candidates, return ONLY the zero-based "
            "index (a single integer, nothing else) of the single most "
            "surprising, counter-intuitive stat that is ALSO easy to turn "
            "into a concrete personal comparison (money in someone's pocket, "
            "hours in their week, years of their life) rather than staying "
            "an abstract economic figure:\n\n" + json.dumps(candidates, default=str)
        )
        text = gh.generate_text(prompt).strip()
        idx = int("".join(ch for ch in text if ch.isdigit()) or "0")
        if 0 <= idx < len(candidates):
            return candidates[idx]
    except Exception as exc:  # noqa: BLE001 - pipeline must never hard-fail here
        print(f"[fetch_stat] Gemini pick failed, falling back to heuristic: {exc}", file=sys.stderr)

    scored = [c for c in candidates if c["pct_change"] is not None]
    if not scored:
        return candidates[0]
    return max(scored, key=lambda c: abs(c["pct_change"]))


def main():
    os.makedirs("data", exist_ok=True)

    # GitHub Actions runners are ephemeral — a retry of today's run is a
    # brand-new machine, so without this check a failed later step (e.g.
    # assemble_video.sh) would cause a retry to re-roll a DIFFERENT random
    # stat here, making the video inconsistent across debugging attempts.
    # daily-short.yml caches this "data" dir keyed by date + pillar + slot
    # (no restore-keys fallback — this repo's paths are NOT date-namespaced
    # like the sibling Lumaris pipeline's are, so a stale prior day's — or
    # prior slot's — cache must never be allowed to satisfy this check).
    if os.path.exists("data/today_stat.json"):
        print("[fetch_stat] data/today_stat.json already exists for today "
              "(restored from cache) — skipping re-fetch.")
        return

    candidates = build_candidates(n=8)
    if not candidates:
        print("[fetch_stat] No candidates fetched — all data sources failed.", file=sys.stderr)
        sys.exit(1)

    chosen = pick_most_surprising(candidates)
    with open("data/today_stat.json", "w", encoding="utf-8") as f:
        json.dump(chosen, f, ensure_ascii=False, indent=2)

    print(f"[fetch_stat] Chosen ({chosen['pillar']}): {chosen['country']} / "
          f"{chosen['indicator_label']} ({chosen['first_year']}: "
          f"{chosen['first_value']} -> {chosen['last_year']}: "
          f"{chosen['last_value']}, {chosen['pct_change']}%)")


if __name__ == "__main__":
    main()
