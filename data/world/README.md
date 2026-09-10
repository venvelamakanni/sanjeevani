# Digital-twin data

One directory per sector (`thar/`), built by `python scripts/fetch_world_data.py`.
Small vector layers are committed; rasters and road extracts are fetched to disk and gitignored.
Raw downloads are cached in `cache/` so re-runs are cheap.

| File | Layer | Source | Licence | Committed |
|---|---|---|---|---|
| `border.geojson` | India polygon (parts near the sector) | Natural Earth 10 m admin-0 countries | public domain | yes |
| `airfields.csv` | airfields in the bbox, all countries | OurAirports | public domain | yes |
| `dem.tif` | elevation, int16 metres, EGM2008 | Copernicus DEM GLO-90 (GLO-30 via config) | ESA free licence | no |
| `landcover.tif` | surface class, WorldCover codes, ~100 m | ESA WorldCover 2021 v200 | CC-BY 4.0 | no |
| `roads.geojson` | motorway / trunk / primary ways | OpenStreetMap via Overpass | ODbL | no |

## Border caveat

The border polygon is Natural Earth. It is **not authoritative**. The hard border rule
must run on Survey of India / MoD geometry before any real use. The layer carries
`authoritative: false` in its properties and every report must say so.

## Coordinate conventions

All rasters are EPSG:4326 (lat/lon on WGS84). Elevation is orthometric (above mean sea
level), matching `AircraftState.alt_m`. Distances in metres are computed in a
sector-local azimuthal equidistant projection (`sanjaya/world/projection.py`).
