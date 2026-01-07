import os
import sqlite3
import time
from typing import Optional, Tuple

import httpx

DB_PATH = "/data/geocache.sqlite3"


def _init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
      CREATE TABLE IF NOT EXISTS geocache (
        key TEXT PRIMARY KEY,
        road TEXT,
        display_name TEXT,
        ts INTEGER
      )
    """)
    conn.commit()
    conn.close()


def _key(lat: float, lon: float) -> str:
    return f"{round(lat, 6)},{round(lon, 6)}"


async def reverse_geocode_road(lat: float, lon: float, user_agent: str) -> Tuple[Optional[str], Optional[str]]:
    _init_db()
    k = _key(lat, lon)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT road, display_name FROM geocache WHERE key=?", (k,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0], row[1]

    throttle = float(os.getenv("GEOCODE_THROTTLE_SECONDS", "1.05"))
    time.sleep(throttle)

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params, headers={"User-Agent": user_agent})
        r.raise_for_status()
        data = r.json()

    address = data.get("address", {}) or {}
    road = address.get("road") or address.get("residential") or address.get("neighbourhood")
    display = data.get("display_name")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO geocache(key, road, display_name, ts) VALUES(?,?,?, strftime('%s','now'))",
        (k, road, display),
    )
    conn.commit()
    conn.close()
    return road, display
