from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
MODEL_DIR = Path(__file__).resolve().parent / "models" / "artifacts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RF_", env_file=".env", extra="ignore")

    openf1_base_url: str = "https://api.openf1.org/v1"
    openf1_max_rps: float = 2.5
    default_season: int = 2026
    default_circuit_short: str = "COTA"
    default_country: str = "United States"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    cache_dir: Path = CACHE_DIR
    model_dir: Path = MODEL_DIR
    race_laps_cota: int = 56
    pit_loss_extra_seconds: float = 18.0


settings = Settings()
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
