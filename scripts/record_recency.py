#!/usr/bin/env python3
"""
record_recency.py — Runs once per day, AFTER all four of today's
build-and-publish matrix jobs (see .github/workflows/daily-short.yml's
"record-recency" job). Reads each job's downloaded data/today_stat.json
(via actions/download-artifact) and appends {date, pillar, country,
indicator_code} to recency_history.json at the repo root, which
fetch_stat.py's build_candidates() reads back on future days to steer away
from repeats (see fetch_stat.py's RECENCY_FILE docstring for why this lives
at the repo root, not inside data/).

This is a SEPARATE, single job (not one of the four parallel matrix jobs),
specifically to avoid a git push race: four concurrent jobs each trying to
commit the same file would step on each other. Running the aggregation once,
serially, after the matrix completes avoids that entirely.

Usage: record_recency.py <YYYY-MM-DD> <artifacts_dir>

Never exits non-zero — a problem here (missing artifacts, corrupt JSON,
nothing new to record) should never fail the workflow run or block
tomorrow's video. Worst case: recency_history.json simply doesn't gain an
entry for today, and diversity exclusion is a little less complete until
the next successful day.
"""
import json
import os
import sys

RECENCY_FILE = "recency_history.json"
# Keep a generous buffer beyond fetch_stat.py's 7-day exclusion window, so
# the file also has some standing value as a plain history log, not just an
# exclusion cache.
KEEP_DAYS_OF_HISTORY = 30


def load_existing():
    if not os.path.exists(RECENCY_FILE):
        return []
    try:
        with open(RECENCY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as exc:  # noqa: BLE001 - never block the workflow
        print(f"[record_recency] Could not read existing {RECENCY_FILE}, "
              f"starting fresh: {exc}", file=sys.stderr)
        return []


def collect_todays_entries(date_str, artifacts_dir):
    entries = []
    if not os.path.isdir(artifacts_dir):
        print(f"[record_recency] No artifacts directory at {artifacts_dir!r} "
              f"— nothing to record today.", file=sys.stderr)
        return entries

    for name in sorted(os.listdir(artifacts_dir)):
        stat_path = os.path.join(artifacts_dir, name, "data", "today_stat.json")
        if not os.path.isfile(stat_path):
            continue
        try:
            with open(stat_path, "r", encoding="utf-8") as f:
                stat = json.load(f)
                entries.append({
                    "date": date_str,
                    "pillar": stat["pillar"],
                    "country": stat["country"],
                    "indicator_code": stat.get("indicator_code"),
                })
        except Exception as exc:  # noqa: BLE001 - one bad artifact must never block the rest
            print(f"[record_recency] Skipping unreadable artifact {name!r}: {exc}", file=sys.stderr)
            continue
    return entries


def main():
    if len(sys.argv) != 3:
        print("[record_recency] Usage: record_recency.py <YYYY-MM-DD> <artifacts_dir>", file=sys.stderr)
        return  # exit 0 — never fail the workflow over a usage mistake

    date_str, artifacts_dir = sys.argv[1], sys.argv[2]

    history = load_existing()
    new_entries = collect_todays_entries(date_str, artifacts_dir)

    if not new_entries:
        print("[record_recency] No new entries found for today — leaving "
              "recency_history.json unchanged.")
        return

    # Dedupe on (date, pillar, country, indicator_code) so re-running this
    # job (e.g. a workflow re-run) never produces repeated rows.
    seen = {(e.get("date"), e.get("pillar"), e.get("country"), e.get("indicator_code")) for e in history}
    for entry in new_entries:
        key = (entry["date"], entry["pillar"], entry["country"], entry["indicator_code"])
        if key not in seen:
            history.append(entry)
            seen.add(key)

    # Trim to the last KEEP_DAYS_OF_HISTORY distinct dates worth of entries.
    distinct_dates = sorted({e["date"] for e in history if "date" in e}, reverse=True)
    keep_dates = set(distinct_dates[:KEEP_DAYS_OF_HISTORY])
    history = [e for e in history if e.get("date") in keep_dates]
    history.sort(key=lambda e: (e.get("date", ""), e.get("pillar", ""), e.get("country", "")))

    with open(RECENCY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"[record_recency] Recorded {len(new_entries)} pick(s) for {date_str}; "
          f"{RECENCY_FILE} now holds {len(history)} entries across "
          f"{len(keep_dates)} day(s).")


if __name__ == "__main__":
    main()
