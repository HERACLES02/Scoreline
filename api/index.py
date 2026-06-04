from __future__ import annotations

import os
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    static_folder=os.path.join(ROOT_DIR, "static"),
    template_folder=os.path.join(ROOT_DIR, "templates"),
)
app.secret_key = os.getenv("SECRET_KEY", "dev-scoreline-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
)


SUPPORTED_GAMES = {
    "all": "All games",
    "lol": "League of Legends",
    "csgo": "Counter-Strike",
    "valorant": "VALORANT",
    "dota2": "Dota 2",
    "rl": "Rocket League",
    "r6siege": "Rainbow Six",
}


@dataclass
class CacheEntry:
    expires_at: float
    data: Any


class TtlCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._items.get(key)
        if not entry or entry.expires_at <= time.time():
            self._items.pop(key, None)
            return None
        return entry.data

    def set(self, key: str, data: Any, ttl_seconds: int) -> None:
        self._items[key] = CacheEntry(time.time() + ttl_seconds, data)


cache = TtlCache()


def format_db_time(value: Any) -> str:
    if hasattr(value, "astimezone"):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return str(value)


class UserStore:
    def __init__(self, database_url: str | None) -> None:
        self.database_url = database_url
        self.backend_name = "postgres" if database_url else "memory"
        self._ready = False
        self._users: dict[str, dict[str, Any]] = {}

    def create_user(self, username: str, password: str) -> dict[str, Any]:
        self._validate_password(password)
        password_hash = generate_password_hash(password)
        user_id = str(uuid.uuid4())
        if self.database_url:
            self._ensure_schema()
            with self._connect() as conn:
                row = conn.execute(
                    """
                    insert into app_users (id, username, password_hash)
                    values (%s, %s, %s)
                    returning id, username, created_at
                    """,
                    (user_id, username, password_hash),
                ).fetchone()
            return self._row_to_user(row)

        if username.lower() in (user["username"].lower() for user in self._users.values()):
            raise ValueError("username already exists")
        user = {"id": user_id, "username": username, "created_at": iso_now()}
        self._users[user_id] = {**user, "password_hash": password_hash}
        return user

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        user_with_hash = self._find_user_with_hash(username)
        if not user_with_hash or not check_password_hash(user_with_hash["password_hash"], password):
            return None
        return {
            "id": user_with_hash["id"],
            "username": user_with_hash["username"],
            "created_at": user_with_hash["created_at"],
        }

    def get_user(self, user_id: str | None) -> dict[str, Any] | None:
        if not user_id:
            return None
        if self.database_url:
            self._ensure_schema()
            with self._connect() as conn:
                row = conn.execute(
                    "select id, username, created_at from app_users where id = %s",
                    (user_id,),
                ).fetchone()
            return self._row_to_user(row) if row else None
        user = self._users.get(user_id)
        if not user:
            return None
        return {"id": user["id"], "username": user["username"], "created_at": user["created_at"]}

    def _find_user_with_hash(self, username: str) -> dict[str, Any] | None:
        if self.database_url:
            self._ensure_schema()
            with self._connect() as conn:
                row = conn.execute(
                    "select id, username, password_hash, created_at from app_users where lower(username) = lower(%s)",
                    (username,),
                ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "username": row[1],
                "password_hash": row[2],
                "created_at": format_db_time(row[3]),
            }

        for user in self._users.values():
            if user["username"].lower() == username.lower():
                return user
        return None

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required when DATABASE_URL is set") from exc
        return psycopg.connect(self.database_url)

    def _ensure_schema(self) -> None:
        if self._ready or not self.database_url:
            return
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists app_users (
                    id text primary key,
                    username text not null unique,
                    password_hash text not null,
                    created_at timestamptz not null default now()
                )
                """
            )
            conn.execute("create unique index if not exists idx_app_users_username_lower on app_users (lower(username))")
        self._ready = True

    def _row_to_user(self, row: Any) -> dict[str, Any]:
        return {"id": row[0], "username": row[1], "created_at": format_db_time(row[2])}

    def _validate_password(self, password: str) -> None:
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")


user_store = UserStore(os.getenv("DATABASE_URL"))


class TeamFollowStore:
    def __init__(self, database_url: str | None) -> None:
        self.database_url = database_url
        self.backend_name = "postgres" if database_url else "memory"
        self._ready = False
        self._follows: dict[str, dict[str, dict[str, Any]]] = {}

    def list_follows(self, user_id: str) -> list[dict[str, Any]]:
        if self.database_url:
            self._ensure_schema()
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    select team_id, team_name, game, created_at
                    from team_follows
                    where user_id = %s
                    order by created_at desc
                    """,
                    (user_id,),
                ).fetchall()
            return [self._row_to_follow(row) for row in rows]
        return list(self._follows.get(user_id, {}).values())

    def follow(self, user_id: str, team_id: str, team_name: str, game: str) -> dict[str, Any]:
        follow = {
            "team_id": team_id,
            "team_name": team_name,
            "game": game,
            "created_at": iso_now(),
        }
        if self.database_url:
            self._ensure_schema()
            with self._connect() as conn:
                row = conn.execute(
                    """
                    insert into team_follows (user_id, team_id, team_name, game)
                    values (%s, %s, %s, %s)
                    on conflict (user_id, team_id)
                    do update set team_name = excluded.team_name, game = excluded.game
                    returning team_id, team_name, game, created_at
                    """,
                    (user_id, team_id, team_name, game),
                ).fetchone()
            return self._row_to_follow(row)
        self._follows.setdefault(user_id, {})[team_id] = follow
        return follow

    def unfollow(self, user_id: str, team_id: str) -> bool:
        if self.database_url:
            self._ensure_schema()
            with self._connect() as conn:
                result = conn.execute(
                    "delete from team_follows where user_id = %s and team_id = %s",
                    (user_id, team_id),
                )
                return bool(result.rowcount)
        return self._follows.get(user_id, {}).pop(team_id, None) is not None

    def followed_ids(self, user_id: str) -> set[str]:
        return {follow["team_id"] for follow in self.list_follows(user_id)}

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required when DATABASE_URL is set") from exc
        return psycopg.connect(self.database_url)

    def _ensure_schema(self) -> None:
        if self._ready or not self.database_url:
            return
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists team_follows (
                    user_id text not null,
                    team_id text not null,
                    team_name text not null,
                    game text not null,
                    created_at timestamptz not null default now(),
                    primary key (user_id, team_id)
                )
                """
            )
            conn.execute("create index if not exists idx_team_follows_user on team_follows (user_id, created_at desc)")
        self._ready = True

    def _row_to_follow(self, row: Any) -> dict[str, Any]:
        return {
            "team_id": row[0],
            "team_name": row[1],
            "game": row[2],
            "created_at": format_db_time(row[3]),
        }


team_follow_store = TeamFollowStore(os.getenv("DATABASE_URL"))


class JsonDiscussionStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._memory: dict[str, list[dict[str, Any]]] = {}
        self.backend_name = "json"

    def list_comments(self, match_id: str) -> list[dict[str, Any]]:
        data = self._read_all()
        return data.get(match_id, [])

    def add_comment(self, match_id: str, author: str, body: str, user_id: str | None = None) -> dict[str, Any]:
        comment = {
            "id": str(uuid.uuid4()),
            "match_id": match_id,
            "user_id": user_id,
            "author": author,
            "body": body,
            "created_at": iso_now(),
            "updated_at": None,
        }
        data = self._read_all()
        data.setdefault(match_id, []).append(comment)
        self._write_all(data)
        return comment

    def update_comment(self, comment_id: str, user_id: str, body: str) -> dict[str, Any] | None:
        data = self._read_all()
        for comments in data.values():
            for comment in comments:
                if comment.get("id") == comment_id and comment.get("user_id") == user_id:
                    comment["body"] = body
                    comment["updated_at"] = iso_now()
                    self._write_all(data)
                    return comment
        return None

    def delete_comment(self, comment_id: str, user_id: str) -> bool:
        data = self._read_all()
        for match_id, comments in data.items():
            next_comments = [
                comment
                for comment in comments
                if not (comment.get("id") == comment_id and comment.get("user_id") == user_id)
            ]
            if len(next_comments) != len(comments):
                data[match_id] = next_comments
                self._write_all(data)
                return True
        return False

    def _read_all(self) -> dict[str, list[dict[str, Any]]]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return self._memory
        if not isinstance(payload, dict):
            return self._memory
        return payload

    def _write_all(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self._memory = data
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError:
            pass


class PostgresDiscussionStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.backend_name = "postgres"
        self._ready = False

    def list_comments(self, match_id: str) -> list[dict[str, Any]]:
        self._ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                select id, match_id, user_id, author, body, created_at, updated_at
                from match_comments
                where match_id = %s
                order by created_at asc
                """,
                (match_id,),
            ).fetchall()
        return [self._row_to_comment(row) for row in rows]

    def add_comment(self, match_id: str, author: str, body: str, user_id: str | None = None) -> dict[str, Any]:
        self._ensure_schema()
        comment_id = str(uuid.uuid4())
        with self._connect() as conn:
            row = conn.execute(
                """
                insert into match_comments (id, match_id, user_id, author, body)
                values (%s, %s, %s, %s, %s)
                returning id, match_id, user_id, author, body, created_at, updated_at
                """,
                (comment_id, match_id, user_id, author, body),
            ).fetchone()
        return self._row_to_comment(row)

    def update_comment(self, comment_id: str, user_id: str, body: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                update match_comments
                set body = %s, updated_at = now()
                where id = %s and user_id = %s
                returning id, match_id, user_id, author, body, created_at, updated_at
                """,
                (body, comment_id, user_id),
            ).fetchone()
        return self._row_to_comment(row) if row else None

    def delete_comment(self, comment_id: str, user_id: str) -> bool:
        self._ensure_schema()
        with self._connect() as conn:
            result = conn.execute(
                "delete from match_comments where id = %s and user_id = %s",
                (comment_id, user_id),
            )
            return bool(result.rowcount)

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required when DATABASE_URL is set") from exc

        return psycopg.connect(self.database_url)

    def _ensure_schema(self) -> None:
        if self._ready:
            return
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists match_comments (
                    id text primary key,
                    match_id text not null,
                    user_id text,
                    author text not null,
                    body text not null,
                    created_at timestamptz not null default now(),
                    updated_at timestamptz
                )
                """
            )
            conn.execute("alter table match_comments add column if not exists user_id text")
            conn.execute("alter table match_comments add column if not exists updated_at timestamptz")
            conn.execute(
                """
                create index if not exists idx_match_comments_match_created
                on match_comments (match_id, created_at)
                """
            )
        self._ready = True

    def _row_to_comment(self, row: Any) -> dict[str, Any]:
        created_at = format_db_time(row[5])
        updated_at = format_db_time(row[6]) if row[6] else None
        return {
            "id": row[0],
            "match_id": row[1],
            "user_id": row[2],
            "author": row[3],
            "body": row[4],
            "created_at": created_at,
            "updated_at": updated_at,
        }


