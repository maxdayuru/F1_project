import argparse
import json
import math
import os

import fastf1
import pandas as pd

# F1 Lab track key  ->  official event name as FastF1 knows it
EVENTS = {
    "monza": "Italian Grand Prix",
    "silverstone": "British Grand Prix",
    "monaco": "Monaco Grand Prix",
    "spa": "Belgian Grand Prix",
    "suzuka": "Japanese Grand Prix",
    "interlagos": "São Paulo Grand Prix",
    "yas": "Abu Dhabi Grand Prix",
    "cota": "United States Grand Prix",
}


def finite(x):
    """True for real numbers (not None, NaN or NaT)."""
    try:
        return x is not None and not pd.isna(x) and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def load_race(year, event):
    """Download one race and return {'event': ..., 'laps': [...], 'results': [...]}."""
    session = fastf1.get_session(year, event, "R")
    session.load(telemetry=False, weather=False, messages=False)

    laps = []
    for _, r in session.laps.iterrows():
        if not finite(r["LapTime"].total_seconds() if pd.notna(r["LapTime"]) else None):
            continue  # lap with no recorded time
        # A lap is "pit" if the car entered or left the pits on it (both are slow laps).
        pit = pd.notna(r["PitInTime"]) or pd.notna(r["PitOutTime"])
        laps.append({
            "team": str(r["Team"]),
            "driver": str(r["Driver"]),
            "lap": int(r["LapNumber"]),
            "time": round(r["LapTime"].total_seconds(), 3),
            "compound": str(r["Compound"]).upper() if pd.notna(r["Compound"]) else "UNKNOWN",
            "age": int(r["TyreLife"]) if finite(r["TyreLife"]) else 1,
            "pit": bool(pit),
            "pitIn": bool(pd.notna(r["PitInTime"])),   # in-lap only: one per stop
        })

    results = []
    for _, r in session.results.iterrows():
        results.append({
            "driver": str(r["Abbreviation"]),
            "team": str(r["TeamName"]),
            "position": int(r["Position"]) if finite(r["Position"]) else 99,
            "points": float(r["Points"]) if finite(r["Points"]) else 0,
        })
    return {"event": f"{session.event['EventName']} {year}", "laps": laps, "results": results}


def main():
    ap = argparse.ArgumentParser(description="Export F1 race data for F1 Lab")
    ap.add_argument("--year", type=int, required=True, help="season, e.g. 2024")
    ap.add_argument("--tracks", nargs="*", default=list(EVENTS), help="track keys (default: all 8)")
    ap.add_argument("--out", default="f1_data.json", help="output file")
    ap.add_argument("--cache-dir", default="f1_cache", help="folder for FastF1's cache (default: ./f1_cache)")
    ap.add_argument("--offline", action="store_true", help="use only what is already cached; never touch the network")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and download everything again")
    args = ap.parse_args()

    # Caching: FastF1 saves every download in this folder, so each race is fetched once and
    # later runs read from disk. It must be switched on BEFORE any session is requested.
    os.makedirs(args.cache_dir, exist_ok=True)
    fastf1.Cache.enable_cache(args.cache_dir, force_renew=args.refresh)
    if args.offline:
        fastf1.Cache.offline_mode(True)

    races = {}
    for key in args.tracks:
        if key not in EVENTS:
            print(f"Unknown track key '{key}'. Choose from: {', '.join(EVENTS)}")
            continue
        try:
            print(f"Loading {EVENTS[key]} {args.year} ...")
            races[key] = load_race(args.year, EVENTS[key])
            print(f"  {len(races[key]['laps'])} laps")
        except Exception as exc:  # network error, event not on calendar, etc.
            print(f"  skipped {key}: {exc}")

    size = sum(os.path.getsize(os.path.join(d, n)) for d, _s, ns in os.walk(args.cache_dir) for n in ns) / 1e6
    print(f"Cache folder '{args.cache_dir}' now holds {size:.0f} MB.")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"source": "fastf1", "year": args.year, "races": races}, f)
    print(f"Wrote {args.out} with {len(races)} race(s).")


if __name__ == "__main__":
    main()