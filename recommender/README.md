# Recommender System

A 4-stage music recommendation engine that builds a personalized playlist by querying MusicBrainz for genre tags, release eras, language metadata, artist collaboration graphs, and similar-user listening patterns.

## Data Source

The listening data used for this run comes from the ListenBrainz user **holycow23** and covers the month of **January 2026**. The dataset contains **414 listens** spanning **74 distinct artists** and **118 unique recordings**. The listening profile skews heavily toward **Indian hip-hop/rap** (Seedhe Maut, KR$NA, Raftaar, DIVINE, Badshah) and **English rock classics** (Led Zeppelin, Red Hot Chili Peppers), with the top detected genres being hip hop, rock, heavy metal, hard rock, pop rock, metal, and rap.

## How It Works

The first three stages share a common foundation: user listens are loaded from `songs.jsonl`, a genre/tag profile is built by querying MusicBrainz for recording-level, release-level, release-group-level, and artist-level tags, and an era histogram is constructed from release years. Genres are bucketed into three affinity tiers -- **primary** (top 20% of cumulative tag weight), **secondary** (20-50%), and **exploration** (the rest) -- and each candidate song is scored against these tiers using configurable weights.

### Stage 1 -- Top Artists

**Goal:** Surface unheard deep cuts from the artists you already love the most.

The algorithm identifies the user's **top 5 artists by listen count** and fetches their full discographies from MusicBrainz. Every recording the user has already heard is excluded. The remaining candidates are scored using:

- **Genre affinity** -- primary-genre tag matches contribute 40 points each, secondary 15, exploration 5.
- **Era preference** -- a normalized score (max 30 points) based on how well the song's release decade aligns with the decades the user listens to most, with half-credit for adjacent decades.

Songs are selected per-artist (5 per artist), preferring those with primary-genre matches first, then secondary, then the rest.

**What it achieved:** 25 songs were recommended across Seedhe Maut (173 listens), Sez on the Beat (74), Bawari Basanti (71), KR$NA (65), and King (16). Top picks included "We Are The Ones" by King (score 115.0) and "No Enema" by Seedhe Maut/Sez on the Beat (score 80.0), both surfaced because of strong hip-hop primary-genre matches and era alignment with the user's 2020s-heavy listening.

### Stage 2 -- Next Artists

**Goal:** Broaden the playlist by pulling from artists the user listens to occasionally (ranked 6th-20th), pushing discovery a bit further from the comfort zone while still staying genre-relevant.

The algorithm takes artists ranked **6 through 20** by listen count and fetches their discographies. Artist-level tags are additionally layered onto candidate recordings (on top of recording and release tags) to improve scoring for artists with sparser MusicBrainz metadata. Recordings already heard *and* those already recommended in Stage 1 are excluded. Scoring uses the same genre-affinity + era formula as Stage 1. The global top 25 candidates are selected, capped at 3 per artist to ensure variety.

**What it achieved:** 25 songs were recommended. The rock classics dominated the top of the list -- Red Hot Chili Peppers' "Scar Tissue" (score 785.0), "Road Trippin'" (775.0), and "Under the Bridge" (775.0) scored extremely high because they matched nearly every primary and secondary genre tag in the user's profile (rock, pop rock, hard rock, etc.) and landed squarely in the user's preferred era. Led Zeppelin tracks like "Bron-Yr-Aur Stomp" and "Dazed and Confused" followed close behind (515.0). Mid-tier Indian artists like DIVINE ("Traffic Jam", 150.0), AP Dhillon ("Toxic", 120.0), Karan Aujla ("Tell Me", 115.0), and Anuv Jain ("Afsos", 100.0) filled out the list with strong hip-hop and pop matches.

### Stage 3 -- Collaborator Artists

**Goal:** Introduce entirely new artists the user has never listened to by following the collaboration graph -- if Artist A and Artist B (whom the user likes) both worked with Artist C, then Artist C is probably worth exploring.

