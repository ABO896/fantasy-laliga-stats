"""The watchlist (DETAIL-04) — players the owner is keeping an eye on.

Membership is exposed as one id list rather than a flag on every player
payload: the browser's full player list would otherwise refetch on every
star click, and two cached copies of the same fact could disagree. Writes
are idempotent PUT/DELETE on the sub-resource ("make this membership
true/false"), so a double click is harmless, and each returns the whole new
list so the client can drop it straight into its cache.
"""

from fastapi import APIRouter, HTTPException

from api.deps import SessionDep
from storage.repository import (
    add_to_watchlist,
    get_player,
    get_watchlist_player_ids,
    remove_from_watchlist,
)

router = APIRouter()


def _serialize(session) -> dict:
    return {"playerIds": get_watchlist_player_ids(session)}


@router.get("/watchlist")
def read_watchlist(session: SessionDep):
    return _serialize(session)


@router.put("/watchlist/{player_id}")
def add_watchlist_player(player_id: int, session: SessionDep):
    if get_player(session, player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")
    add_to_watchlist(session, player_id)
    return _serialize(session)


@router.delete("/watchlist/{player_id}")
def remove_watchlist_player(player_id: int, session: SessionDep):
    remove_from_watchlist(session, player_id)
    return _serialize(session)
