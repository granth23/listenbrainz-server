"""Stage 2: Recommend unheard songs from your artists ranked 6-20."""

import os
import sys
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings
import common


def score_recordings(recordings_by_artist, tags_by_recording, exclude, genre_profile, genre_affinity, era_histogram=None):
    """Score candidate recordings by genre match and era preference."""
    scored = defaultdict(list)
    primary_set = set(genre_affinity.get("primary", []))
    secondary_set = set(genre_affinity.get("secondary", []))
    exploration_set = set(genre_affinity.get("exploration", []))

    entries = []
    for artist_mbid, recordings in recordings_by_artist.items():
        for rec in recordings:
            rid = rec.get("recording_mbid")
            if not rid or rid in exclude:
                continue

            tags = tags_by_recording.get(rid, [])
            p_matches, s_matches, e_matches = [], [], []

            if tags and genre_profile:
                for tag in tags:
                    if tag not in genre_profile:
                        continue
                    if tag in primary_set:
                        p_matches.append(tag)
                    elif tag in secondary_set:
                        s_matches.append(tag)
                    elif tag in exploration_set:
                        e_matches.append(tag)

            year = int(rec.get("release_year") or 0)

            era_raw = 0.0
            if era_histogram and year > 0:
                decade = (year // 10) * 10
                era_raw = (
                    float(era_histogram.get(decade, 0))
                    + 0.5 * float(era_histogram.get(decade - 10, 0))
                    + 0.5 * float(era_histogram.get(decade + 10, 0))
                )

            entries.append({
                "artist_mbid": artist_mbid,
                "recording_mbid": rid,
                "recording_name": rec.get("recording_name"),
                "release_name": rec.get("release_name"),
                "release_year": year,
                "all_tags": tags,
                "primary_matches": sorted(set(p_matches)),
                "secondary_matches": sorted(set(s_matches)),
                "exploration_matches": sorted(set(e_matches)),
                "primary_count": len(p_matches),
                "secondary_count": len(s_matches),
                "exploration_count": len(e_matches),
                "era_raw": era_raw,
            })

    if not entries:
        return scored

    max_era = max((e["era_raw"] for e in entries), default=0.0) or 1.0

    for e in entries:
        era_norm = e["era_raw"] / max_era if e["era_raw"] > 0 else 0.0
        era_score = era_norm * settings.ERA_SCORE_MAX
        score = (
            e["primary_count"] * settings.PRIMARY_WEIGHT
            + e["secondary_count"] * settings.SECONDARY_WEIGHT
            + e["exploration_count"] * settings.EXPLORATION_WEIGHT
            + era_score
        )

        scored[e["artist_mbid"]].append({**e, "era_score": era_score, "score": score})

    for recs in scored.values():
        recs.sort(key=lambda r: (-r["score"], -r["release_year"], r["recording_name"] or ""))

    return scored


def run_stage2():
    """Run Stage 2 and return the number of recommendations generated."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    jsonl_path = os.path.join(base_dir, settings.LISTENS_FILE)

    if not os.path.exists(jsonl_path):
        print(f"Error: {jsonl_path} not found")
        return 0

    # Load listens and extract user profile
    listens = common.load_user_listens(jsonl_path)
    print(f"Loaded {len(listens)} listens")

    user_artists, heard, _, _ = common.extract_artist_info(listens)
    print(f"Found {len(user_artists)} artists, heard {len(heard)} recordings")

    if not user_artists:
        print("No artists found, aborting")
        return 0

    # Build genre and era profiles
    engine = common.connect_mb()
    rec_mbids = common.extract_recording_mbids_from_listens(listens)
    user_tags = common.fetch_user_recording_tags_from_mb(engine, rec_mbids)
    if rec_mbids:
        fake_by_artist = {"__user__": [{"recording_mbid": m} for m in rec_mbids]}
        user_tags = common.augment_tags_with_release_levels(engine, fake_by_artist, user_tags)

    genre_profile = common.build_user_genre_profile(user_tags)
    genre_affinity = common.calculate_genre_affinity_depth(genre_profile)
    era_histogram = common.build_user_era_histogram(engine, listens)

    if genre_profile:
        top = sorted(genre_profile.items(), key=lambda x: -x[1])[:10]
        print("Top genres: " + ", ".join(f"{g}({c})" for g, c in top))

    # Get mid-tier artists (ranked 6-20)
    all_sorted = sorted(user_artists.items(), key=lambda x: x[1]["count"], reverse=True)
    mid_tier = all_sorted[settings.STAGE2_ARTIST_RANK_START - 1:settings.STAGE2_ARTIST_RANK_END]

    if not mid_tier:
        print(f"Not enough artists for rank {settings.STAGE2_ARTIST_RANK_START}-{settings.STAGE2_ARTIST_RANK_END}")
        return 0

    mid_mbids = [mbid for mbid, _ in mid_tier]
    names = common.get_artist_names(engine, mid_mbids)

    print(f"\nUsing artists ranked {settings.STAGE2_ARTIST_RANK_START}-{settings.STAGE2_ARTIST_RANK_END}:")
    for rank, (mbid, info) in enumerate(mid_tier, start=settings.STAGE2_ARTIST_RANK_START):
        info["name"] = info.get("name") or names.get(mbid) or "Unknown"
        print(f"  {rank}. {info['name']} ({info['count']} listens)")

    # Build exclusion set: heard + stage 1 recs
    prev_path = os.path.join(base_dir, settings.STAGE1_OUTPUT)
    prev_mbids = common.load_previous_recommendations(prev_path)
    exclude = set(heard) | prev_mbids
    print(f"Excluding {len(exclude)} recordings (heard + Stage 1)")

    # Fetch candidate recordings and tags
    recordings_by_artist = {}
    for mbid, info in mid_tier:
        recs = common.get_artist_recordings(engine, mbid)
        recordings_by_artist[mbid] = recs
        print(f"  {info['name']}: {len(recs)} recordings found")

    candidate_mbids = [
        r["recording_mbid"]
        for recs in recordings_by_artist.values()
        for r in recs if r.get("recording_mbid")
    ]
    tags = common.fetch_user_recording_tags_from_mb(engine, candidate_mbids)
    tags = common.augment_tags_with_release_levels(engine, recordings_by_artist, tags)
    tags = common.augment_tags_with_artist_level(engine, recordings_by_artist, tags)

    # Score all recordings
    scored = score_recordings(recordings_by_artist, tags, exclude, genre_profile, genre_affinity, era_histogram)

    # Flatten and pick global top 25 (max N per artist)
    all_scored = []
    for artist_mbid, recs in scored.items():
        artist_name = user_artists.get(artist_mbid, {}).get("name") or names.get(artist_mbid) or "Unknown"
        for r in recs:
            r = dict(r)
            r["artist_name"] = artist_name
            all_scored.append(r)

    if not all_scored:
        print("No candidates found after exclusions")
        return 0

    all_scored.sort(key=lambda r: (-r.get("score", 0.0), r.get("recording_name") or ""))

    final = []
    artist_counts = Counter()
    for rec in all_scored:
        mid = rec.get("artist_mbid")
        if not mid or artist_counts[mid] >= settings.STAGE2_MAX_PER_ARTIST:
            continue
        final.append(rec)
        artist_counts[mid] += 1
        if len(final) >= settings.STAGE2_TOTAL_SONGS:
            break

    # Print results
    print(f"\n{'=' * 80}")
    print(f"STAGE 2: NEXT-ARTIST PLAYLIST - {len(final)} SONGS")
    print(f"{'=' * 80}\n")

    for i, rec in enumerate(final, 1):
        year_str = f" ({rec['release_year']})" if rec.get("release_year") else ""
        print(f"  {i:2d}. {rec['recording_name']} - {rec['artist_name']}{year_str}  [score: {rec['score']:.1f}]")

    # Export JSON
    output_path = os.path.join(base_dir, settings.STAGE2_OUTPUT)
    export = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stage": 2,
            "description": f"Artists ranked {settings.STAGE2_ARTIST_RANK_START}-{settings.STAGE2_ARTIST_RANK_END}, top {settings.STAGE2_TOTAL_SONGS} songs",
            "total_recommendations": len(final),
        },
        "recommendations": [
            {
                "rank": i,
                "recording": {
                    "mbid": r["recording_mbid"],
                    "name": r["recording_name"],
                    "release": r.get("release_name"),
                    "year": r.get("release_year"),
                },
                "artist": {
                    "mbid": r["artist_mbid"],
                    "name": r["artist_name"],
                },
                "tags": {
                    "all_tags": r.get("all_tags", []),
                    "primary_matches": r.get("primary_matches", []),
                    "secondary_matches": r.get("secondary_matches", []),
                    "exploration_matches": r.get("exploration_matches", []),
                },
                "scores": {
                    "primary_count": r.get("primary_count", 0),
                    "secondary_count": r.get("secondary_count", 0),
                    "exploration_count": r.get("exploration_count", 0),
                    "era_score": r.get("era_score", 0.0),
                    "final_score": r.get("score", 0.0),
                },
            }
            for i, r in enumerate(final, 1)
        ],
    }

    try:
        with open(output_path, "w") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        print(f"\nExported to {settings.STAGE2_OUTPUT}")
    except Exception as e:
        print(f"Warning: Could not write {output_path}: {e}")

    return len(final)


if __name__ == "__main__":
    run_stage2()
