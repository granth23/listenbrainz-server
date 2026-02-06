"""Configuration for the recommender system."""

# Scoring weights
PRIMARY_WEIGHT = 40.0
SECONDARY_WEIGHT = 15.0
EXPLORATION_WEIGHT = 5.0

# Era scoring
ERA_SCORE_MAX = 30.0
ERA_SCORE_MAX_COLLAB = 25.0

# Collaboration scoring (stage 3)
COLLAB_BREADTH_SCORE_MAX = 20.0
COLLAB_DEPTH_SCORE_MAX = 15.0
LANGUAGE_SCORE_MAX = 15.0

# Stage 1: songs from your top artists
STAGE1_TOP_ARTISTS_COUNT = 5
STAGE1_SONGS_PER_ARTIST = 5

# Stage 2: songs from artists ranked 6-20
STAGE2_ARTIST_RANK_START = 6
STAGE2_ARTIST_RANK_END = 20
STAGE2_MAX_PER_ARTIST = 3
STAGE2_TOTAL_SONGS = 25

# Stage 3: songs from collaborator artists
STAGE3_TOP_N_ARTISTS = 15
STAGE3_COLLABS_PER_ARTIST = 10
STAGE3_MIN_COLLAB_BREADTH = 2
STAGE3_MAX_PER_ARTIST = 3
STAGE3_TOTAL_SONGS = 25
STAGE3_EXCLUDE_TOP_N = 20

# Database
MB_DATABASE_URI = "postgresql://musicbrainz:musicbrainz@localhost:5432/musicbrainz_db"

# File paths (relative to recommender folder)
LISTENS_FILE = "songs.jsonl"
STAGE1_OUTPUT = "stage1_recommendations.json"
STAGE2_OUTPUT = "stage2_recommendations.json"
STAGE3_OUTPUT = "stage3_recommendations.json"
