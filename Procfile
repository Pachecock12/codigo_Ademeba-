web: python manage.py migrate --noinput && python manage.py collectstatic --noinput --clear && gunicorn ademeba_web.wsgi --bind 0.0.0.0:8000 --workers 4 --timeout 120
