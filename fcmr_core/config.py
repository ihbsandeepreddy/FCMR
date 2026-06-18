import os
import secrets
import sys
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# On Vercel the filesystem is read-only except /tmp
_ON_VERCEL = bool(os.environ.get("VERCEL"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FCMR_", env_file=".env", extra="ignore")

    # Root paths — frozen-aware (PyInstaller bundles are read-only; use per-user dir)
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = ""  # Set in __init__
    uploads_dir: Path = ""  # Set in __init__
    parquet_dir: Path = ""  # Set in __init__
    outputs_dir: Path = ""  # Set in __init__
    logs_dir: Path = ""  # Set in __init__
    backups_dir: Path = ""  # Set in __init__
    reference_dir: Path = Path(__file__).resolve().parent / "reference"
    schemas_dir: Path = Path(__file__).resolve().parent / "schemas"
    catalog_path: Path = ""  # Set in __init__

    # Backend and networking
    backend_port: int = 8000

    # Ingest tuning — keep chunk size low enough to stay inside 15 GB RAM when
    # processing 5M-row CSVs with many wide columns.
    ingest_chunk_rows: int = 100_000
    max_upload_bytes: int = 2 * 1024**3  # 2 GB hard limit per upload

    # Column mapping — fuzzy match threshold (0.0–1.0; suggest if >= this score)
    fuzzy_match_threshold: float = 0.6

    # Aadhaar — salt is environment-injectable; do NOT hardcode a real value here.
    aadhaar_hash_salt: str = "change-me-via-FCMR_AADHAAR_HASH_SALT"

    # Session secret for signed cookies; persisted in data/ so sessions survive restarts
    session_secret: str = ""

    def __init__(self, **data):
        super().__init__(**data)

        # Resolve data_dir based on deployment environment
        if _ON_VERCEL:
            # On Vercel the filesystem is read-only except /tmp
            data_root = Path("/tmp/fcmr")
        elif getattr(sys, "frozen", False):
            # Running as PyInstaller bundle — use per-user appdata path
            if sys.platform == "win32":
                data_root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "SanGirAutomations"
            else:
                data_root = Path.home() / ".sangir"
        else:
            # Dev mode — use repo-relative data/ directory
            data_root = self.base_dir / "data"

        self.data_dir = data_root
        self.uploads_dir = self.data_dir / "uploads"
        self.parquet_dir = self.data_dir / "parquet"
        self.outputs_dir = self.data_dir / "outputs"
        self.logs_dir = self.data_dir / "logs"
        self.backups_dir = self.data_dir / "backups"
        self.catalog_path = self.data_dir / "catalog.duckdb"

        # If session_secret is not provided, load from or generate one in data/
        if not self.session_secret:
            if _ON_VERCEL:
                # On Vercel each container is stateless — secret MUST be fixed via env var
                # so session cookies are valid across all containers.
                # Set FCMR_SESSION_SECRET in Vercel project environment variables.
                raise ValueError(
                    "FCMR_SESSION_SECRET environment variable must be set on Vercel. "
                    "Go to Vercel → Project → Settings → Environment Variables and add "
                    "FCMR_SESSION_SECRET with a long random string."
                )
            else:
                secret_file = self.data_dir / ".session_secret"
                if secret_file.exists():
                    self.session_secret = secret_file.read_text().strip()
                else:
                    self.session_secret = secrets.token_urlsafe(32)
                    self.data_dir.mkdir(parents=True, exist_ok=True)
                    secret_file.write_text(self.session_secret)

    def ensure_dirs(self) -> None:
        for d in (self.uploads_dir, self.parquet_dir, self.outputs_dir, self.logs_dir, self.backups_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
