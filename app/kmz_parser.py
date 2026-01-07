import zipfile
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

import pandas as pd
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

def _read_doc_kml_bytes(kmz_path: str) -> bytes:
    with zipfile.ZipFile(kmz_path, "r") as z:
        # Umumnya doc.kml
        return z.read("doc.kml")

def _find_folder(root: ET.Element, folder_name: str) -> Optional[ET.Element]:
    for f in root.findall(".//kml:Folder", KML_NS):
        name = f.findtext("kml:name", default="", namespaces=KML_NS).strip()
        if name == folder_name:
            return f
    return None

def _extract_points(folder: ET.Element, id_col: str) -> pd.DataFrame:
    rows = []
    for pm in folder.findall(".//kml:Placemark", KML_NS):
        coord_el = pm.find(".//kml:Point/kml:coordinates", KML_NS)
        if coord_el is None:
            continue
        name = pm.findtext("kml:name", default="", namespaces=KML_NS).strip()
        lon, lat, *_ = [float(x) for x in coord_el.text.strip().split(",")]
        rows.append({id_col: name, "lon": lon, "lat": lat})
    return pd.DataFrame(rows)

def _extract_polygons(folder: ET.Element) -> List[Tuple[str, Polygon]]:
    polys = []
    for pm in folder.findall(".//kml:Placemark", KML_NS):
        poly_el = pm.find(".//kml:Polygon", KML_NS)
        if poly_el is None:
            continue

        name = pm.findtext("kml:name", default="", namespaces=KML_NS).strip()
        coords_el = poly_el.find(".//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates", KML_NS)
        if coords_el is None:
            continue

        coords = []
        for trip in coords_el.text.strip().split():
            lon, lat, *_ = trip.split(",")
            coords.append((float(lon), float(lat)))

        if len(coords) >= 3:
            polys.append((name, Polygon(coords)))
    return polys

def convert_homepass_kmz(kmz_path: str) -> pd.DataFrame:
    root = ET.fromstring(_read_doc_kml_bytes(kmz_path))
    fat_folder = _find_folder(root, "FAT")
    hp_folder = _find_folder(root, "HP") or _find_folder(root, "HOME")

    if fat_folder is None or hp_folder is None:
        raise ValueError("Folder FAT atau HP/HOME tidak ditemukan di KMZ.")

    fat_polys = _extract_polygons(fat_folder)
    hp_df = _extract_points(hp_folder, "homepass_id")

    prepared = [(name, prep(poly)) for name, poly in fat_polys]

    assigned = []
    for lon, lat in zip(hp_df["lon"], hp_df["lat"]):
        pt = Point(lon, lat)
        chosen = None
        for name, g in prepared:
            if g.contains(pt) or g.covers(pt):
                chosen = name
                break
        assigned.append(chosen)

    hp_df["fat_boundary"] = assigned
    return hp_df[["homepass_id", "lat", "lon", "fat_boundary"]]

def convert_pole_kmz(kmz_path: str) -> pd.DataFrame:
    root = ET.fromstring(_read_doc_kml_bytes(kmz_path))
    pole_folder = _find_folder(root, "POLE")
    fat_folder = _find_folder(root, "FAT")

    if pole_folder is None or fat_folder is None:
        raise ValueError("Folder POLE atau FAT tidak ditemukan di KMZ.")

    poles = _extract_points(pole_folder, "pole_id")
    fats = _extract_points(fat_folder, "fat_id")

    import math
    def haversine_m(lat1, lon1, lat2, lon2) -> float:
        R = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
        return 2 * R * math.asin(math.sqrt(a))

    fats_list = fats.to_dict("records")
    nearest = []
    distm = []
    for _, r in poles.iterrows():
        best_name, best_d = None, float("inf")
        for f in fats_list:
            d = haversine_m(r["lat"], r["lon"], f["lat"], f["lon"])
            if d < best_d:
                best_d, best_name = d, f["fat_id"]
        nearest.append(best_name)
        distm.append(best_d)

    poles["nearest_fat"] = nearest
    poles["dist_to_fat_m"] = distm
    return poles[["pole_id", "lat", "lon", "nearest_fat", "dist_to_fat_m"]]
