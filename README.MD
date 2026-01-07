
# KMZ2CSV RuangNalar

Web converter KMZ → CSV:
- Homepass points + FAT boundary polygon → homepass.csv
- Pole points + FAT point → pole.csv (nearest FAT)
- Optional: reverse geocode street via OSM Nominatim (cached)

## Run (local / Codespaces)
```bash
docker compose up --build
