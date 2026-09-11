from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from datetime import datetime
import xml.etree.ElementTree as ET

SQLALCHEMY_DATABASE_URL = "sqlite:///./rgp.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Station(Base):
    __tablename__ = "stations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    environment = Column(String, nullable=True)
    receiver = Column(String, nullable=True)
    antenna = Column(String, nullable=True)
    metrics = relationship("QCMetrics", back_populates="station")

class QCMetrics(Base):
    __tablename__ = "qc_metrics"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"))
    datetime = Column(DateTime)
    epochs_ratio = Column(Float)
    obs_ratio_mask3 = Column(Float)
    obs_ratio_mask10 = Column(Float)
    latency = Column(Float)
    error = Column(Integer)
    interval = Column(Integer)
    station = relationship("Station", back_populates="metrics")

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def parse_qc_xml(path: str):
    tree = ET.parse(path)
    root = tree.getroot()
    station = root.find(".//station").attrib["name"]
    fileinfo = root.find(".//file")
    epochs_ratio = float(root.find(".//epochs_ratio").text)
    obs_ratio_mask3 = float(root.find(".//obs_ratio").text)
    obs_ratio_mask10 = float(root.find(".//mask_elevation").text.split()[0])
    latency = float(root.find(".//latency").text)
    error = int(fileinfo.attrib["error"])
    interval = int(fileinfo.attrib["interval"])
    dt = datetime.strptime(root.attrib["date"], "%Y-%m-%d")
    return {
        "station": station,
        "datetime": dt,
        "epochs_ratio": epochs_ratio,
        "obs_ratio_mask3": obs_ratio_mask3,
        "obs_ratio_mask10": obs_ratio_mask10,
        "latency": latency,
        "error": error,
        "interval": interval,
    }

def ingest_qc_file(path: str):
    db: Session = SessionLocal()
    data = parse_qc_xml(path)
    station = db.query(Station).filter(Station.name == data["station"]).first()
    if not station:
        station = Station(name=data["station"])
        db.add(station)
        db.commit()
        db.refresh(station)
    metric = QCMetrics(
        station_id=station.id,
        datetime=data["datetime"],
        epochs_ratio=data["epochs_ratio"],
        obs_ratio_mask3=data["obs_ratio_mask3"],
        obs_ratio_mask10=data["obs_ratio_mask10"],
        latency=data["latency"],
        error=data["error"],
        interval=data["interval"],
    )
    db.add(metric)
    db.commit()
    db.close()

app = FastAPI(title="RGP QC API")

def compute_status(m: QCMetrics):
    if m.error != 0 or m.epochs_ratio < 90:
        return "Indisponible"
    if m.epochs_ratio < 95 or m.latency > 5:
        return "Dégradé"
    return "Nominal"

@app.get("/stations")
def list_stations(db: Session = Depends(get_db)):
    stations = db.query(Station).all()
    return [{"name": s.name, "lat": s.lat, "lon": s.lon, "environment": s.environment} for s in stations]

@app.get("/stations/{name}/status")
def station_status(name: str, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.name == name).first()
    if not station:
        return {"error": "station not found"}
    last_metric = (
        db.query(QCMetrics)
        .filter(QCMetrics.station_id == station.id)
        .order_by(QCMetrics.datetime.desc())
        .first()
    )
    if not last_metric:
        return {"status": "unknown"}
    return {
        "station": station.name,
        "status": compute_status(last_metric),
        "datetime": last_metric.datetime,
        "epochs_ratio": last_metric.epochs_ratio,
        "obs_ratio_mask3": last_metric.obs_ratio_mask3,
        "obs_ratio_mask10": last_metric.obs_ratio_mask10,
        "latency": last_metric.latency,
        "error": last_metric.error,
    }

@app.get("/stations/{name}/metrics")
def station_metrics(name: str, start: datetime, end: datetime, db: Session = Depends(get_db)):
    station = db.query(Station).filter(Station.name == name).first()
    if not station:
        return {"error": "station not found"}
    metrics = (
        db.query(QCMetrics)
        .filter(QCMetrics.station_id == station.id)
        .filter(QCMetrics.datetime >= start)
        .filter(QCMetrics.datetime <= end)
        .order_by(QCMetrics.datetime)
        .all()
    )
    return [
        {
            "datetime": m.datetime,
            "epochs_ratio": m.epochs_ratio,
            "obs_ratio_mask3": m.obs_ratio_mask3,
            "obs_ratio_mask10": m.obs_ratio_mask10,
            "latency": m.latency,
            "error": m.error,
        }
        for m in metrics
    ]
