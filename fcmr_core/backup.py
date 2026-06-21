"""Data backup and restore for SanGir Automations.

Creates encrypted (or plaintext) zip backups of the catalog and outputs.
Used for data safety and migration.
"""

import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fcmr_core.config import settings


def create_backup() -> Path:
    """Create a backup zip of catalog + outputs.

    Returns:
        Path to the created backup zip file.
    """
    settings.ensure_dirs()

    # Timestamp for unique backup filename
    now = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_file = settings.backups_dir / f"SAND_Backup_{now}.zip"

    # Create zip with catalog and outputs
    with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as zf:
        # Catalog
        if settings.catalog_path.exists():
            zf.write(settings.catalog_path, arcname="catalog.duckdb")

        # Session secret (for restoring auth)
        secret_file = settings.data_dir / ".session_secret"
        if secret_file.exists():
            zf.write(secret_file, arcname=".session_secret")

        # Outputs (all generated reports)
        if settings.outputs_dir.exists():
            for item in settings.outputs_dir.rglob("*"):
                if item.is_file():
                    arcname = item.relative_to(settings.data_dir)
                    zf.write(item, arcname=arcname)

    return backup_file


def list_backups() -> list[dict]:
    """List all available backups in the backups directory.

    Returns:
        List of dicts with keys: filename, path, size_mb, created_at (ISO format).
        Sorted by creation time, newest first.
    """
    settings.ensure_dirs()
    backups = []

    if not settings.backups_dir.exists():
        return backups

    for backup_file in sorted(settings.backups_dir.glob("SAND_Backup_*.zip"), reverse=True):
        size_mb = backup_file.stat().st_size / (1024 * 1024)
        # Parse timestamp from filename: SAND_Backup_YYYYMMDD_HHMMSS.zip
        try:
            timestamp_part = backup_file.stem.replace("SAND_Backup_", "")
            # Convert YYYYMMDD_HHMMSS to ISO format (basic parsing)
            date_part, time_part = timestamp_part.split("_")
            iso_time = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}Z"
        except (ValueError, IndexError):
            iso_time = "unknown"

        backups.append(
            {
                "filename": backup_file.name,
                "path": str(backup_file),
                "size_mb": round(size_mb, 2),
                "created_at": iso_time,
            }
        )

    return backups


def restore_backup(backup_zip_path: Path) -> None:
    """Restore data from a backup zip.

    WARNING: This overwrites existing catalog and outputs. Backup current data first.

    Args:
        backup_zip_path: Path to the backup .zip file.
    """
    if not backup_zip_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_zip_path}")

    settings.ensure_dirs()

    # Extract to data_dir
    with zipfile.ZipFile(backup_zip_path, "r") as zf:
        zf.extractall(settings.data_dir)
