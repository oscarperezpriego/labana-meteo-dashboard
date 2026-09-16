# Meteo Dashboard

Publica en una web pública (GitHub Pages) los datos de la estación meteorológica
Campbell Scientific, sincronizándolos automáticamente cada 30 min desde el
servidor al que hoy te conectas con WinSCP.

Cómo funciona: `src/sync_campbell.py` descarga los `.dat` nuevos y los guarda en
`data/meteo.db` (SQLite). `src/build_dashboard.py` genera `docs/index.html` con
gráficas (Plotly) de cada variable y una página que se auto-refresca sola en el
navegador. `run_all.bat` encadena ambos pasos y publica `docs/` con `git push`.

## 1. Preparar el entorno (una vez)

En el PC Windows de la oficina:

```bash
cd meteo_dashboard
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Copia `config.example.ini` a `config.ini` y rellena host/usuario/contraseña del
servidor (los mismos datos que usas en WinSCP) y la ruta remota donde el logger
deja los archivos. `config.ini` está en `.gitignore`: nunca se sube a GitHub.

## 2. Crear el repositorio y GitHub Pages (una vez)

1. Crea un repo en GitHub (puede ser público, ya que los datos meteorológicos no
   son sensibles).
2. `git init`, `git remote add origin <url>`, primer commit y `git push`.
3. En Settings → Pages del repo, selecciona "Deploy from a branch" → rama
   `main`, carpeta `/docs`. GitHub te dará la URL pública del dashboard.
4. Para que `git push` funcione sin pedir contraseña cada vez desde la tarea
   programada, usa un [Personal Access Token](https://github.com/settings/tokens)
   guardado con el gestor de credenciales de Windows (`git config --global
   credential.helper manager`), o una clave SSH.

## 3. Probar a mano

```bash
python src\sync_campbell.py
python src\build_dashboard.py
```

Abre `docs/index.html` en el navegador para comprobar que las gráficas
aparecen correctamente antes de programar la tarea.

## 4. Programar la tarea (Windows Task Scheduler)

Crea una tarea nueva:
- Desencadenador: repetir cada 30 minutos, indefinidamente.
- Acción: ejecutar `run_all.bat` (ruta completa), con "Iniciar en" apuntando a
  la carpeta del proyecto.
- Marca "Ejecutar tanto si el usuario inició sesión como si no", ya que es un
  PC que se queda encendido sin nadie delante.

Revisa `data\sync.log` si algo falla.

## Notas sobre el formato de datos

`parse_toa5` en `src/sync_campbell.py` asume el formato TOA5 estándar de
Campbell (4 líneas de cabecera: metadatos, nombres, unidades, agregación). Si
tu programa del datalogger exporta en otro formato (p. ej. array-based/TOACI1),
ajusta esa función — puedes pegarme una muestra de un `.dat` real y lo adapto.

## Notas de seguridad

- `config.ini` contiene la contraseña del servidor en texto plano; queda solo
  en el PC de oficina y no se sube a git. Si el servidor soporta clave SSH en
  vez de contraseña, es preferible — se puede adaptar `sync_campbell.py`.
- El dashboard publicado es público: no incluyas ahí nada más que las series
  meteorológicas.
