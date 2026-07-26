"""Apply pending SQL migrations from supabase/migrations/.

Tracks applied files in public.schema_migrations. Skips _archive/ and only
considers *.sql files directly under the migrations directory.

Usage:
  python -m app.scripts.run_migrations
  python -m app.scripts.run_migrations --dry-run

Env:
  DATABASE_URL — SQLAlchemy or libpq Postgres URL (required)
  MIGRATION_DATABASE_URL — optional override (prefer direct/session DB URL for DDL)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg
from psycopg import ClientCursor

from app.database_url import ensure_remote_ssl

logger = logging.getLogger(__name__)

TRACKING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# When an existing DB has no tracking table yet, only mark migrations through this
# baseline as applied. Newer files (e.g. 013+) still run as pending.
_BOOTSTRAP_THROUGH = "012_profile_platform_admin.sql"


def _repo_root() -> Path:
    # backend/app/scripts/run_migrations.py → repo root
    return Path(__file__).resolve().parents[3]


def _migrations_dir(root: Path | None = None) -> Path:
    return (root or _repo_root()) / "supabase" / "migrations"


def _database_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not url:
        url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        from app.config import get_settings

        url = get_settings().database_url.strip()
    if not url:
        raise SystemExit("DATABASE_URL (or MIGRATION_DATABASE_URL) must be set")
    url = url.replace("postgresql+psycopg://", "postgresql://", 1)
    return ensure_remote_ssl(url)


def list_migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.is_dir():
        raise SystemExit(f"Migrations directory not found: {migrations_dir}")
    files = sorted(p for p in migrations_dir.glob("*.sql") if p.is_file())
    return files


def _ensure_tracking(conn: psycopg.Connection) -> None:
    conn.execute(TRACKING_TABLE_SQL)


def _applied_filenames(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def _schema_already_present(conn: psycopg.Connection) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema = 'public' AND table_name = 'profiles'
        )
        """
    ).fetchone()
    return bool(row and row[0])


def _bootstrap_existing(
    conn: psycopg.Connection, files: list[Path], *, dry_run: bool
) -> None:
    """Mark baseline migrations applied when the DB was migrated manually."""
    names = [f.name for f in files if f.name <= _BOOTSTRAP_THROUGH]
    if dry_run:
        logger.info(
            "Dry run: would bootstrap schema_migrations with %d baseline file(s)",
            len(names),
        )
        return
    with conn.cursor() as cur:
        for name in names:
            cur.execute(
                """
                INSERT INTO schema_migrations (filename)
                VALUES (%s)
                ON CONFLICT (filename) DO NOTHING
                """,
                (name,),
            )
    conn.commit()
    logger.info(
        "Bootstrapped schema_migrations (%d baseline file(s)); newer migrations still pending",
        len(names),
    )


def _apply_one(conn: psycopg.Connection, path: Path, *, dry_run: bool) -> None:
    sql = path.read_text(encoding="utf-8")
    if dry_run:
        logger.info("Dry run: would apply %s", path.name)
        return
    logger.info("Applying %s", path.name)
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s)",
            (path.name,),
        )
    conn.commit()
    logger.info("Applied %s", path.name)


def run_migrations(
    *,
    migrations_dir: Path | None = None,
    dry_run: bool = False,
) -> int:
    directory = migrations_dir or _migrations_dir()
    files = list_migration_files(directory)
    if not files:
        logger.info("No migration files in %s", directory)
        return 0

    dsn = _database_url()
    with psycopg.connect(dsn, cursor_factory=ClientCursor) as conn:
        _ensure_tracking(conn)
        conn.commit()

        applied = _applied_filenames(conn)
        if not applied and _schema_already_present(conn):
            _bootstrap_existing(conn, files, dry_run=dry_run)
            if dry_run:
                return 0
            applied = _applied_filenames(conn)

        pending = [f for f in files if f.name not in applied]
        if not pending:
            logger.info("Database is up to date (%d migration(s))", len(files))
            return 0

        logger.info("%d pending migration(s)", len(pending))
        for path in pending:
            _apply_one(conn, path, dry_run=dry_run)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply pending Supabase SQL migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log pending migrations without applying them",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=None,
        help="Override path to supabase/migrations",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return run_migrations(migrations_dir=args.migrations_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
