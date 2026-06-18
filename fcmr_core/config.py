import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# On Vercel the filesystem is read-only except /tmp
_ON_VERCEL = bool(os.environ.get("VERCEL"))
_DATA_ROOT = Path("/tmp/fcmr") if _ON_VERCEL else Path(__file__).resolve().parent.parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FCMR_", env_file=".env", extra="ignore")

    # Root paths
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = _DATA_ROOT
    uploads_dir: Path = _DATA_ROOT / "uploads"
    parquet_dir: Path = _DATA_ROOT / "parquet"
    outputs_dir: Path = _DATA_ROOT / "outputs"
    reference_dir: Path = Path(__file__).resolve().parent / "reference"
    schemas_dir: Path = Path(__file__).resolve().parent / "schemas"
    catalog_path: Path = _DATA_ROOT / "catalog.duckdb"

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
        for d in (self.uploads_dir, self.parquet_dir, self.outputs_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
