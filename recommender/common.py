"""Shared helpers for the recommender: DB queries, tag fetching, profile building."""

import json
import os
import sys
import uuid
from collections import Counter, defaultdict

import sqlalchemy
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings


def chunks(lst, n):
    """Split a list into chunks of size n."""
    lst = list(lst)
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def dedupe(items):
    """Remove duplicates from a list while preserving order."""
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def connect_mb():
    """Create a SQLAlchemy engine for the MusicBrainz database."""
    return sqlalchemy.create_engine(settings.MB_DATABASE_URI)


def load_user_listens(jsonl_path):
    """Load listens from a JSONL file."""
    listens = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    listens.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return listens


def extract_artist_info(listens):
    """Extract artists, heard recordings, and listen counts from user's listens.

    Returns (artists_dict, heard_set, artist_weights_counter, heard_set_copy).
    """
    artists = {}
    heard = set()
    weights = Counter()

    for listen in listens:
        mapping = listen.get("track_metadata", {}).get("mbid_mapping")
        if not mapping:
            continue

        rec_mbid = mapping.get("recording_mbid")
        if rec_mbid:
            heard.add(str(rec_mbid))

        for artist_mbid in mapping.get("artist_mbids", []):
            mid = str(artist_mbid)
            if mid not in artists:
                artists[mid] = {"name": None, "count": 0}
            artists[mid]["count"] += 1
            weights[mid] += 1

    return artists, heard, weights, set(heard)


def extract_recording_mbids_from_listens(listens):
    """Get unique recording MBIDs from listens."""
    mbids = []
    for listen in listens:
        mapping = listen.get("track_metadata", {}).get("mbid_mapping")
        if mapping and mapping.get("recording_mbid"):
            mbids.append(str(mapping["recording_mbid"]))
    return list(dict.fromkeys(mbids))


def get_user_favorite_artists(user_artists, limit=5):
    """Return top artists sorted by listen count."""
    return sorted(user_artists.items(), key=lambda x: x[1]["count"], reverse=True)[:limit]


def get_artist_names(engine, artist_mbids):
    """Fetch artist names from MusicBrainz."""
    if not artist_mbids:
        return {}

    placeholders = ", ".join(f"'{uuid.UUID(m)}'" for m in artist_mbids)
    query = f"SELECT gid::TEXT as mbid, name FROM artist WHERE gid IN ({placeholders})"

    try:
        with engine.connect() as conn:
            return {row.mbid: row.name for row in conn.execute(text(query))}
    except Exception:
        return {}


def get_artist_recordings(engine, artist_mbid, limit=None):
    """Get all recordings by an artist from MusicBrainz."""
    q = """
        SELECT DISTINCT
            r.gid::TEXT as recording_mbid,
            r.name as recording_name,
            rel.name as release_name,
            ac.name as artist_credit_name,
            COALESCE(rc.date_year, 0) as release_year
        FROM artist a
        JOIN artist_credit_name acn ON a.id = acn.artist
        JOIN artist_credit ac ON acn.artist_credit = ac.id
        JOIN recording r ON ac.id = r.artist_credit
        LEFT JOIN track t ON r.id = t.recording
        LEFT JOIN medium m ON t.medium = m.id
        LEFT JOIN release rel ON m.release = rel.id
        LEFT JOIN release_country rc ON rel.id = rc.release
        WHERE a.gid = :mbid
        ORDER BY COALESCE(rc.date_year, 0) DESC
    """
    if limit:
        q += f" LIMIT {limit}"

    try:
        with engine.connect() as conn:
            result = conn.execute(text(q), {"mbid": uuid.UUID(artist_mbid)})
            recordings = []
            seen = set()
            for row in result:
                if row.recording_mbid and row.recording_mbid not in seen:
                    recordings.append({
                        "recording_mbid": row.recording_mbid,
                        "recording_name": row.recording_name,
                        "release_name": row.release_name,
                        "artist_credit_name": row.artist_credit_name,
                        "release_year": int(row.release_year) if row.release_year else 0,
                    })
                    seen.add(row.recording_mbid)
            return recordings
    except Exception as e:
        print(f"Error fetching recordings for {artist_mbid}: {e}")
        return []


