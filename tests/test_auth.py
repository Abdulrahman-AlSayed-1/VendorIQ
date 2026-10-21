import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vendoriq.models.user import User, UserRole


@pytest.mark.asyncio
async def test_register_customer_success(
    async_client: AsyncClient, db_session: AsyncSession
):
    payload = {
        "name": "Jane Doe",
        "email": "JANE.DOE@example.com ",
        "password": "SecurePassword123!",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Jane Doe"
    assert data["email"] == "jane.doe@example.com"  # Normalized
    assert data["role"] == "customer"
    assert "password" not in data
    assert "password_hash" not in data

    # Verify directly in database
    stmt = select(User).where(User.email == "jane.doe@example.com")
    res = await db_session.execute(stmt)
    user = res.scalar_one_or_none()
    assert user is not None
    assert user.role == UserRole.CUSTOMER
    assert user.password_hash != "SecurePassword123!"


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(
    async_client: AsyncClient, regular_user: User
):
    payload = {
        "name": "Duplicate User",
        "email": regular_user.email,
        "password": "AnotherPassword123!",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    data = response.json()
    assert "already exists" in data["detail"].lower()


@pytest.mark.asyncio
async def test_login_success(async_client: AsyncClient, regular_user: User):
    payload = {
        "email": regular_user.email,
        "password": "Customer123!",
    }
    response = await async_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_invalid_password(async_client: AsyncClient, regular_user: User):
    payload = {
        "email": regular_user.email,
        "password": "WrongPassword999!",
    }
    response = await async_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "invalid email or password" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_current_user_me(async_client: AsyncClient, regular_user: User):
    # First login to get token
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": regular_user.email, "password": "Customer123!"},
    )
    token = login_resp.json()["access_token"]

    # Access /api/v1/auth/me
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["email"] == regular_user.email
    assert data["role"] == "customer"


@pytest.mark.asyncio
async def test_auth_me_unauthorized(async_client: AsyncClient):
    # No header
    resp1 = await async_client.get("/api/v1/auth/me")
    assert resp1.status_code == 401

    # Invalid token
    resp2 = await async_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token.value"}
    )
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_admin_access_control(
    async_client: AsyncClient, regular_user: User, admin_user: User
):
    from vendoriq.api.deps import CurrentAdminDep
    from vendoriq.main import app

    # Temporarily register an admin test route on app
    @app.get("/api/v1/admin/secret-test", include_in_schema=False)
    async def admin_endpoint(admin: CurrentAdminDep):
        return {"admin": admin.email}

    # Customer attempts to access
    cust_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": regular_user.email, "password": "Customer123!"},
    )
    cust_token = cust_login.json()["access_token"]
    cust_resp = await async_client.get(
        "/api/v1/admin/secret-test",
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert cust_resp.status_code == 403
    assert "administrative privileges required" in cust_resp.json()["detail"].lower()

    # Admin accesses
    admin_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "AdminSecure123!"},
    )
    admin_token = admin_login.json()["access_token"]
    admin_resp = await async_client.get(
        "/api/v1/admin/secret-test",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json()["admin"] == admin_user.email
