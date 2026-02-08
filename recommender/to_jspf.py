"""Convert recommendations.json to a JSPF playlist with explainability annotations.

Usage:
    python to_jspf.py                          # reads recommendations.json, writes recommendations.jspf
    python to_jspf.py -i custom.json           # custom input
    python to_jspf.py -o my_playlist.jspf      # custom output
"""

import argparse
import json
import os
import sys

MB_RECORDING_URL = "https://musicbrainz.org/recording/{}"
MB_ARTIST_URL = "https://musicbrainz.org/artist/{}"
JSPF_TRACK_EXT = "https://musicbrainz.org/doc/jspf#track"


def build_reason(rec):
    """Build a human-readable reason string for why this track was recommended."""
    stage = rec.get("stage", 0)
    stage_name = rec.get("stage_name", "")
    artist = rec.get("artist", "")

    if stage == 1:
        return f"Stage 1: Top Artist ({artist})"
    elif stage == 2:
        return f"Stage 2: Next Artist ({artist})"
    elif stage == 3:
        collab_via = rec.get("collab_via", [])
        if collab_via:
            via_str = ", ".join(collab_via)
            return f"Stage 3: Collaborator of {via_str} ({artist})"
        return f"Stage 3: Collaborator Artist ({artist})"
    else:
        return f"Stage {stage}: {stage_name} ({artist})"


def rec_to_jspf_track(rec):
    """Convert a single recommendation dict to a JSPF track object."""
    mbid = rec.get("mbid", "")
    artist_mbid = rec.get("artist_mbid", "")

    track = {
        "title": rec.get("song", ""),
        "creator": rec.get("artist", ""),
        "identifier": [MB_RECORDING_URL.format(mbid)] if mbid else [],
        "annotation": build_reason(rec),
    }

    if rec.get("release"):
        track["album"] = rec["release"]

    # JSPF extension block (MusicBrainz / ListenBrainz convention)
    extension = {}
    if artist_mbid:
        extension["artist_identifiers"] = [MB_ARTIST_URL.format(artist_mbid)]

    extension["additional_metadata"] = {
        "recommendation_reason": build_reason(rec),
        "stage": rec.get("stage"),
        "stage_name": rec.get("stage_name"),
    }

    if rec.get("collab_via"):
        extension["additional_metadata"]["collab_via"] = rec["collab_via"]

    track["extension"] = {JSPF_TRACK_EXT: extension}

    return track


def convert(input_path, output_path):
    """Read recommendations.json and write a JSPF playlist."""
    with open(input_path) as f:
        data = json.load(f)

    metadata = data.get("metadata", {})
    recommendations = data.get("recommendations", [])

    tracks = [rec_to_jspf_track(rec) for rec in recommendations]

    playlist = {
        "playlist": {
            "title": "Recommender System Output",
            "creator": "ListenBrainz Recommender POC",
            "date": metadata.get("generated_at", ""),
            "annotation": (
                f"{metadata.get('total_recommendations', len(tracks))} recommendations "
                f"across {len(metadata.get('stages', []))} stages. "
                "Each track's annotation contains the recommendation reason."
            ),
            "track": tracks,
        }
    }

    with open(output_path, "w") as f:
        json.dump(playlist, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(tracks)} tracks to {output_path}")
    return len(tracks)


def main():
    parser = argparse.ArgumentParser(
        description="Convert recommendations.json to a JSPF playlist."
    )
    base_dir = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument(
        "-i", "--input",
        default=os.path.join(base_dir, "recommendations.json"),
        help="Path to recommendations.json (default: recommendations.json)",
    )
    parser.add_argument(
        "-o", "--output",
        default=os.path.join(base_dir, "recommendations.jspf"),
        help="Path for output JSPF file (default: recommendations.jspf)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found. Run 'python run.py' first.", file=sys.stderr)
        sys.exit(1)

    convert(args.input, args.output)


if __name__ == "__main__":
    main()
