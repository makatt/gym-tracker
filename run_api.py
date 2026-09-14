"""Точка входа API: python run_api.py  (или uvicorn app.api:app --port 8000)"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.api:app", host="0.0.0.0", port=8000)
