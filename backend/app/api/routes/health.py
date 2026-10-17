from fastapi import APIRouter

from app.models.lap_time import LapTimeModel

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    model = LapTimeModel()
    return {
        "status": "ok",
        "service": "raceforesight",
        "model_ready": model.is_ready,
    }
