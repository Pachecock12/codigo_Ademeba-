#!/bin/bash
exec gunicorn ademeba_web.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 4 --timeout 120
