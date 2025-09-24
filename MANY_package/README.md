MANY - Super Bot de Monetización (Paquete Final)
================================================

Contenido:
- app.py
- requirements.txt
- Dockerfile
- Procfile
- templates/ (HTML)
- data/ (sqlite + key generated at first run)

Instrucciones para desplegar en Render (rápido, recomendado):
1) Crea cuenta en https://render.com y conecta tu GitHub (si deseas).
2) En Render: New -> Web Service -> Deploy from GitHub repo OR Upload ZIP.
3) Si subes ZIP, elige este archivo, Render extraerá y desplegará.
   - Build command: pip install -r requirements.txt
   - Start command: gunicorn app:app -b 0.0.0.0:5000
4) Añade Environment Variables (Render -> Environment):
   BOT_ADMIN_USER=admin
   BOT_ADMIN_PASS=admin123
   AUTO_START=1
   AUTO_INTERVAL_HOURS=48
   DEMO_MODE=1
   SECRET_KEY=una_clave_segura
   OPENAI_API_KEY= (opcional)
5) Una vez desplegado, visita: https://<tu-servicio>/login
   - Usuario: BOT_ADMIN_USER
   - Contraseña: BOT_ADMIN_PASS
6) Ve a /config y pega tus claves de afiliados. Puedes pegarlas desde el panel, no hace falta editar código.
7) En el panel, pulsa "Iniciar Auto" para arrancar el worker si no se inició solo.

Notas de seguridad:
- Las claves guardadas vía panel se cifran con una clave local (fernet) que se genera la primera vez:
  - Si mueves la app a otro servidor, copia también data/fernet.key para poder leer las claves.
- Para producción, cambia BOT_ADMIN_PASS y SECRET_KEY en las Environment Variables.

Soporte:
- Si algo falla pega aquí los logs de Render (Dashboard -> Logs) y te guío.
- # --- Core Web Server ---
flask
gunicorn
fastapi
uvicorn

# --- Utilidades generales ---
requests
httpx
beautifulsoup4
lxml
python-dotenv
pydantic
schedule

# --- IA y NLP ---
openai
transformers
torch
torchvision
sentence-transformers

# --- Automatización y scraping ---
selenium
playwright
scrapy

# --- Manejo de datos ---
pandas
numpy

# --- Bases de datos ---
sqlalchemy
pymongo
psycopg2-binary

# --- APIs y seguridad ---
cryptography
authlib
PyJWT

# --- Email / Mensajería ---
twilio
python-telegram-bot

# --- Dashboard / Estadísticas ---
plotly
matplotlib
dash

# --- Extras para estabilidad ---
tenacity
retrying

