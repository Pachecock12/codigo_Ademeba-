web: gunicorn ademeba_web.wsgi --bind 0.0.0.0:8000 --workers 4 --timeout 120
release: python manage.py migrate --noinput
