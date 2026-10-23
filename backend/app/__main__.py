"""Start the API server: `python -m app`.

Binds to 0.0.0.0 and reads the port from $PORT (set by Render), falling back to 8000,
so the same command works on Render, PowerShell and bash.
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT") or 8000),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
