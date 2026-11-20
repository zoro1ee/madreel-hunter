"""TMDB lookup.

The MADREEL OpenAPI deliberately does **not** do keyword search: clients are
expected to turn a title into ``tmdb_id`` + ``media_type`` first (see the
official "工具对接建议" section). This module does exactly that with the public
TMDB v3 API and no third-party HTTP client.
"""

from __future__ import annotations

from dataclasses import dataclass

from .http import request
from .models import TmdbMatch

TMDB_API = "https://api.themoviedb.org/3"


class TmdbError(RuntimeError):
    pass


@dataclass(slots=True)
class TmdbClient:
    api_key: str
    timeout: float = 20.0
    proxy: str = ""
    language: str = "zh-CN"

    def _get(self, path: str, **params: object) -> dict:
        if not self.api_key:
            raise TmdbError(
                "TMDB API key is not configured. Get one at "
                "https://www.themoviedb.org/settings/api and set TMDB_API_KEY."
            )
        query = "&".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
        url = f"{TMDB_API}/search/{path}?api_key={self.api_key}&language={self.language}&{query}"
        resp = request("GET", url, timeout=self.timeout, proxy=self.proxy)
        if resp.status != 200:
            raise TmdbError(f"TMDB returned HTTP {resp.status}: {resp.text[:200]}")
        payload = resp.json() or {}
        return payload

    def search(self, query: str, media_type: str = "multi", year: int | None = None) -> list[TmdbMatch]:
        """Search movies/tv shows and return normalised matches sorted by popularity."""
        payload = self._get(media_type, query=query, year=year)
        results: list[TmdbMatch] = []
        for item in payload.get("results", []):
            kind = item.get("media_type") or ("movie" if media_type == "movie" else "tv")
            if kind not in {"movie", "tv"}:
                continue
            title = item.get("title") or item.get("name") or ""
            date = item.get("release_date") or item.get("first_air_date") or ""
            results.append(
                TmdbMatch(
                    tmdb_id=int(item["id"]),
                    media_type=kind,
                    title=title,
                    year=date[:4] or None,
                    overview=(item.get("overview") or "").strip(),
                    popularity=float(item.get("popularity") or 0.0),
                )
            )
        results.sort(key=lambda m: m.popularity, reverse=True)
        return results
