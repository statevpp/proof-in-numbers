#!/usr/bin/env python3
"""
fetch_stat.py — Pulls a handful of candidate stats for "Proof in Numbers" from
free, unlimited public data sources, then asks Gemini to pick the single most
"surprising" one for today's Short. Fully automatic, no human input required.

STRATEGY UPDATE (2026-09-27) — ESTA.QUEST integration
=======================================================
The channel moved from a 2-pillar x 2-slot matrix (money/1, money/2, life/1,
life/2 — 4 videos/day, but only 2 distinct content pillars) to FOUR distinct
content pillars, one video each, per Pepi's "PROOF IN NUMBERS CONTENT
STRATEGY — ESTA.QUEST INTEGRATION" directive:

- "global_viral"        -> "Global Viral"          (money, business, economy,
  tech/science, surprising World Bank stats — was "money")
- "global_data_story"   -> "Global Data Story"     (life expectancy,
  happiness, work hours — was "life")
- "real_estate_global"  -> "Real Estate Intelligence" (NEW — house-price
  trends for a random country OTHER than Bulgaria, broad global appeal)
- "real_estate_sofia"   -> "Sofia Property Intelligence" (NEW — Bulgaria's
  official house-price index, framed for Sofia buyers/sellers; the ONLY
  pillar where an ESTA.QUEST mention belongs, and only ever a brief,
  natural, non-salesy one in the YouTube description — see
  generate_script.py's REAL_ESTATE_SOFIA_EXTRA)

Because each pillar now produces exactly ONE video/day (not two), the old
SLOT env var (which split COUNTRY_POOL in half so two same-pillar jobs never
picked the same country) is GONE — there is no longer a same-day collision
to avoid. FORCE_PILLAR is now effectively required (daily-short.yml's matrix
always sets it to one of the four pillar names above); leaving it unset
still works for local testing (falls back to fully random legacy behaviour
across all four pillars).

Real-estate data source: Eurostat's official House Price Index
(prc_hpi_a, purchase=TOTAL, https://ec.europa.eu/eurostat/api/...) — a
free, no-key, official-statistics API confirmed live 2026-09-27. This is
REAL, VERIFIED, government-sourced data (2015=100 index + the annual rate
of change), never a fabricated or estimated number — satisfies Pepi's
"do not fabricate Bulgarian/Sofia real-estate statistics" rule by
construction: nothing is ever invented, only official index values and
their already-published rate of change are read straight from the API.
Coverage is EU/EEA/UK/Turkey/Balkans (~31 countries, no aggregates) — this
is a genuine scope limit of the only free, key-less, always-available
official house-price API found; it does not reach the US/China/etc. Noted
as a known limitation in project_8_storytelling_shorts.md, not hidden.

The two original pillars ("money" / "life") keep their original World Bank
+ OWID indicator pools untouched, just renamed and (for global_viral) two
new World Bank indicators added for a bit more "science/tech" variety in
line with the strategy brief's broader Video-1 topic list.
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
# Pillar "global_viral" (was "money") — "Global Viral": money, business,
# economics, tech/science, surprising World Bank stats. Always translated by
# generate_script.py into personal, concrete terms (never raw econ jargon
# like "GDP" or "% of GDP" spoken out loud).
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
    {
        "code": "IT.NET.USER.ZS",
        "label": "Individuals using the Internet (% of population)",
        "framing_hint": "Translate as: out of every 100 people here, how "
                         "many are online — good for a 'you'd assume "
                         "everyone is online by now, but...' surprise angle.",
    },
    {
        "code": "GB.XPD.RSDV.GD.ZS",
        "label": "Research and development expenditure (% of GDP)",
        "framing_hint": "Translate as roughly how many cents out of every "
                         "$100 the whole country earns gets spent inventing "
                         "new technology and science — never say 'R&D "
                         "expenditure as a percent of GDP' out loud.",
    },
]

# ---------------------------------------------------------------------------
# Pillar "global_data_story" (was "life") — "Global Data Story": sleep,
# happiness, work hours, life expectancy. Always translated into years /
# hours-per-week / a feeling on a 0-10 scale a viewer can picture, never a
# bare index number.
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

# A rotating pool of countries so global_viral / global_data_story don't
# repeat the same one. Maps World Bank's ISO2 code to OWID's ISO3 code for
# the same country.
COUNTRY_POOL = {
    "BG": "BGR", "US": "USA", "DE": "DEU", "JP": "JPN", "CN": "CHN",
    "IN": "IND", "BR": "BRA", "NG": "NGA", "FR": "FRA", "GB": "GBR",
    "KR": "KOR", "ZA": "ZAF", "MX": "MEX", "SA": "SAU", "AU": "AUS",
    "CA": "CAN", "TR": "TUR", "PL": "POL", "EG": "EGY", "VN": "VNM",
}

# ---------------------------------------------------------------------------
# Pillar "real_estate_global" / "real_estate_sofia" (NEW, 2026-09-27) —
# Eurostat's official House Price Index (prc_hpi_a), unit=I15_A_AVG
# (2015=100) throughout. All three "purchase" variants below are on that
# SAME 2015=100 basis, so the generic pct_change math in _finish_candidate()
# (first_value -> last_value) stays a mathematically honest "homes here
# cost X% more/less now than in <first_year>" for every one of them — never
# a percent-change-of-a-percent. (An earlier draft also tried Eurostat's
# RCH_A_AVG "already a % rate of change" unit for variety; dropped because
# running it through the same pct_change formula would silently compute a
# percent-change-of-a-percentage — e.g. a rate moving from 7% to 14.6% is
# NOT "108% more expensive homes" — a real accuracy risk this channel's
# whole premise exists to avoid. TOTAL/DW_NEW/DW_EXST have no such trap:
# they're all directly comparable index levels.) Confirmed live via direct
# API calls, 2026-09-27 (TOTAL, DW_NEW and DW_EXST all have solid coverage
# across the country pool below).
# ---------------------------------------------------------------------------
REAL_ESTATE_UNITS = [
    {
        "purchase": "TOTAL",
        "label": "House Price Index — all dwellings (2015 = 100)",
        "framing_hint": "Translate the index level into 'homes here now "
                         "cost roughly X% more (or less) than they did in "
                         "<first_year>' — subtract 100 from the LATEST "
                         "index value only if first_year is 2015; "
                         "otherwise just use the first_value->last_value "
                         "percent change already given. Never say 'index, "
                         "2015=100' out loud.",
    },
    {
        "purchase": "DW_NEW",
        "label": "House Price Index — newly built dwellings (2015 = 100)",
        "framing_hint": "Translate as how much more (or less) it costs to "
                         "buy a brand-NEW home here now vs <first_year> — "
                         "say 'newly built homes', never 'index, 2015=100'.",
    },
    {
        "purchase": "DW_EXST",
        "label": "House Price Index — existing (resale) dwellings (2015 = 100)",
        "framing_hint": "Translate as how much more (or less) it costs to "
                         "buy an already-existing, resale home here now vs "
                         "<first_year> — say 'resale homes', never 'index, "
                         "2015=100'.",
    },
]

# Eurostat's real, ISO-alpha-2-ish geo codes for the House Price Index
# dataset (confirmed live 2026-09-27) — EU + EEA + UK + Türkiye, i.e. every
# country Eurostat actually publishes this series for. Aggregates (EU, EA,
# EU27_2020, etc.) are deliberately excluded — only real countries. NOTE:
# Eurostat uses "UK" and "EL" (not ISO's "GB"/"GR") — kept as Eurostat spells
# them since that's what the API call and this pillar's own country_iso2
# field need to round-trip correctly.
REAL_ESTATE_COUNTRY_POOL = [
    "BE", "BG", "CZ", "DK", "DE", "EE", "IE", "ES", "FR", "HR", "IT", "CY",
    "LV", "LT", "LU", "HU", "MT", "NL", "AT", "PL", "PT", "RO", "SI", "SK",
    "FI", "SE", "IS", "NO", "CH", "UK", "TR",
]

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"

# ---------------------------------------------------------------------------
# Recency exclusion — avoids picking the same country for the same pillar on
# back-to-back days (confirmed in practice: Turkey/inflation picked two days
# running, 2026-09-06 and 2026-09-07 — different numbers each time, but a
# repeat from the viewer's perspective). The workflow's "record-recency" job
# (see .github/workflows/daily-short.yml) appends one entry per published
# video to this file and commits it back to the repo after each day's runs,
# so every matrix job starts from yesterday's (and earlier days') picks
# already checked out fresh from git — no coordination between jobs needed.
#
# This file lives at the repo root, NOT inside data/, so it is never touched
# by the actions/cache step (which only restores data/, audio/, assets/,
# keyed by date+pillar), so it is purely git-tracked history, unrelated to a
# single day's ephemeral cache.
#
# EXCEPTION: "real_estate_sofia" always uses country "BG" by design (see
# module docstring) — there is no country to diversify for that pillar, so
# recency exclusion is skipped for it entirely (see build_candidates()).
# Variety for that pillar instead comes from REAL_ESTATE_UNITS.
# ---------------------------------------------------------------------------
RECENCY_FILE = "recency_history.json"
RECENCY_WINDOW_DAYS = 7


def load_recency_history():
    """Best-effort read of the recency log. Any problem (missing file,
    corrupt JSON, wrong shape) must never block the pipeline — it just means
    no exclusion happens this run, same as before this feature existed."""
    if not os.path.exists(RECENCY_FILE):
        return []
    try:
        with open(RECENCY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        if not isinstance(history, list):
            return []
        return history
    except Exception as exc:  # noqa: BLE001 - must never block the pipeline
        print(f"[fetch_stat] Could not read {RECENCY_FILE}, ignoring: {exc}", file=sys.stderr)
        return []


def recently_used_countries(history, window_days=RECENCY_WINDOW_DAYS):
    """Returns the set of (pillar, country_iso2) pairs used within the last
    `window_days` days, so build_candidates() can steer away from them."""
    import datetime as _dt

    today = _dt.datetime.now(_dt.timezone.utc).date()
    used = set()
    for entry in history:
        try:
            entry_date = _dt.date.fromisoformat(entry["date"])
            if (today - entry_date).days <= window_days:
                used.add((entry["pillar"], entry["country"]))
        except Exception:  # noqa: BLE001 - one bad entry must never block the pipeline
            continue
    return used


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


_EUROSTAT_CACHE: dict[str, dict] = {}


def fetch_eurostat_hpi_series(geo_code: str, purchase: str, years: int = 10):
    """Eurostat's official House Price Index (prc_hpi_a, unit=I15_A_AVG,
    i.e. 2015=100). No API key, free, official government/EU statistics —
    confirmed live 2026-09-27. Returns [(year_str, value_float), ...] sorted
    ascending, or None if this geo/purchase combination has no published
    data (some smaller countries have gaps for some years/purchase types —
    treated as a normal skip, same as a World Bank/OWID miss)."""
    cache_key = f"{geo_code}:{purchase}"
    if cache_key not in _EUROSTAT_CACHE:
        url = (
            f"{EUROSTAT_BASE}/prc_hpi_a?format=JSON&geo={geo_code}"
            f"&purchase={purchase}&unit=I15_A_AVG&lang=EN"
        )
        with urllib.request.urlopen(url, timeout=25) as resp:
            _EUROSTAT_CACHE[cache_key] = json.load(resp)

    payload = _EUROSTAT_CACHE[cache_key]
    time_dim = payload.get("dimension", {}).get("time", {}).get("category", {})
    index_by_time = time_dim.get("index", {})
    values = payload.get("value", {})
    if not index_by_time or not values:
        return None

    # JSON-stat: value is a sparse dict keyed by the FLAT integer position
    # (as a string) across all dimensions. Since this call fixes every other
    # dimension (freq=A implicit, purchase=TOTAL, unit=<one>, geo=<one>) to a
    # single category each, the "time" dimension's own index IS the flat
    # position directly (size = [1,1,1,1,N_years]) — confirmed against a
    # live BG response on 2026-09-27 (21 time points -> 21 values, positions
    # 0..20 matching the time labels in order).
    points = []
    for year_label, pos in index_by_time.items():
        raw_val = values.get(str(pos))
        if raw_val is None:
            continue
        try:
            points.append((year_label, float(raw_val)))
        except (TypeError, ValueError):
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
        "indicator_code": spec.get("code") or spec.get("slug") or spec.get("purchase"),
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


def _build_real_estate_candidates(n: int, pillar: str, exclude: set) -> list:
    """real_estate_global draws a random country (any Eurostat HPI country
    EXCEPT Bulgaria, which is reserved for real_estate_sofia) each day.
    real_estate_sofia always uses Bulgaria — see module docstring for why
    recency exclusion is skipped for it (there is no country to rotate)."""
    candidates = []
    attempts = 0

    if pillar == "real_estate_sofia":
        country_choices = ["BG"]
    else:
        country_choices = [c for c in REAL_ESTATE_COUNTRY_POOL if c != "BG"]

    while len(candidates) < n and attempts < n * 6:
        attempts += 1
        country = random.choice(country_choices)

        if pillar != "real_estate_sofia" and (pillar, country) in exclude:
            continue

        unit_spec = random.choice(REAL_ESTATE_UNITS)
        try:
            series = fetch_eurostat_hpi_series(country, unit_spec["purchase"])
        except Exception as exc:  # noqa: BLE001 - one bad fetch must never kill the run
            print(f"[fetch_stat] Eurostat fetch failed for {country}/{unit_spec['purchase']}: {exc}",
                  file=sys.stderr)
            continue

        if not series or len(series) < 3:
            continue
        candidates.append(_finish_candidate(country, unit_spec, series, pillar,
                                             "Eurostat (official House Price Index)"))

    return candidates


def build_candidates(n: int = 8, exclude: set | None = None):
    """Pull n random candidates that actually have data.

    FORCE_PILLAR (one of "global_viral", "global_data_story",
    "real_estate_global", "real_estate_sofia") restricts which pool this
    run draws from — daily-short.yml's matrix always sets it, one job per
    pillar, so each of today's 4 videos belongs to a different pillar. Left
    unset, this reproduces the original single-video-per-day fully-random
    behaviour across ALL four pillars (kept for local testing only).

    `exclude` is an optional set of (pillar, country_iso2) pairs to steer
    away from (see recently_used_countries()) — a candidate landing on one
    of these is simply skipped and another attempt made, so it only ever
    narrows the choice, never fails the run. Not applied to
    "real_estate_sofia" (see module docstring — that pillar has no country
    to rotate).
    """
    exclude = exclude or set()
    force_pillar = os.environ.get("FORCE_PILLAR", "").strip().lower() or None

    if force_pillar:
        print(f"[fetch_stat] FORCE_PILLAR={force_pillar!r}")

    if force_pillar in ("real_estate_global", "real_estate_sofia"):
        return _build_real_estate_candidates(n, force_pillar, exclude)

    if force_pillar is None:
        # Legacy/local-testing path: fully random across every pillar.
        real_estate_pillar = random.choice(["real_estate_global", "real_estate_sofia"])
        pool = (["global_viral"] * 2 + ["global_data_story"] * 2
                + [real_estate_pillar])
        force_pillar = random.choice(pool)
        if force_pillar in ("real_estate_global", "real_estate_sofia"):
            return _build_real_estate_candidates(n, force_pillar, exclude)

    candidates = []
    attempts = 0

    while len(candidates) < n and attempts < n * 5:
        attempts += 1
        country_iso2, country_iso3 = random.choice(list(COUNTRY_POOL.items()))

        if force_pillar == "global_viral":
            likely_pillar = "global_viral"
        elif force_pillar == "global_data_story":
            likely_pillar = "global_data_story"
        else:
            likely_pillar = None
        if likely_pillar and (likely_pillar, country_iso2) in exclude:
            continue

        if force_pillar == "global_viral":
            pool_choice = "money"
        elif force_pillar == "global_data_story":
            pool_choice = random.choice(["life_wb", "life_owid"])
        else:
            pool_choice = random.choice(["money", "life_wb", "life_owid"])

        try:
            if pool_choice == "money":
                spec = random.choice(MONEY_INDICATORS)
                series = fetch_worldbank_series(country_iso2, spec["code"])
                source, pillar = "World Bank Open Data", "global_viral"
            elif pool_choice == "life_wb":
                spec = random.choice(LIFE_INDICATORS_WB)
                series = fetch_worldbank_series(country_iso2, spec["code"])
                source, pillar = "World Bank Open Data", "global_data_story"
            else:
                spec = random.choice(LIFE_INDICATORS_OWID)
                series = fetch_owid_series(country_iso3, spec["slug"])
                source, pillar = spec.get("source", "Our World in Data"), "global_data_story"
        except Exception as exc:  # noqa: BLE001 - one bad fetch must never kill the run
            print(f"[fetch_stat] Fetch failed for {country_iso2}/{pool_choice}: {exc}", file=sys.stderr)
            continue

        if not series or len(series) < 3:
            continue
        if (pillar, country_iso2) in exclude:
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
    # daily-short.yml caches this "data" dir keyed by date + pillar (no
    # restore-keys fallback — this repo's paths are NOT date-namespaced like
    # the sibling Lumaris pipeline's are, so a stale prior day's — or prior
    # pillar's — cache must never be allowed to satisfy this check).
    if os.path.exists("data/today_stat.json"):
        print("[fetch_stat] data/today_stat.json already exists for today "
              "(restored from cache) — skipping re-fetch.")
        return

    exclude = recently_used_countries(load_recency_history())
    if exclude:
        print(f"[fetch_stat] Steering away from {len(exclude)} recently-used "
              f"(pillar, country) pair(s) from the last {RECENCY_WINDOW_DAYS} days: {sorted(exclude)}")

    candidates = build_candidates(n=8, exclude=exclude)
    if not candidates and exclude:
        # Extremely unlikely with these pool sizes, but a video going out
        # with a repeated country is always better than no video at all —
        # never let the diversity feature block the pipeline.
        print("[fetch_stat] No candidates left after recency exclusion — "
              "retrying without it rather than failing the run.", file=sys.stderr)
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
