import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["project"] == "VendorIQ API"
    assert data["database"] == "connected"

    # Compatibility route
    compat_res = await async_client.get("/api/health")
    assert compat_res.status_code == 200
    compat_data = compat_res.json()
    assert compat_data["status"] == "healthy"
    assert compat_data["database"] == "connected"


@pytest.mark.asyncio
async def test_health_check_degraded(async_client: AsyncClient, monkeypatch):
    from sqlalchemy.exc import OperationalError

    async def mock_execute(*args, **kwargs):
        raise OperationalError("connection failure", params=None, orig=Exception())

    monkeypatch.setattr("sqlalchemy.ext.asyncio.AsyncSession.execute", mock_execute)

    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "unavailable"


@pytest.mark.asyncio
async def test_root(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "docs" in data
