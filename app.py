"""
Main Application Entrypoint for Cloud Deployment (Render, Heroku, Railway, etc.)
Imports and serves the SKIPP'D Solar Forecasting Studio Flask application.
"""

import os
from web_server import app

# Expose app for WSGI servers (gunicorn, uwsgi)
application = app

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=False)
