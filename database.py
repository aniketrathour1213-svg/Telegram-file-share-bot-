"""
Database Module for Telegram File Sharing & Monetization Bot.
Uses SQLite with auto-creation of tables on startup.
Thread-safe with WAL mode for concurrent access.
"""

import sqlite3
import threading
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import Config

logger = logging.getLogger(__name__)

_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """Get a thread-local database connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(
            Config.DATABASE_URL, check_same_thread=False
        )
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
        _local.conn.execute("PRAGMA busy_timeout=5000")
    return _local.conn


def init_db():
    """Create database tables if they don't exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            join_date TEXT,
            last_activity TEXT
        )
    """)

    # Files table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            unique_id TEXT UNIQUE NOT NULL,
            file_type TEXT DEFAULT 'document',
            file_name TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            caption TEXT DEFAULT '',
            uploaded_at TEXT,
            mime_type TEXT DEFAULT ''
        )
    """)

    # Downloads table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            downloaded_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (file_id) REFERENCES files(file_id)
        )
    """)

    # Views table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            file_id TEXT,
            viewed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (file_id) REFERENCES files(file_id)
        )
    """)

    # Indexes for performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_files_unique_id
        ON files(unique_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_downloads_user
        ON downloads(user_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_downloads_file
        ON downloads(file_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_views_file
        ON views(file_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_views_user
        ON views(user_id)
    """)

    conn.commit()
    logger.info("✅ Database tables initialized successfully")


# ─── User Operations ──────────────────────────────────────────────────


def add_or_update_user(
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
):
    """Add a new user or update existing user's last activity."""
    conn = get_connection()
    now = datetime.now().isoformat()
    clean_username = (username or "").strip()
    clean_first_name = (first_name or "").strip()
    conn.execute(
        """
        INSERT INTO users (user_id, username, first_name, join_date, last_activity)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = COALESCE(NULLIF(?, ''), username),
            first_name = COALESCE(NULLIF(?, ''), first_name),
            last_activity = ?
        """,
        (
            user_id,
            clean_username,
            clean_first_name,
            now,
            now,
            clean_username,
            clean_first_name,
            now,
        ),
    )
    conn.commit()


def get_total_users() -> int:
    """Get total number of registered users."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
    return row["count"] if row else 0


def get_all_users() -> List[Dict[str, Any]]:
    """Get all registered users."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY join_date DESC"
    ).fetchall()
    return [dict(row) for row in rows]


# ─── File Operations ──────────────────────────────────────────────────


def save_file(
    file_id: str,
    unique_id: str,
    file_type: str,
    file_name: Optional[str],
    file_size: Optional[int],
    caption: Optional[str],
    mime_type: Optional[str],
) -> bool:
    """Save a file record to the database. Returns True on success."""
    conn = get_connection()
    now = datetime.now().isoformat()
    try:
        conn.execute(
            """
            INSERT INTO files
                (file_id, unique_id, file_type, file_name,
                 file_size, caption, uploaded_at, mime_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                unique_id,
                file_type or "document",
                file_name or "",
                file_size or 0,
                caption or "",
                now,
                mime_type or "",
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Duplicate unique_id: {unique_id}")
        return False


def get_file_by_unique_id(unique_id: str) -> Optional[Dict[str, Any]]:
    """Get file details by unique ID."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM files WHERE unique_id = ?", (unique_id,)
    ).fetchone()
    return dict(row) if row else None


def get_file_by_file_id(file_id: str) -> Optional[Dict[str, Any]]:
    """Get file details by Telegram file_id."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM files WHERE file_id = ?", (file_id,)
    ).fetchone()
    return dict(row) if row else None


def get_all_files() -> List[Dict[str, Any]]:
    """Get all uploaded files ordered by upload time (newest first)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM files ORDER BY uploaded_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_total_files() -> int:
    """Get total number of uploaded files."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as count FROM files").fetchone()
    return row["count"] if row else 0


def delete_file(file_id: str) -> bool:
    """
    Delete a file and all related records (views + downloads).
    Returns True if deletion succeeds.
    """
    conn = get_connection()
    try:
        # delete related views
        conn.execute("DELETE FROM views WHERE file_id = ?", (file_id,))

        # delete related downloads
        conn.execute("DELETE FROM downloads WHERE file_id = ?", (file_id,))

        # delete file record
        cursor = conn.execute("DELETE FROM files WHERE file_id = ?", (file_id,))

        conn.commit()

        # if no file deleted
        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"delete_file failed for {file_id}: {e}")
        return False


# ─── Download Operations ──────────────────────────────────────────────


def record_download(user_id: int, file_id: str):
    """Record a file download event."""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO downloads (user_id, file_id, downloaded_at) VALUES (?, ?, ?)",
        (user_id, file_id, now),
    )
    conn.commit()


def get_total_downloads() -> int:
    """Get total number of downloads across all files."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as count FROM downloads").fetchone()
    return row["count"] if row else 0


# ─── View Operations ──────────────────────────────────────────────────


def record_view(
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    file_id: str,
):
    """Record a file view event."""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO views (user_id, username, first_name, file_id, viewed_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username or "",
            first_name or "",
            file_id,
            now,
        ),
    )
    conn.commit()


def get_views_by_file(file_id: str) -> List[Dict[str, Any]]:
    """Get all views for a specific file, newest first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM views WHERE file_id = ? ORDER BY viewed_at DESC",
        (file_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_total_views() -> int:
    """Get total number of file views."""
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as count FROM views").fetchone()
    return row["count"] if row else 0


def get_total_links() -> int:
    """Total unique links generated (same as files count)."""
    return get_total_files()


# ─── Statistics ───────────────────────────────────────────────────────


def get_detailed_stats() -> Dict[str, Any]:
    """Get detailed statistics for the admin dashboard."""
    conn = get_connection()

    total_users = get_total_users()
    total_files = get_total_files()
    total_links = get_total_links()
    total_downloads = get_total_downloads()
    total_views = get_total_views()

    # Top files by view count
    top_files_rows = conn.execute(
        """
        SELECT f.file_name, f.file_id, f.unique_id,
               COUNT(DISTINCT v.id) as view_count,
               COUNT(DISTINCT d.id) as download_count
        FROM files f
        LEFT JOIN views v ON f.file_id = v.file_id
        LEFT JOIN downloads d ON f.file_id = d.file_id
        GROUP BY f.file_id
        ORDER BY view_count DESC
        LIMIT 10
        """
    ).fetchall()

    top_files = []
    for row in top_files_rows:
        top_files.append(
            {
                "file_name": row["file_name"] or "Unnamed",
                "file_id": row["file_id"],
                "unique_id": row["unique_id"],
                "views": row["view_count"],
                "downloads": row["download_count"],
            }
        )

    return {
        "total_users": total_users,
        "total_files": total_files,
        "total_links": total_links,
        "total_downloads": total_downloads,
        "total_views": total_views,
        "top_files": top_files,
    }
