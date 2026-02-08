# Explainable, Collaboration-Aware Recommender

This is a **multi-stage music recommendation system** that generates personalized playlists using **ListenBrainz listening data** and **MusicBrainz metadata**. It integrates into the ListenBrainz ecosystem as a **Troi patch** (automatic, scheduled playlists) and an **LB Radio stream** (on-demand, blendable with other prompts).

Unlike black-box CF or prompt-based blends, every recommendation carries a **machine-readable reason** — users can see *why* each track was suggested: "From an artist you love (Seedhe Maut)" / "Next-tier artist (DIVINE)" / "Collaborator of Seedhe Maut & KR$NA (KSHMR)."

The goal isn't to replace Spark CF or LB Radio — it's to add a **new, complementary signal** that is explainable, uses collaboration as a discovery channel, and runs **automatically** without requiring any user intervention.

## Quick Start

**Prerequisites:** Python 3.9+ and a local [MusicBrainz database](https://musicbrainz.org/doc/MusicBrainz_Database) (PostgreSQL).

```bash
pip install -r requirements.txt
```

**Run the recommender (Stages 1–3):**

```bash
python3 run.py
```

* **Input:** `songs.jsonl` — a sample listening history (included).
* **Output:** `recommendations.json` — 75 recommended tracks with metadata, scores, and per-track reasons.

**Convert to JSPF playlist:**

```bash
python3 to_jspf.py
```

* **Input:** `recommendations.json`
* **Output:** `recommendations.jspf` — a standard JSPF playlist with MusicBrainz identifiers and per-track recommendation reasons.

See the [Output](#output) and [JSPF Export](#jspf-export) sections below for details.

---

## Data Source

The included `songs.jsonl` is a **sample** of my personal ListenBrainz listening history (user **holycow23**, January 2026). It is provided as a reference so you can run the pipeline out of the box — replace it with your own JSONL export to generate personalised recommendations.

* **414 listens**
* **74 artists**
* **118 unique recordings**

The listening history is dominated by **Indian hip-hop / rap** (Seedhe Maut, KR$NA, Raftaar, DIVINE, Badshah), with a strong secondary cluster of **English rock classics** (Red Hot Chili Peppers, Led Zeppelin).
When I built the tag profile from MusicBrainz, the strongest genres that emerged were **hip hop, rap, rock, hard rock, heavy metal, metal, and pop rock** — which aligned well with what you'd expect from the raw listens.

## Core Idea

All stages share the same foundation:

1. Load user listens from `songs.jsonl`
2. Build a **genre/tag profile** by querying MusicBrainz at multiple levels:

   * recording
   * release
   * release-group
   * artist
3. Build an **era histogram** from release years
4. Score candidate tracks based on:

   * how well they match the user's genre profile
   * how well their release era aligns with what the user listens to

To keep things simple and interpretable, I bucket genres into three tiers:

* **Primary** – top ~20% of cumulative tag weight
* **Secondary** – next ~30%
* **Exploration** – everything else

These tiers are reused across all stages so the behavior stays consistent.

---

## Stage 1 — Top Artists

**Goal:**
Find *new* songs from the artists the user already listens to the most.

I take the **top 5 artists by listen count**, pull their full discographies from MusicBrainz, and remove anything the user has already heard.

Each remaining recording is scored using:

* **Genre affinity**

  * Primary tag match: +40
  * Secondary: +15
  * Exploration: +5
* **Era preference**

  * Up to +30 points depending on how closely the song's release decade matches the user's dominant listening decades
  * Adjacent decades get partial credit

From each artist, I pick **5 tracks**, prioritizing primary-genre matches first so the recommendations feel familiar rather than random.

**Explainability:** Each track carries a structured reason: `{ "stage": 1, "stage_name": "top_artists", "genre_matches": [...], "era_decade": 2020 }` and a human-readable annotation like *"From an artist you love (Seedhe Maut)."*

**Result:**
25 songs total, spread across Seedhe Maut, Sez on the Beat, Bawari Basanti, KR$NA, and King.
Tracks like *"We Are The Ones"* (King) and *"No Enema"* (Seedhe Maut / Sez on the Beat) surfaced mainly because they sat squarely in the user's dominant hip-hop profile and matched the 2020s-heavy era preference.

---

## Stage 2 — Next Artists

**Goal:**
Push discovery slightly beyond the core favorites without jumping too far.

Here I look at artists ranked **6th to 20th** by listen count. These are artists the user clearly likes, just not obsessively.

The flow is similar to Stage 1, with two differences:

* **Artist-level tags** are added to compensate for sparse recording-level metadata
* Anything already recommended in Stage 1 is excluded

I score everything the same way, then take the **global top 25**, capped at **3 tracks per artist** to avoid one artist dominating the list.

**Explainability:** Each track carries a reason like *"Next-tier artist (Red Hot Chili Peppers)"* — the user understands this is an expansion of taste, not a random pick.

**Result:**
Rock classics floated to the top very aggressively — Red Hot Chili Peppers tracks like *"Scar Tissue"*, *"Road Trippin'"*, and *"Under the Bridge"* scored extremely high because they matched almost every primary and secondary genre tag *and* landed perfectly in the user's preferred era.

Led Zeppelin followed close behind, with Indian artists like DIVINE, AP Dhillon, Karan Aujla, and Anuv Jain filling out the rest of the list.
This stage ended up feeling like a very clean "you already like this vibe, here's more of it" expansion.

---

## Stage 3 — Collaborator Artists

**Goal:**
Introduce **entirely new artists** using collaboration signals rather than tags alone.

For the user's **top 15 artists**, I scan MusicBrainz artist credits to find collaborators.
To avoid one-off features, a collaborator has to be connected to **at least two different** user artists.
All of the user's top 20 artists are excluded so the results are genuinely new.

On top of genre and era scoring, I add:

* **Collaboration breadth** (max 20)
  – how many of the user's artists this collaborator has worked with
* **Collaboration depth** (max 15)
  – how many total co-credited recordings exist
* **Language match** (max 15)
  – how well the track's language matches the user's listening history

I then select the **top 25**, capped at 3 per collaborator.

**Explainability:** Each track carries a reason like *"Collaborator of Seedhe Maut & KR$NA (KSHMR)"* — the collaboration path is explicitly named, not hidden in a score.

**Result:**
This stage produced some of the most interesting discoveries.

Foreign Beggars surfaced via both Seedhe Maut and Sez on the Beat.
KSHMR appeared through three different connections (KR$NA, Seedhe Maut, King).
Jonita Gandhi, Ikka, Nucleya, Talhah Yunus, and others came in through overlapping collaboration paths.

The list ended up spanning UK bass, EDM, Bollywood playback, and underground rap — all adjacent to the user's taste, but not something tag-only matching would easily surface.

---

## Stage 4 — Similar Users (Planned)

**Goal:**
Use collaborative filtering to surface tracks popular among users with similar taste.

This stage isn't implemented yet because **similar-user data lives on ListenBrainz infrastructure**, not in the local MusicBrainz database.

The planned approach:

1. Find users with high taste overlap (from Spark or LB, existing endpoint or new dump)
2. Aggregate their most-listened tracks
3. Exclude everything already heard or recommended in Stages 1–3
4. Rank by popularity among similar users, optionally boosted by genre/era signals

**Explainability:** Each track would carry a reason like *"Popular among users with similar taste"* — the CF signal becomes just one named piece of the puzzle.

Once the data is available, this will be added as `stage4_similar_users.py` and plugged into the existing pipeline.

---

## Output

Running:

```bash
python3 run.py
```

Executes Stages 1–3, merges the results, and produces a single `recommendations.json` containing **75 tracks** with full metadata, scores, and (for Stage 3) collaboration paths.
Intermediate stage files are cleaned up after the merge.

---

## JSPF Export

To convert the recommendations into a standard [JSPF](https://xspf.org/jspf/) playlist that tools like **Troi** and **ListenBrainz Radio** can consume:

```bash
python3 to_jspf.py
```

This reads `recommendations.json` and writes `recommendations.jspf` with:

* **One track per recommendation** — `identifier` set to the MusicBrainz recording URL, `creator` set to the artist name, `album` set to the release name.
* **Explainability built in** — each track's `annotation` field contains a human-readable reason, for example:
  * `"Stage 1: Top Artist (Seedhe Maut)"`
  * `"Stage 2: Next Artist (Red Hot Chili Peppers)"`
  * `"Stage 3: Collaborator of Seedhe Maut, KR$NA (KSHMR)"`
* **Structured reason object** — the `https://musicbrainz.org/doc/jspf#track` extension block includes `additional_metadata` with a machine-readable reason:
  ```json
  {
    "stage": 3,
    "stage_name": "collaborator_artists",
    "genre_matches": ["hip hop", "edm"],
    "era_decade": 2020,
    "collab_via": ["artist_mbid_1", "artist_mbid_2"],
    "language_matches": ["Hindi", "English"]
  }
  ```
* **MusicBrainz extension** — includes `artist_identifiers` and full `additional_metadata` (stage number, stage name, collaboration path where applicable).

Custom input/output paths are supported:

```bash
python3 to_jspf.py -i custom_recs.json -o my_playlist.jspf
```

---

## Integration: Troi Patch

The primary integration path is as a **Troi patch** — the system runs automatically on a schedule and generates "Created for You" playlists for users, just like existing Troi recommendation pipelines.

**What this means in practice:**

* Users don't need to do anything — playlists appear in their account with per-track reasons embedded
* The patch reads user listens from the LB API (or approved backend), queries MusicBrainz for metadata, runs Stages 1–3, and outputs a JSPF playlist with the explainability extension
* No dependency on local JSONL files in production; the data pipeline uses LB API and MB database/API
* No breaking changes to existing Troi patches or playlists

**Data pipeline (production):**

* **Listens:** LB API (or approved backend) for user listening history
* **MusicBrainz data:** Either (1) MB database integration for Troi/LB if infra exists, or (2) MB web API client with batching, caching, and rate-limit handling for tags, release years, artist credits, and language
* **Config:** Database/API URLs, cache TTL, batch sizes — all in `settings.py`, documented for deployers

---

## Integration: LB Radio Stream

Beyond the automatic Troi patch, the recommender also integrates as an **LB Radio stream** — a new prompt entity that users can request on demand and blend with other LB Radio sources.

**New prompt entity:**

* `explainable:(username)` or `explainable_recs:(username)` in the LB Radio prompt parser

**New element:**

* e.g. `LBRadioExplainableRecordingElement` — calls the same pipeline as the Troi patch (or a shared backend) and returns a list of `Recording` objects with reasons attached

**Blending:**

* This stream is weighted and blended with artist/tag/stats/recs just like any other LB Radio source
* Optional: in UI, show which tracks in a blended playlist came from the "explainable" source

**Fallback:**

* If no reason is available (e.g. old playlists or other patches), show nothing or "Recommended for you" — no breaking change

This integration is important because it shows the system extends LB Radio rather than duplicating it. Users get a new discovery channel without leaving the tools they already use.

---

## Evaluation & Metrics

To show that explainable recommendations are worth having — not just "another source" — the project includes a metrics pipeline.

**Approach:** For a sample of users, generate both (1) current CF recs and (2) explainable recs. Compute:

* **Diversity:** Artist/release spread, tag entropy
* **Coverage:** % of recs that have MusicBrainz metadata (artist, release, tags)
* **Explainability:** % of recs that have a non-empty reason (stage + at least one of genre/era/collaboration path)

**Deliverables:**

* A short report (or notebook) with tables/plots comparing CF vs explainable recs
* Reusable scripts so future changes to the recommender can re-run the comparison

---

## "Why This Track?" in the UI (Stretch)

For playlists generated by the explainable-rec patch, the frontend can show a short line per track, e.g.:

* *"From an artist you love (Seedhe Maut)"*
* *"Next-tier artist (DIVINE)"*
* *"Collaborator of Seedhe Maut & KR$NA (KSHMR)"*

**Data flow:** Uses the JSPF extension from the structured reason; no new backend endpoint needed since playlists already return JSPF.

**Fallback:** If reason is missing (e.g. old playlists or other patches), show nothing or "Recommended for you."

---

## Configuration

All scoring weights, artist limits, and database settings live in `settings.py`, so it's easy to tweak behavior without touching the core logic.

---

## Why This Approach

This system is intentionally:

* **Explainable** – every recommendation gets a machine-readable reason (stage, genre, era, collaboration path). Enables "Recommended because …" in the UI and builds trust.
* **Collaboration-driven** – uses "who recorded with your favorites" as a first-class signal, distinct from similar-artist and CF. Surfaces producers, featuring artists, and one-off collabs.
* **Debuggable** – no opaque embeddings or training loops; every score can be traced back to specific tags, eras, and collaboration paths.
* **Composable** – each stage can evolve independently; new stages (e.g. Stage 4: similar users) can be added without touching existing ones.
* **Automatic** – runs as a Troi patch on a schedule; users see results without doing anything.
* **Measurable** – evaluation compares explainable vs CF (diversity, coverage, explanation quality); the comparison is reusable.

It's not replacing Spark or LB Radio — it's adding a distinct, debuggable, user-facing story for "why this track," plus evaluation to show it brings diversity and explanations. The POC is the blueprint; the project is the product.

---

## Project Roadmap

| Scope | Description | Priority |
|-------|------------|----------|
| **E. Robust data pipeline** | Production path for listens (LB API) + MusicBrainz data (MB database/API, caching, config) | Core |
| **A. Evaluation & metrics** | Metrics pipeline comparing CF vs explainable recs (diversity, coverage, explainability) | Mandatory |
| **B. Explainability in API/JSPF** | Structured reasons in Troi output, JSPF extension, API contract | Mandatory |
| **C. "Why this track?" UI** | Show explanation per track in playlist detail / Created for You | Stretch |
| **D. LB Radio integration** | New prompt entity, new `LBRadioExplainableRecordingElement`, blend with existing streams | Mandatory |
| **F. Stage 4 (similar users)** | CF stage using similar-user data from LB/Spark | Optional |
| **G. Documentation & community** | Design doc, user-facing docs ("Explainable recommendations" and "LB Radio: explainable stream"), contributor-facing docs | Mandatory |
