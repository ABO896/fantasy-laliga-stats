"""Meta route — proves the config -> app -> HTTP wiring is live before any
domain code exists.
"""

from fastapi import APIRouter

from api.deps import SettingsDep

router = APIRouter()


@router.get("/meta")
def get_meta(settings: SettingsDep):
    return {
        "app_name": "Fantasy LaLiga Stats",
        "db_path": settings.db_path,
    }