def _table_exists(conn, table_name):
    """Check if a table exists in the public schema."""
    try:
        return bool(conn.execute(text(f"SELECT to_regclass('public.{table_name}')")).scalar())
    except Exception:
        return False


def fetch_user_recording_tags_from_mb(engine, recording_mbids):
    """Fetch tags/genres for recordings from MusicBrainz (recording + artist level)."""
    if not recording_mbids:
        return {}

    tags = defaultdict(list)

    try:
        with engine.connect() as conn:
            has_rec_genre = _table_exists(conn, "recording_genre")
            has_artist_genre = _table_exists(conn, "artist_genre")

            for batch in chunks(recording_mbids, 100):
                phs = ", ".join(f"'{uuid.UUID(m)}'" for m in batch)

                # Recording tags
                for row in conn.execute(text(f"""
                    SELECT r.gid::TEXT as rid, tag.name as tag
                    FROM recording r
                    LEFT JOIN recording_tag rt ON r.id = rt.recording
                    LEFT JOIN tag ON rt.tag = tag.id
                    WHERE r.gid IN ({phs})
                """)):
                    if row.tag:
                        tags[row.rid].append(row.tag.lower())

                # Recording genres
                if has_rec_genre:
                    for row in conn.execute(text(f"""
                        SELECT r.gid::TEXT as rid, g.name as genre
                        FROM recording r
                        LEFT JOIN recording_genre rg ON r.id = rg.recording
                        LEFT JOIN genre g ON rg.genre = g.id
                        WHERE r.gid IN ({phs})
                    """)):
                        if row.genre:
                            tags[row.rid].append(row.genre.lower())

                # Artist tags via recording's artist credit
                for row in conn.execute(text(f"""
                    SELECT r.gid::TEXT as rid, tag.name as tag
                    FROM recording r
                    LEFT JOIN artist_credit ac ON r.artist_credit = ac.id
                    LEFT JOIN artist_credit_name acn ON ac.id = acn.artist_credit
                    LEFT JOIN artist a ON acn.artist = a.id
                    LEFT JOIN artist_tag at ON a.id = at.artist
                    LEFT JOIN tag ON at.tag = tag.id
                    WHERE r.gid IN ({phs})
                """)):
                    if row.tag:
                        tags[row.rid].append(row.tag.lower())

                # Artist genres
                if has_artist_genre:
                    for row in conn.execute(text(f"""
                        SELECT r.gid::TEXT as rid, g.name as genre
                        FROM recording r
                        LEFT JOIN artist_credit ac ON r.artist_credit = ac.id
                        LEFT JOIN artist_credit_name acn ON ac.id = acn.artist_credit
                        LEFT JOIN artist a ON acn.artist = a.id
                        LEFT JOIN artist_genre ag ON a.id = ag.artist
                        LEFT JOIN genre g ON ag.genre = g.id
                        WHERE r.gid IN ({phs})
                    """)):
                        if row.genre:
                            tags[row.rid].append(row.genre.lower())

        return {rid: dedupe(tag_list) for rid, tag_list in tags.items()}
    except Exception as e:
        print(f"Warning: Could not fetch tags: {e}")
        return {}


