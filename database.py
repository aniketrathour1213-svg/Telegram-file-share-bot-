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
