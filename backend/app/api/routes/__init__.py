from fastapi import APIRouter

from .health import router as health_router
from .models import router as models_router
from .predictions import router as predictions_router
from .races import router as races_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(races_router)
api_router.include_router(models_router)
api_router.include_router(predictions_router)