def augment_tags_with_release_levels(engine, recordings_by_artist, tags_by_recording):
    """Add album/release and release-group level tags to recordings."""
    all_mbids = set()
    for recs in recordings_by_artist.values():
        for r in recs:
            if r.get("recording_mbid"):
                all_mbids.add(r["recording_mbid"])

    if not all_mbids:
        return tags_by_recording

    try:
        with engine.connect() as conn:
            has_release_tag = _table_exists(conn, "release_tag")
            has_rg_tag = _table_exists(conn, "release_group_tag")
            has_release_genre = _table_exists(conn, "release_genre")
            has_rg_genre = _table_exists(conn, "release_group_genre")

            for batch in chunks(all_mbids, 100):
                phs = ", ".join(f"'{uuid.UUID(m)}'" for m in batch)

                if has_release_tag:
                    for row in conn.execute(text(f"""
                        SELECT r.gid::TEXT as rid, tag.name as tag
                        FROM recording r
                        JOIN track t ON r.id = t.recording
                        JOIN medium m ON t.medium = m.id
                        JOIN release rel ON m.release = rel.id
                        LEFT JOIN release_tag rt ON rel.id = rt.release
                        LEFT JOIN tag ON rt.tag = tag.id
                        WHERE r.gid IN ({phs})
                    """)):
                        if row.tag:
                            tags_by_recording.setdefault(row.rid, []).append(row.tag.lower())

                if has_rg_tag:
                    for row in conn.execute(text(f"""
                        SELECT r.gid::TEXT as rid, tag.name as tag
                        FROM recording r
                        JOIN track t ON r.id = t.recording
                        JOIN medium m ON t.medium = m.id
                        JOIN release rel ON m.release = rel.id
                        JOIN release_group rg ON rel.release_group = rg.id
                        LEFT JOIN release_group_tag rgt ON rg.id = rgt.release_group
                        LEFT JOIN tag ON rgt.tag = tag.id
                        WHERE r.gid IN ({phs})
                    """)):
                        if row.tag:
                            tags_by_recording.setdefault(row.rid, []).append(row.tag.lower())

                if has_release_genre:
                    for row in conn.execute(text(f"""
                        SELECT r.gid::TEXT as rid, g.name as genre
                        FROM recording r
                        JOIN track t ON r.id = t.recording
                        JOIN medium m ON t.medium = m.id
                        JOIN release rel ON m.release = rel.id
                        LEFT JOIN release_genre rg ON rel.id = rg.release
                        LEFT JOIN genre g ON rg.genre = g.id
                        WHERE r.gid IN ({phs})
                    """)):
                        if row.genre:
                            tags_by_recording.setdefault(row.rid, []).append(row.genre.lower())

                if has_rg_genre:
                    for row in conn.execute(text(f"""
                        SELECT r.gid::TEXT as rid, g.name as genre
                        FROM recording r
                        JOIN track t ON r.id = t.recording
                        JOIN medium m ON t.medium = m.id
                        JOIN release rel ON m.release = rel.id
                        JOIN release_group rg ON rel.release_group = rg.id
                        LEFT JOIN release_group_genre rgg ON rg.id = rgg.release_group
                        LEFT JOIN genre g ON rgg.genre = g.id
                        WHERE r.gid IN ({phs})
                    """)):
                        if row.genre:
                            tags_by_recording.setdefault(row.rid, []).append(row.genre.lower())

        for rid in list(tags_by_recording):
            tags_by_recording[rid] = dedupe(tags_by_recording[rid])
    except Exception as e:
        print(f"Warning: Could not augment album-level tags: {e}")

    return tags_by_recording


def augment_tags_with_artist_level(engine, recordings_by_artist, tags_by_recording):
    """Add artist-level tags/genres to recordings."""
    artist_mbids = set(recordings_by_artist.keys())
    if not artist_mbids:
        return tags_by_recording

    artist_tags = defaultdict(list)

    try:
        with engine.connect() as conn:
            has_artist_genre = _table_exists(conn, "artist_genre")

            for batch in chunks(artist_mbids, 100):
                phs = ", ".join(f"'{uuid.UUID(m)}'" for m in batch)

                for row in conn.execute(text(f"""
                    SELECT a.gid::TEXT as amid, tag.name as tag
                    FROM artist a
                    LEFT JOIN artist_tag at ON a.id = at.artist
                    LEFT JOIN tag ON at.tag = tag.id
                    WHERE a.gid IN ({phs})
                """)):
                    if row.tag:
                        artist_tags[row.amid].append(row.tag.lower())

                if has_artist_genre:
                    for row in conn.execute(text(f"""
                        SELECT a.gid::TEXT as amid, g.name as genre
                        FROM artist a
                        LEFT JOIN artist_genre ag ON a.id = ag.artist
                        LEFT JOIN genre g ON ag.genre = g.id
                        WHERE a.gid IN ({phs})
                    """)):
                        if row.genre:
                            artist_tags[row.amid].append(row.genre.lower())

        for artist_mbid, recs in recordings_by_artist.items():
            a_tags = artist_tags.get(artist_mbid, [])
            if not a_tags:
                continue
            for r in recs:
                rid = r.get("recording_mbid")
                if rid:
                    tags_by_recording.setdefault(rid, []).extend(a_tags)

        for rid in list(tags_by_recording):
            tags_by_recording[rid] = dedupe(tags_by_recording[rid])
    except Exception as e:
        print(f"Warning: Could not augment artist-level tags: {e}")

    return tags_by_recording


