"""
Wind speed / direction para LaBana no vienen de la estacion meteo de campo
(AMAYA MET1 / Biomet__CR1000X), sino del propio equipo de flujo SmartFlux:
cada periodo de 30 min genera un `full_output*.csv` (EddyPro) con columnas
`wind_speed`/`wind_dir`, bien ya exportado suelto en una carpeta `eddypro/`,
bien empaquetado dentro del `.ghg` de ese periodo cuando no llego a
exportarse (ver Manual del pipeline EddyCovariance, seccion 7.1).

Fuente LOCAL (no por FTP): esta maquina ya tiene una copia completa y al dia
de esos ficheros en el proyecto EddyCovariance (`wind_source` en config.ini).
Si en el futuro este dashboard se ejecuta en un PC sin acceso a esa carpeta,
esta sincronizacion de viento tendria que rehacerse contra el FTP en su
lugar (ver README).

Uso:
    python src\\sync_wind.py
"""

import configparser
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection, upsert_readings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.ini"

TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{6}")
WIND_COLS = ["date", "time", "wind_speed", "wind_dir"]


def load_config() -> configparser.ConfigParser:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"No existe {CONFIG_PATH}. Copia config.example.ini a config.ini.")
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def full_output_to_long(df: pd.DataFrame) -> pd.DataFrame:
    df = df[WIND_COLS].copy()
    df["timestamp"] = pd.to_datetime(df["date"] + " " + df["time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    long_df = df.melt(
        id_vars="timestamp", value_vars=["wind_speed", "wind_dir"], var_name="variable", value_name="value"
    )
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    return long_df.dropna(subset=["value"])


def parse_loose_full_output(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=[0, 2], usecols=lambda c: c in WIND_COLS, low_memory=False)
    return full_output_to_long(df)


def parse_ghg_full_output(path: Path) -> pd.DataFrame | None:
    with zipfile.ZipFile(path) as z:
        candidates = [
            n for n in z.namelist() if "full_output" in n and (n.endswith(".csv") or n.endswith(".csv.tmp"))
        ]
        if not candidates:
            return None
        with z.open(candidates[0]) as f:
            df = pd.read_csv(f, skiprows=[0, 2], usecols=lambda c: c in WIND_COLS, low_memory=False)
    return full_output_to_long(df)


def main():
    cfg = load_config()
    eddypro_dir = Path(cfg.get("wind_source", "eddypro_dir"))
    ghg_dir = Path(cfg.get("wind_source", "ghg_dir"))

    conn = get_connection()
    total_new = 0
    errors = []

    loose_files = sorted(eddypro_dir.glob("*full_output*.csv"))
    loose_files = [p for p in loose_files if not p.name.endswith(".tmp")]
    print(f"Ficheros full_output sueltos en {eddypro_dir}: {len(loose_files)}")
    max_loose_ts = ""
    for i, path in enumerate(loose_files):
        m = TS_RE.search(path.name)
        if m:
            max_loose_ts = max(max_loose_ts, m.group())
        try:
            total_new += upsert_readings(conn, parse_loose_full_output(path))
        except Exception as e:
            errors.append((path.name, str(e)))
        if (i + 1) % 2000 == 0:
            print(f"...sueltos {i+1}/{len(loose_files)}")

    ghg_files = sorted(ghg_dir.glob("*.ghg"))
    new_ghg = [p for p in ghg_files if TS_RE.search(p.name) and TS_RE.search(p.name).group() > max_loose_ts]
    print(f"Ficheros .ghg posteriores al ultimo full_output suelto ({max_loose_ts}): {len(new_ghg)}")
    for i, path in enumerate(new_ghg):
        try:
            long_df = parse_ghg_full_output(path)
            if long_df is not None:
                total_new += upsert_readings(conn, long_df)
        except Exception as e:
            errors.append((path.name, str(e)))
        if (i + 1) % 1000 == 0:
            print(f"...ghg {i+1}/{len(new_ghg)}")

    conn.close()
    print(f"Listo. {total_new} lecturas de viento (wind_speed/wind_dir) guardadas.")
    if errors:
        print(f"{len(errors)} ficheros con error. Primeros 10:")
        for name, err in errors[:10]:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()
