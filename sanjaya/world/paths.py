"""Where a sector's digital-twin data lives on disk.

Layout (per sector, under data/world/<sector>/):
    border.geojson    India polygon (committed; small)
    airfields.csv     airfields in and around the bbox (committed; small)
    dem.tif           Copernicus DEM mosaic clipped to the bbox (fetched; gitignored)
    landcover.tif     ESA WorldCover decimated to the bbox (fetched; gitignored)
    roads.geojson     OSM major roads in the bbox (fetched; gitignored)

Override the root with SANJAYA_DATA_DIR when the data lives elsewhere.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BORDER_FILE = "border.geojson"
AIRFIELDS_FILE = "airfields.csv"
DEM_FILE = "dem.tif"
LANDCOVER_FILE = "landcover.tif"
ROADS_FILE = "roads.geojson"


def data_root() -> Path:
    env = os.environ.get("SANJAYA_DATA_DIR")
    return Path(env) if env else ROOT / "data" / "world"


def sector_dir(sector_name: str) -> Path:
    return data_root() / sector_name


def cache_dir() -> Path:
    """Raw downloads (tiles, zips) kept so re-fetches are cheap."""
    return data_root() / "cache"
