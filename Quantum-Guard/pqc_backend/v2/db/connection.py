"""
QuantumGuard v2 — Async PostgreSQL Connection Pool
====================================================
Uses asyncpg for high-performance async Postgres access.
Falls back to aiosqlite for development/testing when
DATABASE_URL is not set (uses SQLite on disk).

Usage:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1")
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

logger = logging.getLogger("quantumguard.db")

_pool = None


def _get_database_url() -> str:
    """Read DATABASE_URL from env, falling back to SQLite."""
    return os.environ.get(
        "DATABASE_URL",
        "sqlite:///~/.quantum-guard/quantumguard_v2.db",
    )


async def get_pool():
    """
    Return (or create) the global connection pool.

    For PostgreSQL (asyncpg):
        DATABASE_URL=postgresql://user:pass@host:5432/dbname

    For SQLite fallback (aiosqlite):
        DATABASE_URL=sqlite:///path/to/file.db   (or omit env var)
    """
    global _pool
    if _pool is not None:
        return _pool

    url = _get_database_url()

    if url.startswith("postgresql://") or url.startswith("postgres://"):
        import asyncpg  # type: ignore

        _pool = await asyncpg.create_pool(
            dsn=url,
            min_size=2,
            max_size=20,
            command_timeout=30,
        )
        logger.info("PostgreSQL pool created (%s)", url.split("@")[-1] if "@" in url else url)
    else:
        # SQLite fallback for local dev / testing
        _pool = _SqlitePool(url)
        logger.info("SQLite fallback pool created (%s)", url)

    return _pool


async def close_pool():
    """Gracefully shut down the connection pool."""
    global _pool
    if _pool is None:
        return

    if hasattr(_pool, "close"):
        await _pool.close()
    _pool = None
    logger.info("Database pool closed")


@asynccontextmanager
async def get_db():
    """
    Yield a database connection from the pool.

    Usage:
        async with get_db() as conn:
            row = await conn.fetchrow("SELECT 1")
    """
    pool = await get_pool()

    if hasattr(pool, "acquire"):
        # asyncpg pool
        async with pool.acquire() as conn:
            yield conn
    else:
        # SQLite fallback
        async with pool.acquire() as conn:
            yield conn


# ─── SQLite Fallback ─────────────────────────────────────────

class _SqliteConnection:
    """Thin wrapper around aiosqlite to mimic asyncpg interface."""

    def __init__(self, conn):
        self._conn = conn

    async def execute(self, query: str, *args):
        sql = self._adapt_sql(query)
        await self._conn.execute(sql, args if args else None)
        await self._conn.commit()

    async def executemany(self, query: str, args_list):
        sql = self._adapt_sql(query)
        await self._conn.executemany(sql, args_list)
        await self._conn.commit()

    async def fetch(self, query: str, *args) -> list[dict]:
        sql = self._adapt_sql(query)
        self._conn.row_factory = _dict_factory
        cursor = await self._conn.execute(sql, args if args else None)
        rows = await cursor.fetchall()
        return rows

    async def fetchrow(self, query: str, *args) -> Optional[dict]:
        rows = await self.fetch(query, *args)
        return rows[0] if rows else None

    async def fetchval(self, query: str, *args):
        sql = self._adapt_sql(query)
        cursor = await self._conn.execute(sql, args if args else None)
        row = await cursor.fetchone()
        if row is None:
            return None
        # row might be a dict (from row_factory) or tuple
        if isinstance(row, dict):
            # Return first value
            return next(iter(row.values()))
        return row[0]

    @staticmethod
    def _adapt_sql(sql: str) -> str:
        """Convert $1, $2 positional params to ? for SQLite."""
        import re
        return re.sub(r'\$\d+', '?', sql)


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class _SqlitePool:
    """Minimal pool-like wrapper for aiosqlite."""

    def __init__(self, url: str):
        self._url = url
        path = url.replace("sqlite:///", "").replace("~", str(__import__("pathlib").Path.home()))
        self._path = path
        __import__("pathlib").Path(path).parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def acquire(self):
        import aiosqlite  # type: ignore
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = _dict_factory
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            yield _SqliteConnection(conn)

    async def close(self):
        pass
