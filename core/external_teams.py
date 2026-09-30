"""Club identity across sources (INGEST-09/10's identity matching).

External sources name clubs their own way — football-data.co.uk writes
"Ath Madrid", "Espanol", "La Coruna", "Santander", "Vallecano" — while
`Player.team` holds the fantasy source's names ("Atletico Madrid",
"Espanyol", "Deportivo La Coruna", "Racing Santander", "Rayo Vallecano").

**This is an explicit alias table, not a fuzzy matcher, on purpose.** Twenty
clubs a season, a few promoted each summer: a table is small, reviewable,
and cannot silently pair "Real Madrid" with "Real Sociedad" the way a
token-overlap score can. A name missing from the table is *unmapped* — the
row is skipped and the name reported in the dataset run — never guessed.
A club promoted next summer shows up as exactly that report, and the fix is
one line here.

Canonical names for clubs currently in LaLiga are the exact `Player.team`
strings (verified against `data/fantasy.db` on 2026-09-27). Clubs not in
the current roster (relegated, or only in history) use their plain English
name; nothing joins them to a `Player` row, so there is nothing to match.
"""

import unicodedata

#: football-data.co.uk `HomeTeam`/`AwayTeam` (SP1) -> canonical club name.
FOOTBALL_DATA_TEAMS: dict[str, str] = {
    # In the 2026/27 roster — must equal `Player.team` exactly.
    "Alaves": "Alaves",
    "Ath Bilbao": "Athletic Club",
    "Ath Madrid": "Atletico Madrid",
    "Barcelona": "Barcelona",
    "Betis": "Real Betis",
    "Celta": "Celta Vigo",
    "Elche": "Elche",
    "Espanol": "Espanyol",
    "Getafe": "Getafe",
    "La Coruna": "Deportivo La Coruna",
    "Levante": "Levante",
    "Malaga": "Malaga",
    "Osasuna": "Osasuna",
    "Real Madrid": "Real Madrid",
    "Santander": "Racing Santander",
    "Sevilla": "Sevilla",
    "Sociedad": "Real Sociedad",
    "Valencia": "Valencia",
    "Vallecano": "Rayo Vallecano",
    "Villarreal": "Villarreal",
    # Recent LaLiga clubs outside the current roster — history only.
    "Almeria": "Almeria",
    "Cadiz": "Cadiz",
    "Eibar": "Eibar",
    "Girona": "Girona",
    "Granada": "Granada",
    "Huesca": "Huesca",
    "Las Palmas": "Las Palmas",
    "Leganes": "Leganes",
    "Mallorca": "Mallorca",
    "Oviedo": "Real Oviedo",
    "Sp Gijon": "Sporting Gijon",
    "Valladolid": "Real Valladolid",
}


def _key(name: str) -> str:
    """Case-, accent- and whitespace-insensitive lookup key. Normalising
    here, not fuzzy-matching, is what keeps "Alavés" == "Alaves" without
    letting two different clubs meet."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


_BY_KEY = {_key(k): v for k, v in FOOTBALL_DATA_TEAMS.items()}


def canonical_team(source_name: str | None) -> str | None:
    """The canonical club name for a football-data.co.uk team name, or
    `None` when the name is not in the alias table."""
    if not source_name:
        return None
    return _BY_KEY.get(_key(source_name))
