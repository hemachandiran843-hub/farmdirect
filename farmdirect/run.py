"""FarmDirect — run entry point.

Usage:
    python run.py            # development server at http://localhost:5000
    PORT=8080 python run.py  # custom port
"""
import os

from app_factory import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
