from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vendoriq.api.routes import api_router
from vendoriq.api.routes.health import health_check
from vendoriq.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API v1 routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# Compatibility route for legacy /api/health
app.add_api_route("/api/health", health_check, methods=["GET"], include_in_schema=False)


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs": "/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }


@app.get("/health", tags=["Root"])
async def root_health():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
    }
