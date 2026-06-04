# Vercel Deploy

## Required environment variables

Set these in Vercel Project Settings -> Environment Variables:

```text
PANDASCORE_API_KEY
DATABASE_URL
SECRET_KEY
```

Optional GRID variables:

```text
GRID_API_KEY
GRID_GRAPHQL_URL
GRID_GRAPHQL_QUERY
GRID_AUTH_HEADER
GRID_SEARCH_WINDOW_HOURS
GRID_SEARCH_LIMIT
GRID_LIST_LIMIT
GRID_MATCH_DETAIL_URL_TEMPLATE
GRID_API_TIMEOUT
```

Use `GRID_GRAPHQL_URL=https://api-op.grid.gg/central-data/graphql` and `GRID_AUTH_HEADER=x-api-key` for GRID Central Data. When configured, GRID is the primary scoreboard source for supported titles, and PandaScore is the fallback. `GRID_GRAPHQL_QUERY` is optional and only needed if you want to override the built-in search. `GRID_MATCH_DETAIL_URL_TEMPLATE` is only needed if GRID gives you a REST-style endpoint.

Optional Cito variables:

```text
CITO_API_KEY
CITO_BASE_URL
CITO_MATCH_STATS_URL_TEMPLATE
CITO_AUTH_HEADER
CITO_API_TIMEOUT
```

Use your hosted Postgres pooled connection string for `DATABASE_URL`, with `sslmode=require`.

## Dashboard deploy

1. Push `D:\esports_scores_app` to a GitHub repository.
2. In Vercel, choose Add New -> Project.
3. Import that repository.
4. If this folder is inside a larger repo, set Root Directory to `esports_scores_app`.
5. Add the environment variables above.
6. Deploy.

## CLI deploy

Install and login:

```powershell
npm install -g vercel
vercel login
```

Deploy from the project root:

```powershell
cd D:\esports_scores_app
vercel
```

For production:

```powershell
vercel --prod
```

After deployment, check:

```text
https://your-app.vercel.app/health
```

The response should show:

```json
{
  "discussion_store": "postgres",
  "user_store": "postgres",
  "follow_store": "postgres",
  "ok": true
}
```
