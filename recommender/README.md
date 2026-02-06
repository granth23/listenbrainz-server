# Recommender System (POC)

This is a **4-stage music recommendation proof-of-concept** I built to experiment with personalized playlist generation using **ListenBrainz listening data** and **MusicBrainz metadata**.
The goal wasn’t to train a black-box model, but to see how far you can go with **structured signals** like tags, eras, collaborations, and user similarity — and to keep every step inspectable and debuggable.

## Data Source

For this run, I used listens from the ListenBrainz user **holycow23**, covering **January 2026**.

* **414 listens**
* **74 artists**
* **118 unique recordings**

The listening history is dominated by **Indian hip-hop / rap** (Seedhe Maut, KR$NA, Raftaar, DIVINE, Badshah), with a strong secondary cluster of **English rock classics** (Red Hot Chili Peppers, Led Zeppelin).
When I built the tag profile from MusicBrainz, the strongest genres that emerged were **hip hop, rap, rock, hard rock, heavy metal, metal, and pop rock** — which aligned well with what you’d expect from the raw listens.

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

   * how well they match the user’s genre profile
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

  * Up to +30 points depending on how closely the song’s release decade matches the user’s dominant listening decades
  * Adjacent decades get partial credit

From each artist, I pick **5 tracks**, prioritizing primary-genre matches first so the recommendations feel familiar rather than random.

**Result:**
25 songs total, spread across Seedhe Maut, Sez on the Beat, Bawari Basanti, KR$NA, and King.
Tracks like *“We Are The Ones”* (King) and *“No Enema”* (Seedhe Maut / Sez on the Beat) surfaced mainly because they sat squarely in the user’s dominant hip-hop profile and matched the 2020s-heavy era preference.

---

## Stage 2 — Next Artists

**Goal:**
Push discovery slightly beyond the core favorites without jumping too far.

Here I look at artists ranked **6th to 20th** by listen count. These are artists the user clearly likes, just not obsessively.

The flow is similar to Stage 1, with two differences:

* **Artist-level tags** are added to compensate for sparse recording-level metadata
* Anything already recommended in Stage 1 is excluded

I score everything the same way, then take the **global top 25**, capped at **3 tracks per artist** to avoid one artist dominating the list.

**Result:**
Rock classics floated to the top very aggressively — Red Hot Chili Peppers tracks like *“Scar Tissue”*, *“Road Trippin’”*, and *“Under the Bridge”* scored extremely high because they matched almost every primary and secondary genre tag *and* landed perfectly in the user’s preferred era.

Led Zeppelin followed close behind, with Indian artists like DIVINE, AP Dhillon, Karan Aujla, and Anuv Jain filling out the rest of the list.
This stage ended up feeling like a very clean “you already like this vibe, here’s more of it” expansion.

---

## Stage 3 — Collaborator Artists

**Goal:**
Introduce **entirely new artists** using collaboration signals rather than tags alone.

For the user’s **top 15 artists**, I scan MusicBrainz artist credits to find collaborators.
To avoid one-off features, a collaborator has to be connected to **at least two different** user artists.
All of the user’s top 20 artists are excluded so the results are genuinely new.

On top of genre and era scoring, I add:

* **Collaboration breadth** (max 20)
  – how many of the user’s artists this collaborator has worked with
* **Collaboration depth** (max 15)
  – how many total co-credited recordings exist
* **Language match** (max 15)
  – how well the track’s language matches the user’s listening history

I then select the **top 25**, capped at 3 per collaborator.

**Result:**
This stage produced some of the most interesting discoveries.

Foreign Beggars surfaced via both Seedhe Maut and Sez on the Beat.
KSHMR appeared through three different connections (KR$NA, Seedhe Maut, King).
Jonita Gandhi, Ikka, Nucleya, Talhah Yunus, and others came in through overlapping collaboration paths.

The list ended up spanning UK bass, EDM, Bollywood playback, and underground rap — all adjacent to the user’s taste, but not something tag-only matching would easily surface.

---

## Stage 4 — Similar Users (Planned)

**Goal:**
Use collaborative filtering to surface tracks popular among users with similar taste.

This stage isn’t implemented yet because **similar-user data lives on ListenBrainz infrastructure**, not in the local MusicBrainz database.

The planned approach:

1. Find users with high taste overlap
2. Aggregate their most-listened tracks
3. Exclude everything already heard or recommended
4. Rank by popularity among similar users, optionally boosted by genre/era signals

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

## Configuration

All scoring weights, artist limits, and database settings live in `settings.py`, so it’s easy to tweak behavior without touching the core logic.

---

## Why this approach

This POC is intentionally:

* **Explainable** – every score can be traced
* **Debbugable** – no opaque embeddings or training loops
* **Composable** – each stage can evolve independently

It’s meant as a foundation that can later be:

* moved into **Troi**
* combined with **ListenBrainz radio**
