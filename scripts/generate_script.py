#!/usr/bin/env python3
"""
generate_script.py — Turns data/today_stat.json into a finished English
script for "Proof in Numbers": hook, narration, title, thumbnail text, and
YouTube description.

Two automatic self-checks run before anything is saved (no human review):
1. Mass-appeal / jargon check — a plain deterministic keyword scan (see
   BANNED_JARGON below). This is the channel's core rule: every stat must be
   translated into something a regular person feels in 3 seconds (money in
   their pocket, hours in their week, years of their life), never left as
   raw economics/statistics jargon like "GDP" or "% of GDP".
2. Fact-check — a second Gemini call that compares the script against the
   raw numbers (the "self-check" step from the plan).

If either check fails, we regenerate ONCE with a stricter instruction; if it
fails again we let the workflow fail the run rather than publish something
wrong or off-brand (fail loud, not silent).

Output: data/script.json
"""
import json
import os
import sys

import google_genai_helper as gh

PILLAR_NAMES = {
    "global_viral": "Global Viral",
    "global_data_story": "Global Data Story",
    "real_estate_global": "Real Estate Intelligence",
    "real_estate_sofia": "Sofia Property Intelligence",
}

# One extra sentence appended to the WRITER_PROMPT only for the two real
# estate pillars (added 2026-09-27, ESTA.QUEST integration strategy) — the
# channel's core rule (never economic jargon, always a personal comparison)
# still applies in full; this only tells Gemini the SUBJECT is housing, not
# generic money/life.
REAL_ESTATE_EXTRA = """
This video is about HOUSING / REAL ESTATE prices specifically (not generic
personal finance). Frame the hook and narration around what it costs to buy
a home — never use the words "index" or "2015=100" out loud; always convert
to a plain "homes here cost roughly X% more than they used to" or "buying a
home here got X% more expensive" sentence, using the percent-change number
already given in the raw stat.
"""

# Appended ONLY for pillar "real_estate_sofia" — the ONE pillar where a
# brief, natural ESTA.QUEST mention belongs (2026-09-27 strategy: "ESTA.QUEST
# should NOT be inserted as an artificial advertisement into every video...
# may be mentioned briefly or used as a subtle CTA, but never at the expense
# of the video's entertainment/information value"). Deliberately placed in
# the "description" field only, NEVER in the hook/narration/title — so the
# spoken video itself stays 100% pure entertainment/information and the
# mention only shows up as one soft, optional line in the YouTube
# description below the video, exactly like a footnote/credit, not an ad
# read. Gemini is told this is OPTIONAL so a day where it doesn't fit
# naturally can just skip it rather than forcing something salesy.
REAL_ESTATE_SOFIA_EXTRA = """
This is Bulgaria's official nationwide house-price data — mention in the
narration that Sofia (the capital) drives a large share of this national
market, but do NOT claim this number IS a Sofia-only figure (it isn't —
be honest that it's the national index).

For the "description" field ONLY (never in hook/title/narration): after
the required 2-3 sentences crediting the data source, you MAY optionally
add ONE short, natural, non-salesy sentence mentioning that ESTA.QUEST
(a Sofia property resource) can help viewers interested in the Sofia
market explore current listings or values — but ONLY if it reads as a
genuinely helpful footnote, never as an ad. If it would feel forced or
salesy for this specific stat, skip it entirely and just write the normal
2-3 sentence description. Never mention ESTA.QUEST anywhere except
optionally in this one description sentence.
"""

# Raw academic/technical terms that must NEVER survive into what the viewer
# hears or reads — if the raw stat is phrased this way, the writer prompt
# below instructs Gemini to translate it, and this list is the deterministic
# safety net that catches it if the translation didn't happen.
BANNED_JARGON = [
    "gdp", "per capita", "gini", "% of gdp", "consumer price index", "cpi",
    "oecd", "basis points", "percentile", "quartile",
    # Added 2026-09-27 for the real-estate pillars — Eurostat's House Price
    # Index is a "2015=100" index, and the writer prompt requires it always
    # be translated into a plain percent-more/less-expensive sentence.
    "2015=100", "house price index", "hpi",
]

