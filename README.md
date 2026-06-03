# Scoreline

Scoreline is a web app for esports scores, detailed match rooms, team follows, and match discussions. The long-term goal is one platform for esports and real-life sports scores, results, stats, and analysis.

Fast Flask scoreboard for esports matches, built to deploy on Vercel.

## What it does

- Shows live, upcoming, and recent result tabs
- Filters by major esport
- Uses PandaScore when `PANDASCORE_API_KEY` is set
- Falls back to mock data so the UI runs immediately
- Caches live data briefly to reduce API usage
- Keeps the provider layer separate so real-life sports can be added later
- Adds match discussion comments for the first forum layer
- Uses Postgres for production forum persistence when `DATABASE_URL` is set
- Supports register/login/logout with password hashing
- Links comments to users, with owner-only edit and delete actions
- Adds dedicated match detail pages at `/match/<match_id>`
- Adds a profile page at `/profile`
- Lets logged-in users follow and unfollow teams
- Fetches detailed PandaScore match data when available
- Supports optional GRID detail calls for CS/Dota through environment configuration
- Supports optional Cito detail calls for player-stat enrichment

## Local setup

```powershell
cd D:\esports_scores_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.ps1
```

Open:

```text
http://127.0.0.1:5050
```

To use real esports data locally:

```powershell
$env:PANDASCORE_API_KEY="your_token_here"
.\run.ps1
```

You can also create a local `.env` file next to `run.ps1`. `run.ps1` loads it automatically:

```text
PANDASCORE_API_KEY=your_token_here
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
SECRET_KEY=replace_with_a_long_random_secret
GRID_API_KEY=your_grid_key_here
GRID_MATCH_DETAIL_URL_TEMPLATE=https://example.grid.endpoint/matches/{match_id}
CITO_API_KEY=your_cito_key_here
CITO_MATCH_STATS_URL_TEMPLATE=https://api.citoapi.com/api/v1/{game}/matches/{match_id}/player-stats
```

Keep `.env` private. It is ignored by Git.

Local discussion comments are saved to:

```text
D:\esports_scores_app\data\forum_threads.json
```

This is for local development. On Vercel, use an external database such as Supabase or Neon for persistent forum comments.

If `DATABASE_URL` is set, comments are saved to Postgres instead of the local JSON file. The app creates this table automatically:

```sql
create table if not exists match_comments (
    id text primary key,
    match_id text not null,
    user_id text,
    author text not null,
    body text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz
);
```

The app also creates an `app_users` table for accounts and a `team_follows` table for followed teams.

## Vercel deploy

Use `D:\esports_scores_app` as the project root when importing the repo.

Add this environment variable in Vercel:

```text
PANDASCORE_API_KEY
DATABASE_URL
```

Do not commit API keys. Keep them in Vercel's dashboard.

For `DATABASE_URL`, use the pooled connection string from Supabase or Neon when available, and keep `sslmode=require` in the URL.

PandaScore detailed stats depend on match/game coverage and your plan. Match pages show maps, rosters, and player stat rows when the API returns them. For GRID, set `GRID_API_KEY` and `GRID_MATCH_DETAIL_URL_TEMPLATE`; the template can use `{match_id}` and `{game}` placeholders.

For Cito, set `CITO_API_KEY`. If PandaScore match IDs do not match Cito IDs, set `CITO_MATCH_STATS_URL_TEMPLATE` to the endpoint shape Cito gives you. The template can use `{match_id}` and `{game}` placeholders.

See `VERCEL_DEPLOY.md` for the full deploy checklist.

## API

```text
GET /api/matches?status=live&game=all
GET /api/matches?status=upcoming&game=valorant
GET /api/matches?status=results&game=lol
GET /api/matches/<match_id>
GET /api/matches/<match_id>/comments
POST /api/matches/<match_id>/comments
PATCH /api/comments/<comment_id>
DELETE /api/comments/<comment_id>
GET /api/auth/me
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET /api/profile
GET /api/follows
POST /api/follows
DELETE /api/follows/<team_id>
GET /health
```

Status values:

```text
live
upcoming
results
```

Game values:

```text
all
lol
csgo
valorant
dota2
rl
r6siege
```

## Next features

- Password reset
- Moderation tools
- Notifications for followed teams
- Real-life sports provider using the same normalized match shape
