import os
import tempfile
import zipfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from kmz_parser import detect_types, convert_homepass, convert_pole
from geocode import reverse_geocode_road

APP_USER_AGENT = os.getenv(
    "APP_USER_AGENT",
    "KMZ2CSV RuangNalar (contact: admin@ruangnalar.online)"
)

app = FastAPI(title="KMZ/KML to CSV Converter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
def home():
    return "<h3>Backend OK. Open web via Nginx.</h3>"


def _ensure_kml_kmz(filename: str):
    low = filename.lower()
    if not (low.endswith(".kmz") or low.endswith(".kml")):
        raise HTTPException(status_code=400, detail="File harus .kmz atau .kml")


@app.post("/convert/auto")
async def convert_auto(
    files: list[UploadFile] = File(...),
    include_street: bool = Form(False),
):
    with tempfile.TemporaryDirectory() as td:
        out_zip = os.path.join(td, "output.zip")
        produced_any = False

        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for i, up in enumerate(files, start=1):
                _ensure_kml_kmz(up.filename)

                ext = ".kml" if up.filename.lower().endswith(".kml") else ".kmz"
                src_path = os.path.join(td, f"upload_{i}{ext}")

                with open(src_path, "wb") as f:
                    f.write(await up.read())

                # detect type(s)
                try:
                    info = detect_types(src_path)
                except Exception:
                    continue

                base = os.path.splitext(os.path.basename(up.filename))[0].replace(" ", "_")

                if info.get("homepass"):
                    hp_df = convert_homepass(src_path)

                    if include_street and not hp_df.empty:
                        roads, displays = [], []
                        for _, r in hp_df.iterrows():
                            road, display = await reverse_geocode_road(float(r["lat"]), float(r["lon"]), APP_USER_AGENT)
                            roads.append(road)
                            displays.append(display)
                        hp_df["street"] = roads
                        hp_df["display_name"] = displays

                    hp_csv = os.path.join(td, f"{base}_homepass.csv")
                    hp_df.to_csv(hp_csv, index=False)
                    z.write(hp_csv, arcname=f"{base}_homepass.csv")
                    produced_any = True

                if info.get("pole"):
                    pole_df = convert_pole(src_path)
                    pole_csv = os.path.join(td, f"{base}_pole.csv")
                    pole_df.to_csv(pole_csv, index=False)
                    z.write(pole_csv, arcname=f"{base}_pole.csv")
                    produced_any = True

        if not produced_any:
            raise HTTPException(
                status_code=400,
                detail="Tidak ada data yang terdeteksi. Pastikan file berisi folder HP/HOME/FAT (polygon) atau POLE/FAT."
            )

        return FileResponse(out_zip, media_type="application/zip", filename="kmz_output.zip")
