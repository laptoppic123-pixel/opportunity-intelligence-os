from dataclasses import dataclass, field
from decimal import Decimal
import os
from pathlib import Path
from uuid import UUID
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEMO_OWNER = "00000000-0000-4000-8000-000000000002"


def flag(name, default=False):
    return os.getenv(name, str(default)).lower() in {"true", "1", "yes"}


@dataclass
class Settings:
    demo: bool = False
    live: bool = False
    activated: bool = False
    paid: bool = False
    owner: str = ""
    supabase_url: str = ""
    project_ref: str = "vaxesikpcgrdxzqikyur"
    secret_key: str = field(default="", repr=False)
    monthly_limit: Decimal = Decimal("20")
    paid_stop: Decimal = Decimal("19")
    max_requests: int = 10
    max_documents: int = 30
    max_seconds: int = 180
    retention_days: int = 90
    data_dir: Path = ROOT / ".local"
    sources_file: Path = ROOT / "configs/sources.yaml"

    @classmethod
    def load(cls, *, demo=None):
        load_dotenv(ROOT / ".env", override=False)
        return cls(
            demo=flag("OI_DEMO_MODE") if demo is None else demo,
            live=flag("OI_LIVE_ENABLED"),
            activated=flag("OI_ACTIVATED"),
            paid=flag("OI_PAID_ENABLED"),
            owner=os.getenv("OI_OWNER_ID", ""),
            supabase_url=os.getenv("SUPABASE_URL", ""),
            project_ref=os.getenv("OI_EXPECTED_PROJECT_REF", "vaxesikpcgrdxzqikyur"),
            secret_key=os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            monthly_limit=Decimal(os.getenv("OI_MONTHLY_LIMIT_USD", "20")),
            paid_stop=Decimal(os.getenv("OI_INTERNAL_PAID_STOP_USD", "19")),
            max_requests=min(30, max(1, int(os.getenv("OI_MAX_REQUESTS", "10")))),
            max_documents=min(100, max(1, int(os.getenv("OI_MAX_DOCUMENTS", "30")))),
            max_seconds=min(600, max(10, int(os.getenv("OI_MAX_SECONDS", "180")))),
            retention_days=max(7, int(os.getenv("OI_RETENTION_DAYS", "90"))),
            data_dir=Path(os.getenv("OI_DATA_DIR", str(ROOT / ".local"))),
        )

    def require_live(self):
        if self.demo or not self.live or not self.activated:
            raise PermissionError(
                "Live access is disabled. Activation and OI_LIVE_ENABLED=true are required."
            )

    def require_connection(self):
        if not self.supabase_url.startswith("https://") or not self.secret_key:
            raise ValueError("Supabase URL and server-only secret key are missing. Run oi doctor.")
        if self.supabase_url.rstrip("/") != "https://" + self.project_ref + ".supabase.co":
            raise ValueError(
                "Supabase URL does not match the dedicated project reference. Existing projects are protected."
            )
        UUID(self.owner)

    @property
    def namespace(self):
        return DEMO_OWNER if self.demo else str(UUID(self.owner))
