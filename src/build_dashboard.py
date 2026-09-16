"""
Genera docs/index.html a partir de la base local con gráficas de las últimas
lecturas. docs/ es la carpeta que luego publicas en GitHub Pages.

Uso:
    python src\\build_dashboard.py
"""

import configparser
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.ini"
DOCS_DIR = ROOT / "docs"


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def load_recent_data(days: int, variables: list[str] | None = None) -> pd.DataFrame:
    conn = get_connection()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    if variables:
        placeholders = ",".join("?" * len(variables))
        query = (
            f"SELECT timestamp, variable, value FROM readings "
            f"WHERE timestamp >= ? AND variable IN ({placeholders}) ORDER BY timestamp"
        )
        params = (since, *variables)
    else:
        query = "SELECT timestamp, variable, value FROM readings WHERE timestamp >= ? ORDER BY timestamp"
        params = (since,)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def build_current_conditions_html(df: pd.DataFrame, variable_order: list[str] | None = None) -> str:
    latest_per_var = df.sort_values("timestamp").groupby("variable").last()
    if variable_order:
        latest_per_var = latest_per_var.reindex([v for v in variable_order if v in latest_per_var.index])
    cards = []
    for variable, row in latest_per_var.iterrows():
        cards.append(
            f"""
            <div class="card">
              <div class="card-label">{variable}</div>
              <div class="card-value">{row['value']:.2f}</div>
            </div>
            """
        )
    return "\n".join(cards)


def build_charts_html(df: pd.DataFrame, variable_order: list[str] | None = None) -> str:
    charts = []
    present = set(df["variable"].unique())
    order = [v for v in variable_order if v in present] if variable_order else sorted(present)
    for variable in order:
        sub = df[df["variable"] == variable]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["value"], mode="lines", name=variable))
        fig.update_layout(
            title=variable,
            margin=dict(l=40, r=20, t=40, b=30),
            height=320,
            template="plotly_white",
        )
        include_js = "cdn" if not charts else False
        charts.append(fig.to_html(full_html=False, include_plotlyjs=include_js, div_id=f"chart-{variable}"))
    return "\n".join(charts)


def main():
    cfg = load_config()
    site_title = cfg.get("dashboard", "site_title", fallback="Estación Meteorológica")
    days = cfg.getint("dashboard", "days_to_show", fallback=7)
    refresh_seconds = cfg.getint("dashboard", "refresh_seconds", fallback=300)
    variables = [v.strip() for v in cfg.get("dashboard", "variables", fallback="").split(",") if v.strip()]

    df = load_recent_data(days, variables or None)
    if df.empty:
        cards_html = "<p>Todavía no hay datos sincronizados.</p>"
        charts_html = ""
        last_update = "sin datos"
    else:
        cards_html = build_current_conditions_html(df, variables or None)
        charts_html = build_charts_html(df, variables or None)
        last_update = df["timestamp"].max().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh_seconds}">
<title>{site_title}</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; margin: 0; padding: 20px; background: #f7f8fa; color: #222; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .updated {{ color: #666; margin-bottom: 20px; font-size: 0.9rem; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }}
  .card {{ background: white; border-radius: 8px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 140px; }}
  .card-label {{ font-size: 0.8rem; color: #666; text-transform: uppercase; }}
  .card-value {{ font-size: 1.6rem; font-weight: 600; }}
  .charts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }}
</style>
</head>
<body>
  <h1>{site_title}</h1>
  <div class="updated">Última actualización: {last_update} &middot; la página se refresca sola cada {refresh_seconds}s</div>
  <div class="cards">
    {cards_html}
  </div>
  <div class="charts">
    {charts_html}
  </div>
</body>
</html>
"""

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard generado en {DOCS_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
