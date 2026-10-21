import os
import sys
import traceback
from pathlib import Path

# Ensure backend root is in sys.path so 'app' imports resolve cleanly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from app.main import app as fastapi_app

    class VercelPathMiddleware:
        def __init__(self, asgi_app):
            self.asgi_app = asgi_app

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope.get("headers", []))
                matched = headers.get(b"x-matched-path", b"").decode("utf-8")
                path = scope.get("path", "")

                if matched and not matched.endswith(".py"):
                    scope["path"] = matched
                elif path.startswith("/api/index.py"):
                    sub = path[len("/api/index.py"):]
                    scope["path"] = sub if sub.startswith("/") else ("/" + sub)
                elif path.startswith("/api/index"):
                    sub = path[len("/api/index"):]
                    scope["path"] = sub if sub.startswith("/") else ("/" + sub)

                if not scope.get("path"):
                    scope["path"] = "/"

            await self.asgi_app(scope, receive, send)

    app = VercelPathMiddleware(fastapi_app)
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
