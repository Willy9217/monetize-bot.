Monetize Bot Ready - Paquete v2
================================
Paquete mejorado y revisado para principiantes.

Archivos incluidos:
- monetize_bot_ready.py
- requirements.txt
- Dockerfile
- docker-compose.yml
- .env.example
- video_script_es.txt
- video_prompt.txt
- DEPLOY_HINTS.txt

Instrucciones (resumen rápido):
1) Edita .env con tus claves (OPENAI_API_KEY, SECRET_KEY, AFFIL_DOMAINS).
2) Subir a Render o a un VPS con Docker.
3) Ejecutar: docker-compose up -d --build
4) Configurar nginx/certbot si usas dominio propio.

Recomendación para principiantes: desplegar en Render (free tier) conectando este repositorio a Render y configurando las environment variables.
