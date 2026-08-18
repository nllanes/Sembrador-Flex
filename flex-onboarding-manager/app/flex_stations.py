"""Catálogo de estaciones Amazon Flex (portado desde monitor_saas).

Fuente: FLEX_STATIONS en monitor_saas/dashboard/index.html
Filtrado: estado US → radio ~125 km desde punto geocodificado (ciudad/ZIP).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

METRO_RADIUS_KM = 125.0
_DATA_FILE = Path(__file__).resolve().parent / "data" / "flex_stations.json"

_STATE_SUFFIX = re.compile(r",\s*([A-Z]{2})\s*$")

US_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}


def _nominatim_ua() -> str:
    return (
        os.getenv("NOMINATIM_USER_AGENT") or "FlexOnboardingManager/1.0 (local dev)"
    ).strip()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@lru_cache
def load_stations() -> tuple[dict[str, Any], ...]:
    raw = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return tuple(raw)


def catalog_state_codes() -> frozenset[str]:
    """Códigos US presentes en el catálogo de estaciones."""
    codes: set[str] = set()
    for station in load_stations():
        code = station_state_code(station)
        if code:
            codes.add(code)
    return frozenset(codes)


def list_us_states() -> list[dict[str, Any]]:
    """Lista de estados US para selectores (nombre + si hay estaciones en catálogo)."""
    catalog = catalog_state_codes()
    return [
        {
            "code": code,
            "name": US_STATE_NAMES[code],
            "has_stations": code in catalog,
        }
        for code in sorted(US_STATE_NAMES.keys(), key=lambda c: US_STATE_NAMES[c])
    ]


def station_state_code(station: dict[str, Any]) -> str | None:
    city = str(station.get("city") or "")
    if re.search(r"washington\s*dc", city, re.I):
        return "DC"
    if re.search(r"new\s*jersey", city, re.I):
        return "NJ"
    m = _STATE_SUFFIX.search(city)
    return m.group(1) if m else None


def geocode_us(query: str) -> dict[str, Any]:
    """Geocodifica dirección/ZIP/ciudad en EE.UU. vía Nominatim (como monitor_saas)."""
    q = (query or "").strip()
    if len(q) < 3:
        return {"ok": False, "detail": "Consulta demasiado corta"}

    search_q = q if "usa" in q.lower() or "united states" in q.lower() else f"{q}, USA"
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": search_q,
                "format": "json",
                "addressdetails": 1,
                "limit": 1,
                "countrycodes": "us",
            },
            headers={"User-Agent": _nominatim_ua()},
            timeout=18,
        )
        if r.status_code != 200:
            return {"ok": False, "detail": f"nominatim HTTP {r.status_code}"}
        rows = r.json()
        if not rows:
            return {"ok": False, "detail": "Sin resultados en EE.UU."}
        row = rows[0]
        addr = row.get("address") or {}
        iso = addr.get("ISO3166-2-lvl4")
        state_code = None
        if isinstance(iso, str) and iso.upper().startswith("US-"):
            state_code = iso.split("-", 1)[-1].upper()
        return {
            "ok": True,
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "label": row.get("display_name"),
            "state_code": state_code,
            "state_name": addr.get("state"),
            "postcode": addr.get("postcode"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("geocode failed: %s", exc)
        return {"ok": False, "detail": str(exc)}


def _normalize_state(state: str | None) -> str | None:
    if not state:
        return None
    s = state.strip().upper()
    return s if len(s) == 2 else None


def _city_matches(station: dict[str, Any], city: str) -> bool:
    c = city.strip().lower()
    sc = str(station.get("city") or "").lower()
    name = str(station.get("name") or "").lower()
    return c in sc or c in name


def search_flex_stations(
    *,
    state: str | None = None,
    city: str | None = None,
    zip_code: str | None = None,
) -> dict[str, Any]:
    """Lista estaciones Flex del catálogo monitor_saas filtradas por ubicación."""
    state_norm = _normalize_state(state)
    city = (city or "").strip() or None
    zip_code = (zip_code or "").strip() or None

    geo: dict[str, Any] | None = None
    anchor_lat: float | None = None
    anchor_lon: float | None = None

    # Prioridad: ZIP → geocode; si no, ciudad (+ estado); si no, solo estado.
    if zip_code:
        geo = geocode_us(zip_code)
        if geo.get("ok"):
            anchor_lat, anchor_lon = geo["lat"], geo["lon"]
            if not state_norm and geo.get("state_code"):
                state_norm = geo["state_code"]
    elif city:
        q = f"{city}, {state_norm}" if state_norm else city
        geo = geocode_us(q)
        if geo.get("ok"):
            anchor_lat, anchor_lon = geo["lat"], geo["lon"]
            if not state_norm and geo.get("state_code"):
                state_norm = geo["state_code"]

    stations = list(load_stations())
    if state_norm:
        stations = [s for s in stations if station_state_code(s) == state_norm]

    if city and not zip_code:
        by_city = [s for s in stations if _city_matches(s, city)]
        if by_city:
            stations = by_city

    results: list[dict[str, Any]] = []
    for s in stations:
        dist: float | None = None
        if anchor_lat is not None and anchor_lon is not None:
            dist = round(haversine_km(anchor_lat, anchor_lon, s["lat"], s["lng"]), 1)
        results.append(
            {
                "code": s["code"],
                "name": s["name"],
                "city": s["city"],
                "state": station_state_code(s),
                "lat": s["lat"],
                "lng": s["lng"],
                "distance_km": dist,
            }
        )

    if anchor_lat is not None:
        near = [r for r in results if r["distance_km"] is not None and r["distance_km"] <= METRO_RADIUS_KM]
        if near:
            results = near
        results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 9999)

    return {
        "query": {"state": state_norm, "city": city, "zip_code": zip_code},
        "geocoded": geo,
        "radius_km": METRO_RADIUS_KM,
        "source": "monitor_saas_catalog",
        "uses_amazon_api": False,
        "message": (
            "Estaciones del catálogo Flex usado en monitor_saas (getOfferFiltersOptions / FLEX_STATIONS). "
            "NO consulta Amazon en vivo; orienta dónde suelen operar estaciones para onboarding."
        ),
        "total": len(results),
        "stations": results,
    }


def station_code_index() -> dict[str, str]:
    """Mapa código de estación → estado US (para agrupar siembras en el panel)."""
    return {s["code"]: station_state_code(s) for s in load_stations()}
