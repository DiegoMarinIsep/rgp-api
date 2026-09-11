from fastapi import FastAPI, Response
import requests
from bs4 import BeautifulSoup

app = FastAPI()

###############################################
# 1) ENDPOINTS RGP : LISTING + DOWNLOAD
###############################################

@app.get("/rgp/list")
def list_rgp_files(year: int, doy: int):
    """
    Liste les fichiers RGP disponibles pour une année + day-of-year.
    Exemple : /rgp/list?year=2025&doy=1
    """
    url = f"https://rgpdata.ign.fr/pub/data/{year}/{doy:03d}/"
    html = requests.get(url).text
    soup = BeautifulSoup(html, "html.parser")

    files = [a["href"] for a in soup.find_all("a") if a["href"].endswith(".gz")]
    return {"files": files}


@app.get("/rgp/download")
def download_rgp_file(year: int, doy: int, filename: str):
    """
    Télécharge un fichier RGP directement depuis rgpdata.ign.fr
    Exemple :
    /rgp/download?year=2025&doy=1&filename=AAER00FRA_R_20250010000_01D_30S_MO.rnx.gz
    """
    url = f"https://rgpdata.ign.fr/pub/data/{year}/{doy:03d}/{filename}"

    r = requests.get(url)
    if r.status_code != 200:
        return {"error": "Fichier introuvable sur le serveur RGP"}

    return Response(
        content=r.content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

###############################################
# 2) TES ENDPOINTS EXISTANTS (stations, status, metrics)
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
