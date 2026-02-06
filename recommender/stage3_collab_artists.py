"""Stage 3: Recommend songs from artists who collaborated with your top artists."""

import os
import sys
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings
import common


def score_recordings_with_collab(
    recordings_by_artist, tags_by_recording, languages_by_recording,
    exclude, genre_profile, genre_affinity, era_histogram,
    user_language_profile, collab_info,
):
    """Score recordings with genre, era, collaboration, and language signals."""
    scored = defaultdict(list)
    primary_set = set(genre_affinity.get("primary", []))
    secondary_set = set(genre_affinity.get("secondary", []))
    exploration_set = set(genre_affinity.get("exploration", []))

    max_breadth = max((info["collab_breadth"] for info in collab_info.values()), default=1)
    max_depth = max((info["total_collab_count"] for info in collab_info.values()), default=1)

    entries = []
    for artist_mbid, recordings in recordings_by_artist.items():
        artist_info = collab_info.get(artist_mbid, {})
        breadth = artist_info.get("collab_breadth", 1)
        depth = artist_info.get("total_collab_count", 1)

        for rec in recordings:
            rid = rec.get("recording_mbid")
            if not rid or rid in exclude:
                continue

            tags = tags_by_recording.get(rid, [])
            rec_langs = languages_by_recording.get(rid, [])
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

            # Language matching
            lang_raw = 0
            matched_langs = []
            if rec_langs and user_language_profile:
                for lang in rec_langs:
                    if lang in user_language_profile:
                        lang_raw += user_language_profile[lang]
                        matched_langs.append(lang)

            entries.append({
                "artist_mbid": artist_mbid,
                "recording_mbid": rid,
                "recording_name": rec.get("recording_name"),
                "release_name": rec.get("release_name"),
                "release_year": year,
                "all_tags": tags,
                "all_languages": rec_langs,
                "matched_languages": matched_langs,
                "primary_matches": sorted(set(p_matches)),
                "secondary_matches": sorted(set(s_matches)),
                "exploration_matches": sorted(set(e_matches)),
                "primary_count": len(p_matches),
                "secondary_count": len(s_matches),
                "exploration_count": len(e_matches),
                "era_raw": era_raw,
                "lang_raw": lang_raw,
                "collab_breadth": breadth,
                "total_collab_count": depth,
            })

    if not entries:
        return scored

    max_era = max((e["era_raw"] for e in entries), default=0.0) or 1.0
    max_lang = max((e["lang_raw"] for e in entries), default=0.0) or 1.0

    for e in entries:
        era_score = (e["era_raw"] / max_era) * settings.ERA_SCORE_MAX_COLLAB
        breadth_score = (e["collab_breadth"] / max_breadth) * settings.COLLAB_BREADTH_SCORE_MAX
        depth_score = (e["total_collab_count"] / max_depth) * settings.COLLAB_DEPTH_SCORE_MAX
        lang_score = (e["lang_raw"] / max_lang * settings.LANGUAGE_SCORE_MAX) if e["lang_raw"] > 0 else 0.0

        score = (
            e["primary_count"] * settings.PRIMARY_WEIGHT
            + e["secondary_count"] * settings.SECONDARY_WEIGHT
            + e["exploration_count"] * settings.EXPLORATION_WEIGHT
            + era_score + breadth_score + depth_score + lang_score
        )

        scored[e["artist_mbid"]].append({
            **e,
            "era_score": era_score,
            "collab_breadth_score": breadth_score,
            "collab_depth_score": depth_score,
            "language_score": lang_score,
            "score": score,
        })

    for recs in scored.values():
        recs.sort(key=lambda r: (-r["score"], -r["release_year"]))

    return scored


