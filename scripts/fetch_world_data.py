"""Fetch and clip the digital-twin data layers for a sector.

Sources (all open, all public):
    border     Natural Earth 10 m admin-0 countries (public domain). NOT authoritative.
    airfields  OurAirports (public domain)
    dem        Copernicus DEM GLO-90 / GLO-30 COGs on AWS (ESA, free licence)
    landcover  ESA WorldCover 2021 v200 COGs on AWS (CC-BY 4.0), read remotely and decimated
    roads      OpenStreetMap via Overpass (ODbL)

Usage:
    python scripts/fetch_world_data.py                       # all layers, sector_thar.yaml
    python scripts/fetch_world_data.py --layers border,airfields
    python scripts/fetch_world_data.py --sector sector_thar.yaml --data-dir /elsewhere

Raw downloads are cached under data/world/cache/ so re-runs only rebuild outputs.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
import shapefile
from rasterio.enums import Resampling
from rasterio.merge import merge
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run from a checkout without installing
from sanjaya.config import BoundingBox, SectorConfig, load_default, load_yaml  # noqa: E402
from sanjaya.world import paths

UA = "SANJAYA/0.1 (Project SANJEEVANI research prototype)"
DEM_NODATA = -32768

NE_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OVERPASS_URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
WORLDCOVER_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
DEM_URLS = {
    "glo90": "https://copernicus-dem-90m.s3.amazonaws.com/Copernicus_DSM_COG_30_{tile}_DEM/Copernicus_DSM_COG_30_{tile}_DEM.tif",
    "glo30": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{tile}_DEM/Copernicus_DSM_COG_10_{tile}_DEM.tif",
}


# ----------------------------------------------------------------------------- helpers

def log(msg: str) -> None:
    print(msg, flush=True)


def http_get(url: str, data: bytes | None = None, retries: int = 3, timeout: int = 600) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            wait = 5 * (attempt + 1)
            log(f"    retry {attempt + 1}/{retries} after error: {e} (sleeping {wait}s)")
            time.sleep(wait)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def http_exists(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    return dest


def bbox_poly(b: BoundingBox) -> Polygon:
    return box(b.lon_min, b.lat_min, b.lon_max, b.lat_max)


def dem_tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00"


def worldcover_tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{ns}{abs(lat):02d}{ew}{abs(lon):03d}"


# ----------------------------------------------------------------------------- layers

def fetch_border(sector: SectorConfig, out: Path) -> None:
    log("[border] Natural Earth 10m admin-0 countries")
    zpath = download(NE_URL, paths.cache_dir() / "ne_10m_admin_0_countries.zip")
    with zipfile.ZipFile(zpath) as z:
        names = {Path(n).suffix.lower(): n for n in z.namelist()}
        rdr = shapefile.Reader(shp=io.BytesIO(z.read(names[".shp"])), dbf=io.BytesIO(z.read(names[".dbf"])),
                               shx=io.BytesIO(z.read(names[".shx"])))
        fields = [f[0] for f in rdr.fields[1:]]
        i_admin = fields.index("ADMIN")
        geom = None
        for sr in rdr.iterShapeRecords():
            if sr.record[i_admin] == "India":
                geom = shape(sr.shape.__geo_interface__)
                break
    if geom is None:
        raise RuntimeError("India not found in Natural Earth")
    if not geom.is_valid:
        geom = geom.buffer(0)

    # Keep the parts that matter to this sector: any polygon within 1.5 deg of the bbox.
    near = bbox_poly(sector.bbox).buffer(1.5)
    parts = [g for g in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]) if g.intersects(near)]
    kept = parts[0] if len(parts) == 1 else MultiPolygon(parts)
    n_vertices = sum(len(p.exterior.coords) for p in parts)
    feat = {
        "type": "Feature",
        "geometry": mapping(kept),
        "properties": {
            "country": "India",
            "iso_a3": "IND",
            "source": "Natural Earth 10m admin_0_countries",
            "source_url": NE_URL,
            "licence": "public domain",
            "fetched": date.today().isoformat(),
            "authoritative": False,
            "caveat": "NOT authoritative. Replace with Survey of India / MoD geometry before any real use.",
            "parts_kept": len(parts),
        },
    }
    out.write_text(json.dumps({"type": "FeatureCollection", "features": [feat]}, separators=(",", ":")), encoding="utf-8")
    log(f"[border] wrote {out} ({len(parts)} polygon(s), {n_vertices} vertices, {out.stat().st_size // 1024} KB)")


def fetch_airfields(sector: SectorConfig, out: Path) -> None:
    log("[airfields] OurAirports")
    src = download(OURAIRPORTS_URL, paths.cache_dir() / "ourairports_airports.csv")
    b = sector.bbox
    pad = 0.25
    keep_types = set(sector.world.airfield_types)
    rows = []
    with open(src, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                lat, lon = float(r["latitude_deg"]), float(r["longitude_deg"])
            except ValueError:
                continue
            if r["type"] not in keep_types or r["name"].startswith("[Duplicate]"):
                continue
            if not (b.lat_min - pad <= lat <= b.lat_max + pad and b.lon_min - pad <= lon <= b.lon_max + pad):
                continue
            elev_ft = (r.get("elevation_ft") or "").strip()
            rows.append({
                "ident": r["ident"], "type": r["type"], "name": r["name"],
                "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
                "elevation_m": f"{float(elev_ft) * 0.3048:.1f}" if elev_ft else "",
                "iso_country": r.get("iso_country", ""), "municipality": r.get("municipality", ""),
                "iata_code": r.get("iata_code", ""),
                "gps_code": r.get("gps_code") or r.get("icao_code") or "",
            })
    rows.sort(key=lambda r: r["ident"])
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    by_country: dict[str, int] = {}
    for r in rows:
        by_country[r["iso_country"]] = by_country.get(r["iso_country"], 0) + 1
    log(f"[airfields] wrote {out}: {len(rows)} airfields {by_country}")


def fetch_dem(sector: SectorConfig, out: Path) -> None:
    product = sector.world.dem_product
    b = sector.bbox
    log(f"[dem] Copernicus {product}")
    url_t = DEM_URLS[product]
    tiles: list[Path] = []
    for lat in range(math.floor(b.lat_min), math.ceil(b.lat_max)):
        for lon in range(math.floor(b.lon_min), math.ceil(b.lon_max)):
            name = dem_tile_name(lat, lon)
            url = url_t.format(tile=name)
            dest = paths.cache_dir() / "dem" / product / f"{name}.tif"
            if not dest.exists():
                if not http_exists(url):
                    log(f"    {name}: no tile (sea)")
                    continue
                log(f"    {name}: downloading")
                download(url, dest)
            tiles.append(dest)
    log(f"[dem] {len(tiles)} tiles, mosaicking to bbox")
    srcs = [rasterio.open(t) for t in tiles]
    try:
        arr, transform = merge(srcs, bounds=(b.lon_min, b.lat_min, b.lon_max, b.lat_max),
                               nodata=DEM_NODATA, dtype="float32")
    finally:
        for s in srcs:
            s.close()
    data = arr[0]
    out_arr = np.where(data == DEM_NODATA, DEM_NODATA, np.rint(data)).astype(np.int16)
    profile = {
        "driver": "GTiff", "dtype": "int16", "count": 1, "nodata": DEM_NODATA,
        "width": out_arr.shape[1], "height": out_arr.shape[0], "crs": "EPSG:4326", "transform": transform,
        "tiled": True, "blockxsize": 512, "blockysize": 512, "compress": "deflate", "predictor": 2,
    }
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(out_arr, 1)
        dst.update_tags(source=f"Copernicus DEM {product.upper()}", vertical_datum="EGM2008", units="m",
                        fetched=date.today().isoformat())
    valid = out_arr != DEM_NODATA
    log(f"[dem] wrote {out}: {out_arr.shape[1]}x{out_arr.shape[0]} px, "
        f"elev {out_arr[valid].min()}..{out_arr[valid].max()} m, {out.stat().st_size // (1 << 20)} MB")


def fetch_landcover(sector: SectorConfig, out: Path) -> None:
    b = sector.bbox
    res = sector.world.landcover_res_deg
    log(f"[landcover] ESA WorldCover 2021 at {res} deg, read remotely")
    urls = []
    for lat in range(math.floor(b.lat_min / 3) * 3, math.ceil(b.lat_max), 3):
        for lon in range(math.floor(b.lon_min / 3) * 3, math.ceil(b.lon_max), 3):
            url = WORLDCOVER_URL.format(tile=worldcover_tile_name(lat, lon))
            if http_exists(url):
                urls.append(url)
            else:
                log(f"    {worldcover_tile_name(lat, lon)}: no tile")
    log(f"[landcover] {len(urls)} tiles")
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
           "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "VSI_CACHE": "TRUE"}
    with rasterio.Env(**env):
        srcs = [rasterio.open(u) for u in urls]
        try:
            arr, transform = merge(srcs, bounds=(b.lon_min, b.lat_min, b.lon_max, b.lat_max), res=(res, res),
                                   nodata=0, dtype="uint8", resampling=Resampling.nearest)
        finally:
            for s in srcs:
                s.close()
    data = arr[0]
    profile = {
        "driver": "GTiff", "dtype": "uint8", "count": 1, "nodata": 0,
        "width": data.shape[1], "height": data.shape[0], "crs": "EPSG:4326", "transform": transform,
        "tiled": True, "blockxsize": 512, "blockysize": 512, "compress": "deflate",
    }
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(source="ESA WorldCover 2021 v200", licence="CC-BY 4.0", fetched=date.today().isoformat())
    codes, counts = np.unique(data, return_counts=True)
    mix = {int(c): round(100 * n / data.size, 1) for c, n in zip(codes, counts)}
    log(f"[landcover] wrote {out}: {data.shape[1]}x{data.shape[0]} px, class mix % {mix}")


def fetch_roads(sector: SectorConfig, out: Path) -> None:
    b = sector.bbox
    classes = "|".join(sector.world.road_classes)
    log(f"[roads] OSM via Overpass, highway in ({classes})")
    feats: dict[int, dict] = {}
    step = 2.0
    lat = b.lat_min
    while lat < b.lat_max:
        lon = b.lon_min
        while lon < b.lon_max:
            s, n = lat, min(lat + step, b.lat_max)
            w, e = lon, min(lon + step, b.lon_max)
            q = f'[out:json][timeout:300];way["highway"~"^({classes})$"]({s},{w},{n},{e});out geom;'
            body = urllib.parse.urlencode({"data": q}).encode()
            res: bytes | None = None
            for url in OVERPASS_URLS:
                try:
                    res = http_get(url, data=body, retries=2)
                    break
                except RuntimeError as ex:
                    log(f"    {url}: {ex}")
            if res is None:
                raise RuntimeError("all Overpass endpoints failed")
            els = json.loads(res).get("elements", [])
            new = 0
            for el in els:
                if el.get("type") != "way" or el["id"] in feats or len(el.get("geometry", [])) < 2:
                    continue
                tags = el.get("tags", {})
                feats[el["id"]] = {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[g["lon"], g["lat"]] for g in el["geometry"]]},
                    "properties": {"osm_id": el["id"], "highway": tags.get("highway", ""), "ref": tags.get("ref", ""),
                                   "name": tags.get("name", ""), "surface": tags.get("surface", ""),
                                   "lanes": tags.get("lanes", ""), "oneway": tags.get("oneway", "")},
                }
                new += 1
            log(f"    tile {s:.1f},{w:.1f}..{n:.1f},{e:.1f}: {len(els)} ways, {new} new")
            time.sleep(2)
            lon += step
        lat += step
    gj = {"type": "FeatureCollection",
          "properties": {"source": "OpenStreetMap via Overpass", "licence": "ODbL", "fetched": date.today().isoformat(),
                         "classes": list(sector.world.road_classes)},
          "features": list(feats.values())}
    out.write_text(json.dumps(gj, separators=(",", ":")), encoding="utf-8")
    log(f"[roads] wrote {out}: {len(feats)} ways, {out.stat().st_size // (1 << 20)} MB")


LAYERS = {
    "border": (fetch_border, paths.BORDER_FILE),
    "airfields": (fetch_airfields, paths.AIRFIELDS_FILE),
    "dem": (fetch_dem, paths.DEM_FILE),
    "landcover": (fetch_landcover, paths.LANDCOVER_FILE),
    "roads": (fetch_roads, paths.ROADS_FILE),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sector", default="sector_thar.yaml", help="sector config (name in sanjaya/config or a path)")
    ap.add_argument("--layers", default=",".join(LAYERS), help="comma-separated subset of " + ",".join(LAYERS))
    ap.add_argument("--data-dir", default=None, help="output dir (default data/world/<sector>)")
    ap.add_argument("--force", action="store_true", help="rebuild layers whose output already exists")
    args = ap.parse_args()

    sp = Path(args.sector)
    sector = load_yaml(sp, SectorConfig) if sp.exists() else load_default(SectorConfig, args.sector)
    d = Path(args.data_dir) if args.data_dir else paths.sector_dir(sector.name)
    d.mkdir(parents=True, exist_ok=True)
    wanted = [x.strip() for x in args.layers.split(",") if x.strip()]
    bad = [x for x in wanted if x not in LAYERS]
    if bad:
        sys.exit(f"unknown layers: {bad}")

    b = sector.bbox
    log(f"sector={sector.name} bbox=({b.lat_min},{b.lon_min})..({b.lat_max},{b.lon_max}) out={d}")
    for name in wanted:
        fn, fname = LAYERS[name]
        out = d / fname
        if out.exists() and not args.force:
            log(f"[{name}] exists, skipping ({out}); use --force to rebuild")
            continue
        t0 = time.time()
        fn(sector, out)
        log(f"[{name}] done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
