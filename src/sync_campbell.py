"""
Descarga los archivos de datos del logger Campbell desde el servidor remoto
(el mismo al que te conectas ahora con WinSCP) y los guarda en la base local.

Pensado para lanzarse cada 30 min desde el Programador de tareas de Windows:
    python src\\sync_campbell.py
"""

import configparser
import fnmatch
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection, upsert_readings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.ini"
RAW_DIR = ROOT / "data" / "raw"


def load_config() -> configparser.ConfigParser:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"No existe {CONFIG_PATH}. Copia config.example.ini a config.ini y rellena tus datos."
        )
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def list_remote_files(cfg) -> list[str]:
    explicit = [f.strip() for f in cfg.get("server", "files", fallback="").split(",") if f.strip()]
    if explicit:
        return explicit

    pattern = cfg.get("server", "file_pattern", fallback="*.dat")
    protocol = cfg.get("server", "protocol", fallback="sftp").lower()
    remote_path = cfg.get("server", "remote_path")

    if protocol == "sftp":
        import paramiko

        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                cfg.get("server", "host"),
                port=cfg.getint("server", "port", fallback=22),
                username=cfg.get("server", "username"),
                password=cfg.get("server", "password"),
            )
            with ssh.open_sftp() as sftp:
                names = sftp.listdir(remote_path)
    else:
        from ftplib import FTP

        with FTP() as ftp:
            ftp.connect(cfg.get("server", "host"), cfg.getint("server", "port", fallback=21))
            ftp.login(cfg.get("server", "username"), cfg.get("server", "password"))
            ftp.cwd(remote_path)
            names = ftp.nlst()

    return [n for n in names if fnmatch.fnmatch(n, pattern)]


def download_files(cfg, filenames: list[str]) -> list[Path]:
    """Descarga solo los ficheros que aun no existen en local -- la carpeta
    remota acumula el historico completo (miles de ficheros), y volver a
    bajarlos todos en cada pasada (cada 30 min) tardaria mas que el propio
    intervalo de la tarea programada."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    protocol = cfg.get("server", "protocol", fallback="sftp").lower()
    remote_path = cfg.get("server", "remote_path")

    pending = [name for name in filenames if not (RAW_DIR / name).exists()]
    skipped = len(filenames) - len(pending)
    if skipped:
        print(f"{skipped} ficheros ya presentes en local, se omiten.")
    local_paths = []

    if protocol == "sftp":
        import paramiko

        with paramiko.SSHClient() as ssh:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                cfg.get("server", "host"),
                port=cfg.getint("server", "port", fallback=22),
                username=cfg.get("server", "username"),
                password=cfg.get("server", "password"),
            )
            with ssh.open_sftp() as sftp:
                for name in pending:
                    local_path = RAW_DIR / name
                    sftp.get(f"{remote_path.rstrip('/')}/{name}", str(local_path))
                    local_paths.append(local_path)
    else:
        from ftplib import FTP

        with FTP() as ftp:
            ftp.connect(cfg.get("server", "host"), cfg.getint("server", "port", fallback=21))
            ftp.login(cfg.get("server", "username"), cfg.get("server", "password"))
            ftp.cwd(remote_path)
            for name in pending:
                local_path = RAW_DIR / name
                with open(local_path, "wb") as fh:
                    ftp.retrbinary(f"RETR {name}", fh.write)
                local_paths.append(local_path)

    return local_paths


def parse_toa5(path: Path) -> pd.DataFrame:
    """
    Formato TOA5 estándar de Campbell Scientific:
      línea 1: metadatos de la estación
      línea 2: nombres de columna   <- cabecera real
      línea 3: unidades
      línea 4: tipo de agregación
      línea 5+: datos
    Si tu archivo tiene otro formato (p.ej. TOACI1, array-based), ajusta skiprows aquí.
    """
    df = pd.read_csv(path, skiprows=[0, 2, 3], na_values=["NAN"], low_memory=False)
    if "TIMESTAMP" not in df.columns:
        raise ValueError(f"{path.name}: no se encontró columna TIMESTAMP; ¿formato distinto a TOA5?")

    df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"])
    value_cols = [c for c in df.columns if c not in ("TIMESTAMP", "RECORD")]

    long_df = df.melt(id_vars="TIMESTAMP", value_vars=value_cols, var_name="variable", value_name="value")
    long_df = long_df.rename(columns={"TIMESTAMP": "timestamp"})
    long_df["timestamp"] = long_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    return long_df.dropna(subset=["value"])


def main():
    cfg = load_config()
    print(f"[{datetime.now(timezone.utc).isoformat()}] Buscando archivos remotos...")
    filenames = list_remote_files(cfg)
    if not filenames:
        print("No se encontraron archivos que sincronizar.")
        return

    local_paths = download_files(cfg, filenames)
    print(f"Descargados {len(local_paths)} ficheros nuevos.")

    conn = get_connection()
    total_new = 0
    for path in local_paths:
        long_df = parse_toa5(path)
        total_new += upsert_readings(conn, long_df)
    conn.close()

    print(f"Listo. {total_new} lecturas nuevas guardadas en la base local.")


if __name__ == "__main__":
    main()
