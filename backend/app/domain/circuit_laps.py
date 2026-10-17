"""Scheduled race lap counts by OpenF1 circuit_short_name (and aliases).

OpenF1 meetings do not always expose race distance; Classification/Strategy need
an accurate lap total or race times will be systematically short/long.
"""

from __future__ import annotations

# Typical F1 Grand Prix distances (can vary slightly year to year with layout tweaks)
RACE_LAPS_BY_CIRCUIT: dict[str, int] = {
    "BAHRAIN": 57,
    "SAKHIR": 57,
    "JEDDAH": 50,
    "MELBOURNE": 58,
    "ALBERT PARK": 58,
    "SUZUKA": 53,
    "SHANGHAI": 56,
    "MIAMI": 57,
    "IMOLA": 63,
    "MONACO": 78,
    "MONTREAL": 70,
    "CIRCUIT GILLES VILLENEUVE": 70,
    "BARCELONA": 66,
    "CATALUNYA": 66,
    "SPIELBERG": 71,
    "RED BULL RING": 71,
    "SILVERSTONE": 52,
    "HUNGARORING": 70,
    "SPA-FRANCORCHAMPS": 44,
    "SPA": 44,
    "ZANDVOORT": 72,
    "MONZA": 53,
    "BAKU": 51,
    "SINGAPORE": 62,
    "MARINA BAY": 62,
    "COTA": 56,
    "AUSTIN": 56,
    "MEXICO CITY": 71,
    "RODRIGUEZ": 71,
    "INTERLAGOS": 71,
    "SAO PAULO": 71,
    "LAS VEGAS": 50,
    "LUSAIL": 57,
    "QATAR": 57,
    "YAS MARINA CIRCUIT": 58,
    "YAS MARINA": 58,
    "ABU DHABI": 58,
}

DEFAULT_RACE_LAPS = 56


def resolve_race_laps(circuit_short_name: str | None, meeting_name: str | None = None) -> int:
    circuit = (circuit_short_name or "").strip().upper()
    if circuit in RACE_LAPS_BY_CIRCUIT:
        return RACE_LAPS_BY_CIRCUIT[circuit]

    # Fuzzy aliases via substring
    for key, laps in RACE_LAPS_BY_CIRCUIT.items():
        if key in circuit or circuit in key:
            return laps

    name = (meeting_name or "").upper()
    name_hints = {
        "SINGAPORE": 62,
        "MONACO": 78,
        "MONZA": 53,
        "SPA": 44,
        "SILVERSTONE": 52,
        "HUNGAR": 70,
        "ZANDVOORT": 72,
        "BAHRAIN": 57,
        "JEDDAH": 50,
        "MIAMI": 57,
        "MONTREAL": 70,
        "CANADA": 70,
        "AUSTRIA": 71,
        "MEXICO": 71,
        "BRAZIL": 71,
        "SAO PAULO": 71,
        "LAS VEGAS": 50,
        "QATAR": 57,
        "ABU DHABI": 58,
        "AUSTRALIA": 58,
        "JAPAN": 53,
        "CHINA": 56,
        "UNITED STATES": 56,
        "AUSTIN": 56,
    }
    for hint, laps in name_hints.items():
        if hint in name:
            return laps

    return DEFAULT_RACE_LAPS
