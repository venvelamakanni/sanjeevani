"""Airfield database for a sector, with nearest-k queries.

Source for the prototype is the OurAirports open dataset, filtered to the
sector bbox by scripts/fetch_world_data.py. Every airfield in the box is kept,
including those across the border, because this layer describes the world; the
border rule decides what is allowed.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sanjaya.core.geodesy import LatLon, bearing_deg, distance_m

COLUMNS = ("ident", "type", "name", "lat", "lon", "elevation_m", "iso_country", "municipality", "iata_code", "gps_code")


@dataclass(frozen=True, slots=True)
class Airfield:
    ident: str
    type: str
    name: str
    pos: LatLon
    elevation_m: float | None
    iso_country: str
    municipality: str = ""
    iata_code: str = ""
    gps_code: str = ""


@dataclass(frozen=True, slots=True)
class AirfieldFix:
    """An airfield as seen from a query point."""
    airfield: Airfield
    distance_m: float
    bearing_deg: float


class AirfieldLayer:
    def __init__(self, airfields: list[Airfield]):
        self.airfields = list(airfields)
        idents = [a.ident for a in self.airfields]
        if len(set(idents)) != len(idents):
            raise ValueError("duplicate airfield ident")

    @classmethod
    def from_csv(cls, path: Path | str) -> "AirfieldLayer":
        out: list[Airfield] = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"airfields file missing columns: {missing}")
            for r in reader:
                elev = r["elevation_m"].strip()
                out.append(Airfield(
                    ident=r["ident"].strip(), type=r["type"].strip(), name=r["name"].strip(),
                    pos=LatLon(lat=float(r["lat"]), lon=float(r["lon"])),
                    elevation_m=float(elev) if elev else None,
                    iso_country=r["iso_country"].strip(), municipality=r["municipality"].strip(),
                    iata_code=r["iata_code"].strip(), gps_code=r["gps_code"].strip(),
                ))
        return cls(out)

    def __len__(self) -> int:
        return len(self.airfields)

    def by_ident(self, ident: str) -> Airfield:
        for a in self.airfields:
            if a.ident == ident:
                return a
        raise KeyError(ident)

    def nearest(self, p: LatLon, k: int = 3) -> list[AirfieldFix]:
        """The k nearest airfields by geodesic distance, nearest first."""
        if k < 0:
            raise ValueError("k must be >= 0")
        fixes = [AirfieldFix(a, distance_m(p, a.pos), bearing_deg(p, a.pos)) for a in self.airfields]
        fixes.sort(key=lambda f: (f.distance_m, f.airfield.ident))
        return fixes[:k]
