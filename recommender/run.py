"""Run all 3 recommendation stages and merge results into a single JSON file."""

import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings
from stage1_top_artists import run_stage1
from stage2_next_artists import run_stage2
from stage3_collab_artists import run_stage3


STAGES = [
    (settings.STAGE1_OUTPUT, 1, "Top Artists"),
    (settings.STAGE2_OUTPUT, 2, "Next Artists"),
    (settings.STAGE3_OUTPUT, 3, "Collaborator Artists"),
]


def merge_results():
    """Merge the 3 stage JSON files into a single recommendations.json."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    all_recs = []

    for filename, stage_num, stage_name in STAGES:
        filepath = os.path.join(base_dir, filename)
        if not os.path.exists(filepath):
            print(f"Warning: {filename} not found, skipping Stage {stage_num}")
            continue

        with open(filepath) as f:
            data = json.load(f)

        count = 0
        for rec in data.get("recommendations", []):
            all_recs.append({
                "song": rec["recording"]["name"],
                "artist": rec["artist"]["name"],
                "mbid": rec["recording"]["mbid"],
                "artist_mbid": rec["artist"]["mbid"],
                "release": rec["recording"].get("release"),
                "year": rec["recording"].get("year"),
                "stage": stage_num,
                "stage_name": stage_name,
            })
            count += 1

        print(f"  Stage {stage_num} ({stage_name}): {count} songs")

    # Write merged output
    merged = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_recommendations": len(all_recs),
            "stages": [
                {"stage": num, "name": name, "count": sum(1 for r in all_recs if r["stage"] == num)}
                for _, num, name in STAGES
            ],
        },
        "recommendations": all_recs,
    }

    output_path = os.path.join(base_dir, "recommendations.json")
    with open(output_path, "w") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"\nMerged {len(all_recs)} total recommendations into recommendations.json")

    # Clean up individual stage files
    for filename, _, _ in STAGES:
        filepath = os.path.join(base_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    return len(all_recs)


def main():
    print("=" * 50)
    print("RECOMMENDER SYSTEM - RUNNING ALL STAGES")
    print("=" * 50)
    print()

    # Stage 1
    print("Running Stage 1: Top Artists...")
    s1 = run_stage1()
    print(f"Stage 1 done ({s1} recommendations)\n")

    # Stage 2
    print("Running Stage 2: Next Artists...")
    s2 = run_stage2()
    print(f"Stage 2 done ({s2} recommendations)\n")

    # Stage 3
    print("Running Stage 3: Collaborator Artists...")
    s3 = run_stage3()
    print(f"Stage 3 done ({s3} recommendations)\n")

    # Merge
    print("=" * 50)
    print("MERGING RESULTS")
    print("=" * 50)
    print()

    total = merge_results()

    print()
    print("=" * 50)
    print(f"ALL DONE - {total} songs in recommendations.json")
    print("=" * 50)


if __name__ == "__main__":
    main()
