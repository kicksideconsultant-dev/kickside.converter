import os
import tempfile
import zipfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from kmz_parser import convert_homepass_kmz, convert_pole_kmz
from geocode import reverse_geocode_road

APP_USER_AGENT = os.getenv(
    "APP_USER_AGENT",
    "KMZ2CSV RuangNalar (contact: admin@ruangnalar.online)"
)

app = FastAPI(title="KMZ to CSV Converter")

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

def _ensure_kmz(filename: str):
    if not filename.lower().endswith(".kmz"):
        raise HTTPException(status_code=400, detail="File harus .kmz")

@app.post("/convert/all")
async def convert_all(
    kmz_homepass: UploadFile = File(...),
    kmz_pole: UploadFile = File(None),
    include_street: bool = Form(False),
):
    _ensure_kmz(kmz_homepass.filename)
    if kmz_pole is not None:
        _ensure_kmz(kmz_pole.filename)

    with tempfile.TemporaryDirectory() as td:
        out_zip = os.path.join(td, "output.zip")

        hp_path = os.path.join(td, "homepass.kmz")
        with open(hp_path, "wb") as f:
            f.write(await kmz_homepass.read())

        try:
            hp_df = convert_homepass_kmz(hp_path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Gagal parse KMZ homepass: {e}")

        if include_street and not hp_df.empty:
            roads, displays = [], []
            for _, r in hp_df.iterrows():
                road, display = await reverse_geocode_road(float(r["lat"]), float(r["lon"]), APP_USER_AGENT)
                roads.append(road)
                displays.append(display)
            hp_df["street"] = roads
            hp_df["display_name"] = displays

        pole_df = None
        if kmz_pole is not None:
            pole_path = os.path.join(td, "pole.kmz")
            with open(pole_path, "wb") as f:
                f.write(await kmz_pole.read())
            try:
                pole_df = convert_pole_kmz(pole_path)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Gagal parse KMZ pole: {e}")

        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            hp_csv = os.path.join(td, "homepass.csv")
            hp_df.to_csv(hp_csv, index=False)
            z.write(hp_csv, arcname="homepass.csv")

            if pole_df is not None:
                pole_csv = os.path.join(td, "pole.csv")
                pole_df.to_csv(pole_csv, index=False)
                z.write(pole_csv, arcname="pole.csv")

        return FileResponse(out_zip, media_type="application/zip", filename="kmz_output.zip")
