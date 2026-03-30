from __future__ import annotations

import os

import uvicorn


def run_api() -> None:
    host = os.getenv("ADP_HOST", "0.0.0.0")
    port = int(os.getenv("ADP_PORT", "8000"))
    uvicorn.run("app.api:create_app", factory=True, host=host, port=port)


if __name__ == "__main__":
    run_api()
