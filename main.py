import os
from datetime import datetime
from fastapi import FastAPI, Response
import requests
from bs4 import BeautifulSoup
import psycopg2

# Module externe contenant le parsing avancé
from rinex_parser import parse_rinex_file

app = FastAPI()

###############################################
# 0) ROUTE ROOT POUR RENDER (OBLIGATOIRE)
###############################################

@app.get("/")
def root():
    return {"status": "ok", "message": "RGP API is running"}

###############################################
# 1) CONNEXION POSTGRESQL (Render)
###############################################

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT", "5432")
    )

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rinex_files (
            id SERIAL PRIMARY KEY,
            station TEXT,
            year INTEGER,
            doy INTEGER,
            filename TEXT,
            downloaded_at TIMESTAMP,
            size INTEGER,
            path TEXT
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rinex_metrics (
            id SERIAL PRIMARY KEY,
            station TEXT,
            year INTEGER,
            doy INTEGER,
            filename TEXT,
            satellites INTEGER,
            observations INTEGER,
            cycle_slips INTEGER,
            snr_avg DOUBLE PRECISION
        );
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

###############################################
# 2) LISTE TOUS LES FICHIERS RGP
###############################################

@app.get("/rgp/list")
def list_rgp_files(year: int, doy: int):
    url = f"https://rgpdata.ign.fr/pub/data/{year}/{doy:03d}/"
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    files = [a["href"] for a in soup.find_all("a") if "." in a["href"]]
    return {"files": files}

###############################################
# 3) TÉLÉCHARGER UN FICHIER RGP + STOCKER EN DB
###############################################

def save_file_to_disk(year, doy, filename, content):
    os.makedirs("data", exist_ok=True)
    local_path = f"data/{year}_{doy}_{filename}"
    with open(local_path, "wb") as f:
        f.write(content)
    return local_path

@app.get("/rgp/download")
def download_rgp_file(year: int, doy: int, filename: str):
    url = f"https://rgpdata.ign.fr/pub/data/{year}/{doy:03d}/{filename}"
    r = requests.get(url)

    if r.status_code != 200:
        return {"error": "Fichier introuvable sur le serveur RGP"}

    local_path = save_file_to_disk(year, doy, filename, r.content)

    conn = get_db_conn()
    cur = conn.cursor()

    station = filename[:4]
    size = len(r.content)

    cur.execute("""
        INSERT INTO rinex_files (station, year, doy, filename, downloaded_at, size, path)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (station, year, doy, filename, datetime.utcnow(), size, local_path))

    conn.commit()
    cur.close()
    conn.close()

    return Response(
        content=r.content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

###############################################
# 4) MÉTRIQUES GNSS VIA PARSING RINEX AVANCÉ
###############################################

@app.get("/rgp/metrics")
def rgp_metrics(year: int, doy: int, filename: str):
    local_path = f"data/{year}_{doy}_{filename}"

    if not os.path.exists(local_path):
        return {"error": "Fichier non téléchargé. Utilise /rgp/download d'abord."}

    parsed = parse_rinex_file(local_path)
    metrics = parsed["metrics"]
    station = filename[:4]

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO rinex_metrics (station, year, doy, filename, satellites, observations, cycle_slips, snr_avg)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        station,
        year,
        doy,
        filename,
        metrics["satellites"],
        metrics["observations"],
        metrics["cycle_slips"],
        metrics["snr_avg"]
    ))

    conn.commit()
    cur.close()
    conn.close()

    return {
        "station": station,
        "year": year,
        "doy": doy,
        "filename": filename,
        "header": parsed["header"],
        "satellites": metrics["satellites"],
        "observations": metrics["observations"],
        "cycle_slips": metrics["cycle_slips"],
        "snr_avg": metrics["snr_avg"],
        "epochs_count": len(parsed["epochs"])
    }

###############################################
# 5) ENDPOINT CRON AUTOMATIQUE
###############################################

@app.post("/rgp/cron/daily")
def rgp_cron_daily(year: int, doy: int):
    files = list_rgp_files(year, doy)["files"]
    results = []

    for filename in files:
        download_rgp_file(year, doy, filename)
        try:
            metrics = rgp_metrics(year, doy, filename)
            results.append(metrics)
        except Exception as e:
            results.append({"filename": filename, "error": str(e)})

    return {
        "year": year,
        "doy": doy,
        "processed": results
    }

###############################################
# 6) ENDPOINTS STATIONS
###############################################

stations_data = {
    "AAER": {"status": "OK", "metrics": {"temp": 22, "battery": 95}},
    "BBER": {"status": "DOWN", "metrics": {"temp": None, "battery": None}},
}

@app.get("/stations")
def get_stations():
    return list(stations_data.keys())

@app.get("/stations/{station_id}/status")
def get_station_status(station_id: str):
    if station_id not in stations_data:
        return {"error": "Station inconnue"}
    return {"station": station_id, "status": stations_data[station_id]["status"]}

@app.get("/stations/{station_id}/metrics")
def get_station_metrics(station_id: str, start: str = None, end: str = None):
    if station_id not in stations_data:
        return {"error": "Station inconnue"}
    return {
        "station": station_id,
        "metrics": stations_data[station_id]["metrics"],
        "start": start,
        "end": end
    }
