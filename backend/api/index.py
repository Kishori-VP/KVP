import os
import sys
import traceback
from pathlib import Path

# Ensure backend root is in sys.path so 'app' imports resolve cleanly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app.main import app
except Exception as e:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="KVP API Vercel Startup Fallback")
    tb = traceback.format_exc()

    @app.api_route("/{path_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
    async def vercel_startup_error(path_path: str):
        return JSONResponse(
            status_code=500,
            content={
                "error": "FastAPI application failed during Vercel cold-start initialization",
                "message": str(e),
                "traceback": tb.splitlines(),
                "sys_path": sys.path,
            },
        )