WRITER_PROMPT = """You are the scriptwriter for "Proof in Numbers", a faceless,
English-language data-storytelling YouTube Shorts / TikTok / Reels channel
for a GLOBAL, GENERAL audience — regular people scrolling their phone, NOT
economists or data nerds.

The channel publishes 4 videos/day across four content pillars:
- "Global Viral": money, business, economy, tech/science — surprising stats
- "Global Data Story": sleep, happiness, work hours, life expectancy
- "Real Estate Intelligence": housing prices anywhere in the world
- "Sofia Property Intelligence": Bulgaria's housing market, for Sofia buyers/sellers

This stat belongs to the "{pillar_name}" pillar.
{pillar_extra}

THE MOST IMPORTANT RULE (mass-appeal filter): every sentence must pass this
test — "would someone with zero interest in economics or statistics
instantly feel why this matters to THEM, within 3 seconds?" Never use raw
academic/technical terms. Always translate the raw number into something
concrete and personal: money in someone's pocket, hours in a day/week/year,
years of a life, or "X out of every 100 people".

NEVER use these words (or close equivalents) in the hook, title, or
narration: GDP, "per capita", inflation index, CPI, Gini, "% of GDP", basis
points, percentile, OECD. If the raw stat below is phrased in one of these
terms, convert it into a plain-language personal comparison before writing
anything.

How to translate THIS specific stat: {framing_hint}

Raw stat (for the real numbers only — never invent numbers not present here):
{stat_json}

Return ONLY valid JSON (no markdown fences), with these exact keys:
- "hook": one punchy opening sentence (English, max 20 words), plain
  language, zero jargon
- "narration": the full spoken script, 35-45 seconds when read aloud
  (roughly 90-120 words), English, plain sentences a 12-year-old would
  understand, NO markdown, NO stage directions, written for the EAR not the
  eye
- "title": YouTube title, max 60 characters, English, plain language
- "thumbnail_text": max 5 words, English, all-caps is fine, plain language
- "description": 2-3 sentences for the YouTube description, English, must
  credit the data source by name (the source is given in the raw stat above)
"""

FACT_CHECK_PROMPT = """You are a fact-checker. Compare this generated script against the raw
data it is supposed to be based on. Return ONLY valid JSON (no markdown
fences) with exactly two keys:
- "accurate": true or false — false if any number, year, or direction of
  change (increase/decrease) in the script contradicts the raw data
- "issues": a short string describing the problem if accurate is false,
  otherwise an empty string

Raw stat:
{stat_json}

Generated script:
{script_json}
"""


def find_jargon(script: dict) -> list:
    """Deterministic mass-appeal check: scan the viewer-facing text for
    banned jargon terms. Cheap, reliable, and doesn't depend on Gemini
    correctly judging its own output."""
    haystack = " ".join([
        script.get("hook", ""),
        script.get("title", ""),
        script.get("narration", ""),
    ]).lower()
    return [term for term in BANNED_JARGON if term in haystack]


def main():
    # Same ephemeral-runner retry logic as fetch_stat.py: if a later step
    # failed and this run is being retried the same day, reuse the already
    # fact-checked script instead of paying for + re-rolling new Gemini
    # calls (and risking a DIFFERENT script than the one render_chart.py's
    # chart / generate_voice.py's voice will end up describing).
    if os.path.exists("data/script.json"):
        print("[generate_script] data/script.json already exists for today "
              "(restored from cache) — skipping regeneration.")
        return

    with open("data/today_stat.json", "r", encoding="utf-8") as f:
        stat = json.load(f)

    pillar = stat.get("pillar", "global_viral")
    pillar_name = PILLAR_NAMES.get(pillar, PILLAR_NAMES["global_viral"])
    framing_hint = stat.get(
        "framing_hint",
        "Translate this into a concrete, personal comparison — money in "
        "someone's pocket, hours in their week, or years of their life.",
    )
    stat_json = json.dumps(stat, ensure_ascii=False, default=str)

    pillar_extra = ""
    if pillar == "real_estate_global":
        pillar_extra = REAL_ESTATE_EXTRA
    elif pillar == "real_estate_sofia":
        pillar_extra = REAL_ESTATE_EXTRA + REAL_ESTATE_SOFIA_EXTRA

    def write(extra_instruction: str = ""):
        prompt = WRITER_PROMPT.format(
            pillar_name=pillar_name, pillar_extra=pillar_extra,
            framing_hint=framing_hint, stat_json=stat_json,
        )
        if extra_instruction:
            prompt += "\n\nIMPORTANT: " + extra_instruction
        return gh.generate_json(prompt)

    def check(script: dict) -> list:
        issues = []
        jargon = find_jargon(script)
        if jargon:
            issues.append(
                "Uses jargon a general audience won't relate to: "
                + ", ".join(jargon) + ". Rewrite using plain, personal terms."
            )
        fact = gh.generate_json(
            FACT_CHECK_PROMPT.format(
                stat_json=stat_json, script_json=json.dumps(script, ensure_ascii=False)
            )
        )
        if not fact.get("accurate", False):
            issues.append(fact.get("issues") or "Factual mismatch with the raw data.")
        return issues

    script = write()
    issues = check(script)

    if issues:
        print(f"[generate_script] Self-check failed: {'; '.join(issues)} — retrying once.",
              file=sys.stderr)
        script = write("a previous attempt had these problems, avoid them: " + "; ".join(issues))
        issues2 = check(script)
        if issues2:
            print(f"[generate_script] Self-check failed twice: {'; '.join(issues2)} "
                  f"— failing the run instead of publishing a bad or off-brand video.",
                  file=sys.stderr)
            sys.exit(1)

    with open("data/script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    print(f"[generate_script] OK ({pillar_name}): \"{script['title']}\"")


if __name__ == "__main__":
    main()