The algorithm discovers collaborators by scanning MusicBrainz artist credits for shared recordings across the user's **top 15 artists**. A collaborator must be connected to at least **2 different** user artists to qualify (the "breadth" threshold), which filters out one-off features. The user's top 20 artists are excluded so the results are genuinely new. Scoring adds three new dimensions on top of genre and era:

- **Collaboration breadth** (max 20 points) -- how many of the user's artists this collaborator has worked with, normalized.
- **Collaboration depth** (max 15 points) -- total number of co-credited recordings across all connections, normalized.
- **Language match** (max 15 points) -- how well the candidate recording's language (from MusicBrainz work/release language metadata) matches the user's language listening profile.

The global top 25 are selected, capped at 3 per collaborator artist.

**What it achieved:** 14 qualifying collaborators were discovered, and 25 songs were recommended. Foreign Beggars topped the list with "Mind's Eye" (score 209.7), connected via both Seedhe Maut and Sez on the Beat, benefiting from strong genre overlap and collaboration signals. Neha Kakkar appeared via Raftaar and Badshah connections ("Hauli Hauli", 158.3). KSHMR surfaced through 3 connections (KR$NA, Seedhe Maut, King), contributing "Echo" (132.6). Jonita Gandhi, linked via DIVINE, Karan Aujla, and Badshah, brought in Bollywood-crossover picks. Ikka appeared through KR$NA, Sez on the Beat, and Karan Aujla. The stage successfully introduced artists from adjacent scenes -- UK bass music (Foreign Beggars), EDM (KSHMR, Nucleya), Bollywood playback (Jonita Gandhi, Payal Dev, Shashwat Sachdev), and underground rap (Talhah Yunus, Rashmeet Kaur).

### Stage 4 -- Similar Users (Not Yet Implemented)

**Goal:** Recommend the most popular songs among ListenBrainz users whose taste closely resembles yours -- a collaborative-filtering approach that surfaces tracks the user's "taste neighbors" love but the user hasn't heard yet.

The planned algorithm would work as follows:

1. **Find similar users** -- query the ListenBrainz similar-users dataset to identify users with the highest taste overlap with holycow23, based on shared artist and recording listening patterns.
2. **Aggregate their top tracks** -- collect the most frequently listened recordings across those similar users, weighted by how similar each user is.
3. **Filter and score** -- exclude everything the user has already heard and everything recommended in Stages 1-3, then rank the remaining candidates by popularity-among-similar-users, optionally boosted by the same genre-affinity and era signals used in earlier stages.
4. **Select top N** -- pick the final set of songs, capped per artist to maintain variety.

This stage was not implemented or tested because the similar-users data is not available in the local MusicBrainz database -- it lives on ListenBrainz's production infrastructure and would require either API access or a local dump of the similarity matrix. Once that data is available, the stage would be added as `stage4_similar_users.py` and wired into `run.py` alongside the existing three stages.

## Output

Running `python3 run.py` currently executes Stages 1-3 sequentially, merges the results, and writes a single `recommendations.json` containing 75 songs with full metadata (MBIDs, tags, scores, collaboration paths). Individual stage files are cleaned up after the merge. Once Stage 4 is implemented, it will be included in the merge and the total count will increase accordingly.

## Configuration

All tunable parameters (scoring weights, artist counts, song limits, database URI) live in `settings.py`.

## File Overview

| File | Purpose |
|---|---|
| `run.py` | Orchestrator -- runs all stages and merges output |
| `stage1_top_artists.py` | Stage 1 algorithm |
| `stage2_next_artists.py` | Stage 2 algorithm |
| `stage3_collab_artists.py` | Stage 3 algorithm |
| `stage4_similar_users.py` | Stage 4 algorithm (planned, not yet implemented) |
| `common.py` | Shared DB queries, tag fetching, profile building |
| `settings.py` | Configuration constants |
| `songs.jsonl` | Input listens (holycow23, January 2026) |
