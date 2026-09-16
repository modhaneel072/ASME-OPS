# Not read by Render (render.yaml is). Kept for hosts that use a Procfile, and
# as the shape the start command should have anywhere: bind 0.0.0.0 and the PORT
# the host hands out, never a fixed port on localhost.
release: python manage.py upgrade
web: gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120 app:app
worker: python manage.py worker