def run_stage3():
    """Run Stage 3 and return the number of recommendations generated."""
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

    # Build genre, era, and language profiles
    engine = common.connect_mb()
    rec_mbids = common.extract_recording_mbids_from_listens(listens)
    user_tags = common.fetch_user_recording_tags_from_mb(engine, rec_mbids)
    if rec_mbids:
        fake_by_artist = {"__user__": [{"recording_mbid": m} for m in rec_mbids]}
        user_tags = common.augment_tags_with_release_levels(engine, fake_by_artist, user_tags)

    genre_profile = common.build_user_genre_profile(user_tags)
    genre_affinity = common.calculate_genre_affinity_depth(genre_profile)
    era_histogram = common.build_user_era_histogram(engine, listens)
    lang_profile = common.build_user_language_profile(engine, rec_mbids)

    if genre_profile:
        top = sorted(genre_profile.items(), key=lambda x: -x[1])[:10]
        print("Top genres: " + ", ".join(f"{g}({c})" for g, c in top))
    if lang_profile:
        print("Top languages: " + ", ".join(f"{l}({c})" for l, c in lang_profile.most_common(5)))

    # Get top N artists and find their collaborators
    all_sorted = sorted(user_artists.items(), key=lambda x: x[1]["count"], reverse=True)
    top_slice = all_sorted[:settings.STAGE3_TOP_N_ARTISTS]
    top_20_mbids = [mbid for mbid, _ in all_sorted[:settings.STAGE3_EXCLUDE_TOP_N]]

    if not top_slice:
        print("Not enough artists to find collaborators")
        return 0

    all_mbids_for_names = list(set([m for m, _ in top_slice] + top_20_mbids))
    names = common.get_artist_names(engine, all_mbids_for_names)

    # Discover collaborators
    print(f"\nFinding collaborators for top {settings.STAGE3_TOP_N_ARTISTS} artists...")
    collab_raw = defaultdict(lambda: {"via_artists": set(), "total_collab_count": 0, "name": None})

    for mbid, info in top_slice:
        artist_name = info.get("name") or names.get(mbid) or "Unknown"
        collabs = common.get_top_collabs_for_artist(engine, mbid, top_20_mbids, top_n=settings.STAGE3_COLLABS_PER_ARTIST)
        for c in collabs:
            collab_raw[c["mbid"]]["via_artists"].add(mbid)
            collab_raw[c["mbid"]]["total_collab_count"] += c["collab_count"]
            collab_raw[c["mbid"]]["name"] = c["name"]
        print(f"  {artist_name}: {len(collabs)} collaborators")

    # Filter by minimum breadth
    filtered = []
    for collab_mbid, info in collab_raw.items():
        breadth = len(info["via_artists"])
        if breadth >= settings.STAGE3_MIN_COLLAB_BREADTH:
            filtered.append({
                "mbid": collab_mbid,
                "name": info["name"],
                "collab_breadth": breadth,
                "total_collab_count": info["total_collab_count"],
                "via_artists": list(info["via_artists"]),
            })

    filtered.sort(key=lambda x: (-x["collab_breadth"], -x["total_collab_count"]))
    print(f"\n{len(filtered)} collaborators with {settings.STAGE3_MIN_COLLAB_BREADTH}+ connections:")
    for c in filtered:
        via = [names.get(v) or user_artists.get(v, {}).get("name") or "?" for v in c["via_artists"]]
        print(f"  {c['name']}: {c['collab_breadth']} connections via {', '.join(via)}")

    if not filtered:
        print("No qualifying collaborators found")
        return 0

    collab_info = {
        c["mbid"]: {
            "name": c["name"],
            "collab_breadth": c["collab_breadth"],
            "total_collab_count": c["total_collab_count"],
            "via_artists": c["via_artists"],
        }
        for c in filtered
    }

    # Build exclusion set: heard + stage 1 + stage 2 recs
    prev1 = os.path.join(base_dir, settings.STAGE1_OUTPUT)
    prev2 = os.path.join(base_dir, settings.STAGE2_OUTPUT)
    prev_mbids = common.load_previous_recommendations(prev1, prev2)
    exclude = set(heard) | prev_mbids
    print(f"Excluding {len(exclude)} recordings (heard + Stage 1 + Stage 2)")

    # Fetch candidate recordings, tags, and languages
    recordings_by_artist = {}
    for c in filtered:
        recs = common.get_artist_recordings(engine, c["mbid"])
        recordings_by_artist[c["mbid"]] = recs
        print(f"  {c['name']}: {len(recs)} recordings found")

    candidate_mbids = [
        r["recording_mbid"]
        for recs in recordings_by_artist.values()
        for r in recs if r.get("recording_mbid")
    ]
    tags = common.fetch_user_recording_tags_from_mb(engine, candidate_mbids)
    tags = common.augment_tags_with_release_levels(engine, recordings_by_artist, tags)
    tags = common.augment_tags_with_artist_level(engine, recordings_by_artist, tags)
    languages = common.get_recording_languages(engine, candidate_mbids)

    # Score with collab and language signals
    scored = score_recordings_with_collab(
        recordings_by_artist, tags, languages, exclude,
        genre_profile, genre_affinity, era_histogram, lang_profile, collab_info,
    )

    # Flatten and pick global top 25 (max N per artist)
    all_scored = []
    for artist_mbid, recs in scored.items():
        info = collab_info.get(artist_mbid, {})
        artist_name = info.get("name") or "Unknown"
        via = [names.get(v) or user_artists.get(v, {}).get("name") or "?" for v in info.get("via_artists", [])]
        for r in recs:
            r = dict(r)
            r["artist_name"] = artist_name
            r["via_artist_names"] = via
            all_scored.append(r)

    if not all_scored:
        print("No candidates found after exclusions")
        return 0

    all_scored.sort(key=lambda r: (-r.get("score", 0.0), r.get("recording_name") or ""))

    final = []
    artist_counts = Counter()
    for rec in all_scored:
        mid = rec.get("artist_mbid")
        if not mid or artist_counts[mid] >= settings.STAGE3_MAX_PER_ARTIST:
            continue
        final.append(rec)
        artist_counts[mid] += 1
        if len(final) >= settings.STAGE3_TOTAL_SONGS:
            break

    # Print results
    print(f"\n{'=' * 80}")
    print(f"STAGE 3: COLLAB-ARTIST PLAYLIST - {len(final)} SONGS")
    print(f"{'=' * 80}\n")

    for i, rec in enumerate(final, 1):
        year_str = f" ({rec['release_year']})" if rec.get("release_year") else ""
        via = ", ".join(rec.get("via_artist_names", []))
        print(f"  {i:2d}. {rec['recording_name']} - {rec['artist_name']}{year_str}  [score: {rec['score']:.1f}, via: {via}]")

    # Export JSON
    output_path = os.path.join(base_dir, settings.STAGE3_OUTPUT)
    export = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stage": 3,
            "description": f"Collaborators of top {settings.STAGE3_TOP_N_ARTISTS} artists (min {settings.STAGE3_MIN_COLLAB_BREADTH} connections)",
            "total_recommendations": len(final),
        },
        "qualified_collab_artists": [
            {
                "mbid": c["mbid"],
                "name": c["name"],
                "collab_breadth": c["collab_breadth"],
                "total_collab_count": c["total_collab_count"],
                "via_artists": [
                    {"mbid": v, "name": names.get(v) or user_artists.get(v, {}).get("name") or "?"}
                    for v in c["via_artists"]
                ],
            }
            for c in filtered
        ],
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
                    "collab_via": r.get("via_artist_names", []),
                    "collab_breadth": r.get("collab_breadth", 0),
                    "total_collab_count": r.get("total_collab_count", 0),
                },
                "tags": {
                    "all_tags": r.get("all_tags", []),
                    "primary_matches": r.get("primary_matches", []),
                    "secondary_matches": r.get("secondary_matches", []),
                    "exploration_matches": r.get("exploration_matches", []),
                },
                "languages": {
                    "all_languages": r.get("all_languages", []),
                    "matched_languages": r.get("matched_languages", []),
                },
                "scores": {
                    "primary_count": r.get("primary_count", 0),
                    "secondary_count": r.get("secondary_count", 0),
                    "exploration_count": r.get("exploration_count", 0),
                    "era_score": r.get("era_score", 0.0),
                    "collab_breadth_score": r.get("collab_breadth_score", 0.0),
                    "collab_depth_score": r.get("collab_depth_score", 0.0),
                    "language_score": r.get("language_score", 0.0),
                    "final_score": r.get("score", 0.0),
                },
            }
            for i, r in enumerate(final, 1)
        ],
    }

    try:
        with open(output_path, "w") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        print(f"\nExported to {settings.STAGE3_OUTPUT}")
    except Exception as e:
        print(f"Warning: Could not write {output_path}: {e}")

    return len(final)


if __name__ == "__main__":
    run_stage3()