def create_discussion_store() -> JsonDiscussionStore | PostgresDiscussionStore:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return PostgresDiscussionStore(database_url)
    return JsonDiscussionStore(
        os.getenv("FORUM_STORAGE_FILE", os.path.join(ROOT_DIR, "data", "forum_threads.json"))
    )


discussion_store = create_discussion_store()


def json_loads(payload: str) -> Any:
    return json.loads(payload)


class PandaScoreClient:
    def __init__(self, token: str | None) -> None:
        self.token = token
        self.base_url = os.getenv("PANDASCORE_BASE_URL", "https://api.pandascore.co")
        self.timeout = float(os.getenv("SCORES_API_TIMEOUT", "8"))

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def matches(self, status: str, game: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []

        endpoint = self._endpoint_for_status(status)
        params: dict[str, Any] = {
            "per_page": min(int(os.getenv("SCORES_PAGE_SIZE", "40")), 100),
            "sort": self._sort_for_status(status),
            "token": self.token,
        }
        if game != "all":
            params["filter[videogame]"] = game

        url = f"{self.base_url}{endpoint}?{urlencode(params)}"
        with urlopen(url, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8")
        return [normalize_pandascore_match(match) for match in json_loads(payload)]

    def match(self, match_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        params = {"token": self.token}
        url = f"{self.base_url}/matches/{match_id}?{urlencode(params)}"
        with urlopen(url, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8")
        raw = json_loads(payload)
        return normalize_pandascore_match(raw, include_detail=True)

    def _endpoint_for_status(self, status: str) -> str:
        if status == "live":
            return "/matches/running"
        if status == "results":
            return "/matches/past"
        return "/matches/upcoming"

    def _sort_for_status(self, status: str) -> str:
        if status == "results":
            return "-begin_at"
        return "begin_at"


class GridClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("GRID_API_KEY")
        self.match_detail_template = os.getenv("GRID_MATCH_DETAIL_URL_TEMPLATE")
        self.graphql_url = os.getenv("GRID_GRAPHQL_URL")
        self.graphql_query = os.getenv("GRID_GRAPHQL_QUERY")
        self.auth_header = os.getenv("GRID_AUTH_HEADER", "x-api-key")
        self.timeout = float(os.getenv("GRID_API_TIMEOUT", "8"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and (self.match_detail_template or self.graphql_url))

    def match_stats(self, match: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled or not should_try_grid(match):
            return None

        if self.match_detail_template:
            return self._rest_match_stats(match)
        if self.graphql_url:
            return self._graphql_match_stats(match)
        return None

    def _rest_match_stats(self, match: dict[str, Any]) -> dict[str, Any] | None:
        url = self.match_detail_template.format(
            match_id=match["id"],
            game=match["game"].lower().replace(" ", "-"),
        )
        try:
            request_obj = Request(url, headers=self._headers())
            with urlopen(request_obj, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, ValueError):
            return None

        return {
            "provider": "grid",
            "configured": True,
            "available": True,
            "mode": "rest",
            "raw": json_loads(payload),
            "note": "GRID response is attached raw until the account-specific schema is mapped.",
        }

    def _graphql_match_stats(self, match: dict[str, Any]) -> dict[str, Any]:
        if not self.graphql_query:
            return {
                "provider": "grid",
                "configured": True,
                "available": False,
                "mode": "graphql",
                "raw": None,
                "note": (
                    "GRID GraphQL is configured. Add GRID_GRAPHQL_QUERY with the query GRID gives "
                    "you for your schema before match stats can be fetched."
                ),
            }

        variables = {
            "matchId": match["id"],
            "game": match.get("game"),
            "teamOne": (match.get("team_one") or {}).get("name"),
            "teamTwo": (match.get("team_two") or {}).get("name"),
            "startsAt": match.get("starts_at"),
        }
        body = json.dumps({"query": self.graphql_query, "variables": variables}).encode("utf-8")
        try:
            request_obj = Request(
                self.graphql_url,
                data=body,
                headers={**self._headers(), "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request_obj, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
            raw = json_loads(payload)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return {
                "provider": "grid",
                "configured": True,
                "available": False,
                "mode": "graphql",
                "raw": None,
                "note": f"GRID GraphQL request failed: {exc}",
            }

        has_errors = isinstance(raw, dict) and bool(raw.get("errors"))
        return {
            "provider": "grid",
            "configured": True,
            "available": not has_errors,
            "mode": "graphql",
            "raw": raw,
            "note": (
                "GRID GraphQL returned data."
                if not has_errors
                else "GRID GraphQL returned errors; check GRID_GRAPHQL_QUERY and variables."
            ),
        }

    def _headers(self) -> dict[str, str]:
        if self.auth_header.lower() == "authorization":
            return {"Authorization": f"Bearer {self.api_key}"}
        return {self.auth_header: self.api_key}


class CitoClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("CITO_API_KEY")
        self.base_url = os.getenv("CITO_BASE_URL", "https://api.citoapi.com/api/v1").rstrip("/")
        self.match_stats_template = os.getenv("CITO_MATCH_STATS_URL_TEMPLATE")
        self.auth_header = os.getenv("CITO_AUTH_HEADER", "x-api-key")
        self.timeout = float(os.getenv("CITO_API_TIMEOUT", "8"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def match_stats(self, match: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        url = self._match_stats_url(match)
        if not url:
            return None

        try:
            from urllib.request import Request

            request_obj = Request(url, headers=self._headers())
            with urlopen(request_obj, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, ValueError):
            return None

        raw = json_loads(payload)
        data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
        player_stats = extract_stat_rows(data) if isinstance(data, dict) else []
        return {
            "provider": "cito",
            "configured": True,
            "available": True,
            "raw": raw,
            "player_stats": player_stats,
            "note": cito_note(match, bool(player_stats)),
        }

    def _headers(self) -> dict[str, str]:
        if self.auth_header.lower() == "authorization":
            return {"Authorization": f"Bearer {self.api_key}"}
        return {self.auth_header: self.api_key}

    def _match_stats_url(self, match: dict[str, Any]) -> str | None:
        game_slug = cito_game_slug(match)
        if self.match_stats_template:
            return self.match_stats_template.format(match_id=match["id"], game=game_slug or "unknown")
        if not game_slug:
            return None
        if game_slug == "lol":
            return f"{self.base_url}/lol/games/{match['id']}/player-stats"
        if game_slug == "cod":
            return f"{self.base_url}/cod/matches/{match['id']}/player-stats?includeMaps=true"
        return f"{self.base_url}/{game_slug}/matches/{match['id']}/player-stats"


grid_client = GridClient()
cito_client = CitoClient()


def normalize_pandascore_match(match: dict[str, Any], include_detail: bool = False) -> dict[str, Any]:
    opponents = match.get("opponents") or []
    team_one = _opponent_name(opponents, 0)
    team_two = _opponent_name(opponents, 1)
    results = match.get("results") or []
    normalized = {
        "id": str(match.get("id")),
        "source": "pandascore",
        "game": (match.get("videogame") or {}).get("name") or "Esports",
        "league": (match.get("league") or {}).get("name") or "Unknown league",
        "tournament": (match.get("serie") or {}).get("full_name")
        or (match.get("tournament") or {}).get("name")
        or "Tournament",
        "status": match.get("status") or "unknown",
        "starts_at": match.get("begin_at"),
        "team_one": team_one,
        "team_two": team_two,
        "score_one": _score_for(results, team_one["id"]),
        "score_two": _score_for(results, team_two["id"]),
        "best_of": match.get("number_of_games"),
        "stream_url": _first_stream_url(match.get("streams_list") or []),
        "winner_id": match.get("winner_id"),
    }
    if include_detail:
        normalized["stats"] = normalize_detail_stats(match)
    return normalized


def normalize_detail_stats(match: dict[str, Any]) -> dict[str, Any]:
    games = match.get("games") or []
    opponents = match.get("opponents") or []
    return {
        "provider": "pandascore",
        "available": bool(games or match.get("detailed_stats")),
        "detailed_stats": bool(match.get("detailed_stats")),
        "complete": match.get("complete"),
        "games": [normalize_game(game) for game in games],
        "rosters": [normalize_roster(opponent) for opponent in opponents],
        "player_stats": extract_stat_rows(match),
        "coverage_note": detail_coverage_note(match),
    }


def normalize_game(game: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(game.get("id")) if game.get("id") is not None else None,
        "position": game.get("position"),
        "status": game.get("status"),
        "winner_id": str(game.get("winner", {}).get("id") or game.get("winner_id") or "") or None,
        "winner_name": (game.get("winner") or {}).get("name"),
        "begin_at": game.get("begin_at"),
        "end_at": game.get("end_at"),
        "length": game.get("length"),
        "complete": game.get("complete"),
        "detailed_stats": game.get("detailed_stats"),
        "map": (game.get("map") or {}).get("name") or game.get("map_name") or game.get("name"),
        "raw_stats": compact_stats(game),
    }


def normalize_roster(opponent: dict[str, Any]) -> dict[str, Any]:
    team = opponent.get("opponent") or {}
    players = team.get("players") or opponent.get("players") or []
    return {
        "team_id": str(team.get("id")) if team.get("id") is not None else None,
        "team_name": team.get("name") or "TBD",
        "players": [
            {
                "id": str(player.get("id")) if player.get("id") is not None else None,
                "name": player.get("name") or player.get("first_name") or "Unknown",
                "role": player.get("role"),
                "nationality": player.get("nationality"),
                "image": player.get("image_url"),
            }
            for player in players
            if isinstance(player, dict)
        ],
    }


def extract_stat_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in [payload, *(payload.get("games") or [])]:
        for key in ("players", "player_stats", "stats", "statistics"):
            value = source.get(key)
            if isinstance(value, list):
                rows.extend(normalize_stat_row(item) for item in value if isinstance(item, dict))
    return [row for row in rows if row["metrics"]]


def normalize_stat_row(item: dict[str, Any]) -> dict[str, Any]:
    player = item.get("player") if isinstance(item.get("player"), dict) else item
    team = item.get("team") if isinstance(item.get("team"), dict) else {}
    reserved = {"id", "player", "team", "name", "first_name", "last_name", "image_url"}
    metrics = {
        key: value
        for key, value in item.items()
        if key not in reserved and isinstance(value, (str, int, float, bool)) and value not in ("", None)
    }
    return {
        "player_id": str(player.get("id")) if player.get("id") is not None else None,
        "player_name": player.get("name") or player.get("first_name") or item.get("name") or "Unknown",
        "team_name": team.get("name"),
        "metrics": metrics,
    }


def compact_stats(item: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "id",
        "winner",
        "winner_id",
        "begin_at",
        "end_at",
        "created_at",
        "updated_at",
        "match",
        "players",
        "teams",
    }
    return {
        key: value
        for key, value in item.items()
        if key not in excluded and isinstance(value, (str, int, float, bool)) and value not in ("", None)
    }


def detail_coverage_note(match: dict[str, Any]) -> str:
    if match.get("detailed_stats"):
        return "PandaScore marks this match as having detailed statistics."
    if match.get("games"):
        return "Game/map records are available, but detailed player statistics may not be complete."
    return "Detailed stats were not returned for this match by the current provider/plan."


def should_try_grid(match: dict[str, Any]) -> bool:
    game = match.get("game", "").lower()
    return any(token in game for token in ("counter", "cs", "dota"))


def cito_game_slug(match: dict[str, Any]) -> str | None:
    game = match.get("game", "").lower()
    if "league of legends" in game or game == "lol":
        return "lol"
    if "dota" in game:
        return "dota2"
    if "call of duty" in game or game == "cod":
        return "cod"
    if "valorant" in game:
        return "valorant"
    if "rocket" in game:
        return "rocketleague"
    if "fortnite" in game:
        return "fortnite"
    if "apex" in game:
        return "apex"
    return None


def cito_note(match: dict[str, Any], has_rows: bool) -> str:
    if has_rows:
        return "Cito returned player stat rows for this match."
    if not cito_game_slug(match):
        return "Cito is configured, but this game is not mapped to a Cito endpoint yet."
    return "Cito returned data, but no generic player stat rows could be extracted."


def _opponent_name(opponents: list[dict[str, Any]], index: int) -> dict[str, str | None]:
    try:
        opponent = opponents[index].get("opponent") or {}
    except IndexError:
        opponent = {}
    return {
        "id": str(opponent.get("id")) if opponent.get("id") is not None else None,
        "name": opponent.get("name") or "TBD",
        "image": opponent.get("image_url"),
    }


def _score_for(results: list[dict[str, Any]], team_id: str | None) -> int:
    if not team_id:
        return 0
    for result in results:
        if str(result.get("team_id")) == team_id:
            return int(result.get("score") or 0)
    return 0


def _first_stream_url(streams: list[dict[str, Any]]) -> str | None:
    for stream in streams:
        url = stream.get("raw_url") or stream.get("embed_url")
        if url:
            return url
    return None


def mock_matches(status: str, game: str) -> list[dict[str, Any]]:
    all_matches = [
        {
            "id": "mock-1",
            "source": "mock",
            "game": "VALORANT",
            "league": "VCT Pacific",
            "tournament": "Stage 2",
            "status": "running",
            "starts_at": iso_now(),
            "team_one": {"id": "prx", "name": "Paper Rex", "image": None},
            "team_two": {"id": "drx", "name": "DRX", "image": None},
            "score_one": 1,
            "score_two": 0,
            "best_of": 3,
            "stream_url": "https://www.twitch.tv/valorant",
            "winner_id": None,
        },
        {
            "id": "mock-2",
            "source": "mock",
            "game": "Counter-Strike",
            "league": "ESL Pro League",
            "tournament": "Group Stage",
            "status": "not_started",
            "starts_at": "2026-06-04T14:00:00Z",
            "team_one": {"id": "navi", "name": "Natus Vincere", "image": None},
            "team_two": {"id": "g2", "name": "G2 Esports", "image": None},
            "score_one": 0,
            "score_two": 0,
            "best_of": 3,
            "stream_url": "https://www.twitch.tv/eslcs",
            "winner_id": None,
        },
        {
            "id": "mock-3",
            "source": "mock",
            "game": "League of Legends",
            "league": "LCK",
            "tournament": "Regular Season",
            "status": "finished",
            "starts_at": "2026-06-02T10:00:00Z",
            "team_one": {"id": "t1", "name": "T1", "image": None},
            "team_two": {"id": "hle", "name": "Hanwha Life", "image": None},
            "score_one": 2,
            "score_two": 1,
            "best_of": 3,
            "stream_url": None,
            "winner_id": "t1",
        },
        {
            "id": "mock-4",
            "source": "mock",
            "game": "Dota 2",
            "league": "DreamLeague",
            "tournament": "Playoffs",
            "status": "not_started",
            "starts_at": "2026-06-05T18:00:00Z",
            "team_one": {"id": "spirit", "name": "Team Spirit", "image": None},
            "team_two": {"id": "falcons", "name": "Team Falcons", "image": None},
            "score_one": 0,
            "score_two": 0,
            "best_of": 5,
            "stream_url": "https://www.twitch.tv/dreamleague",
            "winner_id": None,
        },
    ]

    filtered = [match for match in all_matches if _status_bucket(match["status"]) == status]
    if game != "all":
        wanted = SUPPORTED_GAMES.get(game, game).lower()
        filtered = [match for match in filtered if wanted in match["game"].lower()]
    return filtered


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _status_bucket(raw_status: str) -> str:
    if raw_status in {"running", "live"}:
        return "live"
    if raw_status in {"finished", "completed"}:
        return "results"
    return "upcoming"


def get_matches(status: str, game: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    token = os.getenv("PANDASCORE_API_KEY")
    cache_key = f"{status}:{game}:{bool(token)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached, {"provider": "cache", "mock": cached[0]["source"] == "mock" if cached else not token}

    client = PandaScoreClient(token)
    ttl = 25 if status == "live" else 180
    meta = {"provider": "pandascore" if client.enabled else "mock", "mock": not client.enabled}

    try:
        matches = client.matches(status, game) if client.enabled else mock_matches(status, game)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        matches = mock_matches(status, game)
        meta = {"provider": "mock", "mock": True, "error": str(exc)}

    cache.set(cache_key, matches, ttl)
    return matches, meta


def get_match_detail(match_id: str) -> dict[str, Any] | None:
    token = os.getenv("PANDASCORE_API_KEY")
    cache_key = f"detail:{match_id}:{bool(token)}:{grid_client.enabled}:{cito_client.enabled}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    match = None
    if token:
        try:
            match = PandaScoreClient(token).match(match_id)
        except (HTTPError, URLError, TimeoutError, ValueError):
            match = None

    if not match:
        match = find_match(match_id, use_detail=False)
        if match and "stats" not in match:
            match["stats"] = {
                "provider": "mock" if match.get("source") == "mock" else "pandascore",
                "available": False,
                "detailed_stats": False,
                "complete": None,
                "games": [],
                "rosters": [],
                "player_stats": [],
                "coverage_note": "Detailed stats were not returned for this match.",
            }

    if not match:
        return None

    grid_stats = grid_client.match_stats(match)
    match["stats"]["grid"] = grid_stats or {
        "provider": "grid",
        "configured": grid_client.enabled,
        "available": False,
        "note": (
            "GRID is only queried for CS/Dota when GRID_API_KEY is set with "
            "GRID_GRAPHQL_URL or GRID_MATCH_DETAIL_URL_TEMPLATE."
        ),
    }
    cito_stats = cito_client.match_stats(match)
    match["stats"]["cito"] = cito_stats or {
        "provider": "cito",
        "configured": cito_client.enabled,
        "available": False,
        "note": "Cito is queried when CITO_API_KEY is set. Use CITO_MATCH_STATS_URL_TEMPLATE if PandaScore and Cito IDs do not match.",
    }
    if cito_stats and cito_stats.get("player_stats"):
        existing = match["stats"].get("player_stats") or []
        match["stats"]["player_stats"] = existing or cito_stats["player_stats"]
    cache.set(cache_key, match, 45)
    return match


def find_match(match_id: str, use_detail: bool = True) -> dict[str, Any] | None:
    if use_detail:
        return get_match_detail(match_id)
    for status in ("live", "upcoming", "results"):
        matches, _meta = get_matches(status, "all")
        for match in matches:
            if match["id"] == match_id:
                return match
    return None


def current_user() -> dict[str, Any] | None:
    return user_store.get_user(session.get("user_id"))


def require_user() -> tuple[dict[str, Any] | None, Any | None]:
    user = current_user()
    if not user:
        return None, (jsonify({"error": "login required"}), 401)
    return user, None


def clean_username(value: Any) -> str | None:
    username = str(value or "").strip()
    if len(username) < 3 or len(username) > 30:
        return None
    if not all(char.isalnum() or char in {"_", "-"} for char in username):
        return None
    return username


def clean_auth_payload(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    return clean_username(payload.get("username")), str(payload.get("password") or "")


def clean_comment_payload(payload: dict[str, Any]) -> str | None:
    body = str(payload.get("body") or "").strip()
    if not body:
        return None
    return body[:1000]


def clean_team_payload(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    team_id = str(payload.get("team_id") or "").strip()[:80]
    team_name = str(payload.get("team_name") or "").strip()[:120]
    game = str(payload.get("game") or "Esports").strip()[:80]
    if not team_id or not team_name:
        return None, None, None
    return team_id, team_name, game


def user_comment_count(user_id: str) -> int:
    if not isinstance(discussion_store, PostgresDiscussionStore):
        return 0
    discussion_store._ensure_schema()
    with discussion_store._connect() as conn:
        row = conn.execute("select count(*) from match_comments where user_id = %s", (user_id,)).fetchone()
    return int(row[0] or 0)


def public_match(match: dict[str, Any]) -> dict[str, Any]:
    user = current_user()
    followed = team_follow_store.followed_ids(user["id"]) if user else set()
    return {
        **match,
        "team_one": {**match["team_one"], "followed": bool(match["team_one"].get("id") in followed)},
        "team_two": {**match["team_two"], "followed": bool(match["team_two"].get("id") in followed)},
    }


@app.get("/")
def home():
    return render_template("index.html", games=SUPPORTED_GAMES)


@app.get("/match/<match_id>")
def match_page(match_id: str):
    match = find_match(match_id)
    if not match:
        return render_template("match.html", match=None), 404
    return render_template("match.html", match=public_match(match))


@app.get("/profile")
def profile_page():
    return render_template("profile.html")


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "time": iso_now(),
            "discussion_store": discussion_store.backend_name,
            "user_store": user_store.backend_name,
            "follow_store": team_follow_store.backend_name,
        }
    )


@app.get("/api/auth/me")
def api_me():
    return jsonify({"user": current_user()})


@app.get("/api/profile")
def api_profile():
    user, error_response = require_user()
    if error_response:
        return error_response
    return jsonify(
        {
            "user": user,
            "stats": {
                "comments": user_comment_count(user["id"]),
                "followed_teams": len(team_follow_store.list_follows(user["id"])),
            },
            "followed_teams": team_follow_store.list_follows(user["id"]),
        }
    )


@app.post("/api/auth/register")
def api_register():
    payload = request.get_json(silent=True) or {}
    username, password = clean_auth_payload(payload)
    if not username:
        return jsonify({"error": "username must be 3-30 letters, numbers, underscores, or hyphens"}), 400
    try:
        user = user_store.create_user(username, password)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return jsonify({"error": "username already exists"}), 409
    session["user_id"] = user["id"]
    return jsonify({"user": user}), 201


@app.post("/api/auth/login")
def api_login():
    payload = request.get_json(silent=True) or {}
    username, password = clean_auth_payload(payload)
    if not username:
        return jsonify({"error": "invalid username or password"}), 400
    user = user_store.authenticate(username, password)
    if not user:
        return jsonify({"error": "invalid username or password"}), 401
    session["user_id"] = user["id"]
    return jsonify({"user": user})


@app.post("/api/auth/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/matches")
def api_matches():
    status = request.args.get("status", "live")
    game = request.args.get("game", "all")
    if status not in {"live", "upcoming", "results"}:
        return jsonify({"error": "status must be live, upcoming, or results"}), 400
    if game not in SUPPORTED_GAMES:
        return jsonify({"error": "unsupported game"}), 400

    matches, meta = get_matches(status, game)
    return jsonify(
        {
            "matches": matches,
            "meta": {
                **meta,
                "status": status,
                "game": game,
                "updated_at": iso_now(),
            },
        }
    )


@app.get("/api/matches/<match_id>")
def api_match_detail(match_id: str):
    match = find_match(match_id)
    if not match:
        return jsonify({"error": "match not found"}), 404
    return jsonify({"match": public_match(match)})


@app.get("/api/matches/<match_id>/comments")
def api_comments(match_id: str):
    user = current_user()
    comments = discussion_store.list_comments(match_id)
    for comment in comments:
        comment["owned"] = bool(user and comment.get("user_id") == user["id"])
    return jsonify({"comments": comments})


@app.post("/api/matches/<match_id>/comments")
def api_create_comment(match_id: str):
    user, error_response = require_user()
    if error_response:
        return error_response
    payload = request.get_json(silent=True) or {}
    body = clean_comment_payload(payload)
    if not body:
        return jsonify({"error": "comment body is required"}), 400
    comment = discussion_store.add_comment(match_id, user["username"], body, user["id"])
    comment["owned"] = True
    return jsonify({"comment": comment}), 201


@app.patch("/api/comments/<comment_id>")
def api_update_comment(comment_id: str):
    user, error_response = require_user()
    if error_response:
        return error_response
    payload = request.get_json(silent=True) or {}
    body = clean_comment_payload(payload)
    if not body:
        return jsonify({"error": "comment body is required"}), 400
    comment = discussion_store.update_comment(comment_id, user["id"], body)
    if not comment:
        return jsonify({"error": "comment not found"}), 404
    comment["owned"] = True
    return jsonify({"comment": comment})


@app.delete("/api/comments/<comment_id>")
def api_delete_comment(comment_id: str):
    user, error_response = require_user()
    if error_response:
        return error_response
    if not discussion_store.delete_comment(comment_id, user["id"]):
        return jsonify({"error": "comment not found"}), 404
    return jsonify({"ok": True})


@app.get("/api/follows")
def api_follows():
    user, error_response = require_user()
    if error_response:
        return error_response
    return jsonify({"followed_teams": team_follow_store.list_follows(user["id"])})


@app.post("/api/follows")
def api_follow_team():
    user, error_response = require_user()
    if error_response:
        return error_response
    team_id, team_name, game = clean_team_payload(request.get_json(silent=True) or {})
    if not team_id or not team_name:
        return jsonify({"error": "team_id and team_name are required"}), 400
    follow = team_follow_store.follow(user["id"], team_id, team_name, game)
    return jsonify({"follow": follow}), 201


@app.delete("/api/follows/<team_id>")
def api_unfollow_team(team_id: str):
    user, error_response = require_user()
    if error_response:
        return error_response
    if not team_follow_store.unfollow(user["id"], team_id):
        return jsonify({"error": "follow not found"}), 404
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5050"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
