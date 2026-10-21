import uvicorn

from vendoriq.main import app


def main() -> None:
    uvicorn.run("vendoriq.main:app", host="0.0.0.0", port=8000, reload=True)


__all__ = ["app", "main"]