def build_user_genre_profile(tags_by_recording):
    """Count how often each tag appears across the user's listened recordings."""
    counts = Counter()
    for tag_list in tags_by_recording.values():
        for tag in tag_list:
            counts[tag] += 1
    return counts


def calculate_genre_affinity_depth(genre_profile):
    """Split genres into primary (top 20%), secondary (20-50%), exploration (rest)."""
    if not genre_profile:
        return {"primary": [], "secondary": [], "exploration": []}

    sorted_genres = sorted(genre_profile.items(), key=lambda x: -x[1])
    total = sum(c for _, c in sorted_genres)

    primary, secondary, exploration = [], [], []
    cumulative = 0
    for genre, count in sorted_genres:
        ratio = cumulative / total if total > 0 else 0
        cumulative += count
        if ratio < 0.2:
            primary.append(genre)
        elif ratio < 0.5:
            secondary.append(genre)
        else:
            exploration.append(genre)

    return {"primary": primary, "secondary": secondary, "exploration": exploration}


def build_user_era_histogram(engine, listens):
    """Build a histogram of listens per decade."""
    rec_counts = Counter()
    for listen in listens:
        mapping = listen.get("track_metadata", {}).get("mbid_mapping") or {}
        rec_mbid = mapping.get("recording_mbid")
        if rec_mbid:
            rec_counts[str(rec_mbid)] += 1

    if not rec_counts:
        return {}

    era_counts = Counter()
    try:
        with engine.connect() as conn:
            for batch in chunks(list(rec_counts.keys()), 100):
                phs = ", ".join(f"'{uuid.UUID(m)}'" for m in batch)
                for row in conn.execute(text(f"""
                    SELECT DISTINCT r.gid::TEXT as rid, COALESCE(rc.date_year, 0) as year
                    FROM recording r
                    LEFT JOIN track t ON r.id = t.recording
                    LEFT JOIN medium m ON t.medium = m.id
                    LEFT JOIN release rel ON m.release = rel.id
                    LEFT JOIN release_country rc ON rel.id = rc.release
                    WHERE r.gid IN ({phs}) AND COALESCE(rc.date_year, 0) > 0
                """)):
                    year = int(row.year or 0)
                    if year > 0:
                        decade = (year // 10) * 10
                        era_counts[decade] += rec_counts.get(row.rid, 0)
    except Exception as e:
        print(f"Warning: Could not build era histogram: {e}")
        return {}

    return dict(era_counts)


def build_user_language_profile(engine, recording_mbids):
    """Build language preferences from user's listened recordings."""
    counts = Counter()
    if not recording_mbids:
        return counts

    try:
        with engine.connect() as conn:
            for batch in chunks(recording_mbids, 100):
                phs = ", ".join(f"'{uuid.UUID(m)}'" for m in batch)

                # From work language
                try:
                    for row in conn.execute(text(f"""
                        SELECT DISTINCT r.gid::TEXT as rid, l.iso_code_3 as lang
                        FROM recording r
                        LEFT JOIN l_recording_work lrw ON r.id = lrw.entity0
                        LEFT JOIN work w ON lrw.entity1 = w.id
                        LEFT JOIN language l ON w.language = l.id
                        WHERE r.gid IN ({phs}) AND l.iso_code_3 IS NOT NULL
                    """)):
                        if row.lang:
                            counts[row.lang.lower()] += 1
                except Exception:
                    pass

                # From release language
                try:
                    for row in conn.execute(text(f"""
                        SELECT DISTINCT r.gid::TEXT as rid, l.iso_code_3 as lang
                        FROM recording r
                        JOIN track t ON r.id = t.recording
                        JOIN medium m ON t.medium = m.id
                        JOIN release rel ON m.release = rel.id
                        LEFT JOIN language l ON rel.language = l.id
                        WHERE r.gid IN ({phs}) AND l.iso_code_3 IS NOT NULL
                    """)):
                        if row.lang:
                            counts[row.lang.lower()] += 1
                except Exception:
                    pass
    except Exception as e:
        print(f"Warning: Could not build language profile: {e}")

    return counts


def get_recording_languages(engine, recording_mbids):
    """Get languages for candidate recordings."""
    langs = defaultdict(list)
    if not recording_mbids:
        return langs

    try:
        with engine.connect() as conn:
            for batch in chunks(recording_mbids, 100):
                phs = ", ".join(f"'{uuid.UUID(m)}'" for m in batch)

                try:
                    for row in conn.execute(text(f"""
                        SELECT DISTINCT r.gid::TEXT as rid, l.iso_code_3 as lang
                        FROM recording r
                        LEFT JOIN l_recording_work lrw ON r.id = lrw.entity0
                        LEFT JOIN work w ON lrw.entity1 = w.id
                        LEFT JOIN language l ON w.language = l.id
                        WHERE r.gid IN ({phs}) AND l.iso_code_3 IS NOT NULL
                    """)):
                        if row.lang:
                            langs[row.rid].append(row.lang.lower())
                except Exception:
                    pass

                try:
                    for row in conn.execute(text(f"""
                        SELECT DISTINCT r.gid::TEXT as rid, l.iso_code_3 as lang
                        FROM recording r
                        JOIN track t ON r.id = t.recording
                        JOIN medium m ON t.medium = m.id
                        JOIN release rel ON m.release = rel.id
                        LEFT JOIN language l ON rel.language = l.id
                        WHERE r.gid IN ({phs}) AND l.iso_code_3 IS NOT NULL
                    """)):
                        if row.lang:
                            langs[row.rid].append(row.lang.lower())
                except Exception:
                    pass

        for rid in langs:
            langs[rid] = list(set(langs[rid]))
    except Exception as e:
        print(f"Warning: Could not fetch recording languages: {e}")

    return langs


def load_previous_recommendations(*paths):
    """Load recording MBIDs from previous stage JSON files to avoid duplicates."""
    mbids = set()
    for path in paths:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            for item in data.get("recommendations", []):
                rec_mbid = (item.get("recording") or {}).get("mbid")
                if rec_mbid:
                    mbids.add(str(rec_mbid))
        except Exception as e:
            print(f"Warning: Could not read {path}: {e}")
    return mbids


def get_top_collabs_for_artist(engine, artist_mbid, exclude_mbids, top_n=5):
    """Find top N collaborators for an artist (excluding specified artists)."""
    collabs = []

    try:
        query = f"""
            SELECT DISTINCT
                a2.gid::TEXT as collab_mbid,
                a2.name as collab_name,
                COUNT(DISTINCT r.id) as collab_count
            FROM recording r
            JOIN artist_credit ac ON r.artist_credit = ac.id
            JOIN artist_credit_name acn1 ON ac.id = acn1.artist_credit
            JOIN artist a1 ON acn1.artist = a1.id
            JOIN artist_credit_name acn2 ON ac.id = acn2.artist_credit
            JOIN artist a2 ON acn2.artist = a2.id
            WHERE a1.gid = '{uuid.UUID(artist_mbid)}'
              AND a2.gid != a1.gid
            GROUP BY a2.gid, a2.name
            ORDER BY collab_count DESC
        """

        exclude_set = set(exclude_mbids)
        with engine.connect() as conn:
            for row in conn.execute(text(query)):
                if row.collab_mbid in exclude_set:
                    continue
                collabs.append({
                    "mbid": row.collab_mbid,
                    "name": row.collab_name,
                    "collab_count": int(row.collab_count),
                    "via_artist_mbid": artist_mbid,
                })
                if len(collabs) >= top_n:
                    break
    except Exception as e:
        print(f"Warning: Could not fetch collabs for {artist_mbid}: {e}")

    return collabs
