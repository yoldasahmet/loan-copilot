from fastapi.testclient import TestClient

from tests.conftest import PASSWORD


def test_setup_creates_first_admin_once(client: TestClient) -> None:
    assert client.get("/api/auth/setup").json() == {"needed": True}
    body = {"name": "First Admin", "email": "Admin@Example.com", "password": PASSWORD}
    response = client.post("/api/auth/setup", json=body)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["email"] == "admin@example.com"
    assert client.get("/api/auth/me").json()["name"] == "First Admin"

    assert client.get("/api/auth/setup").json() == {"needed": False}
    again = {"name": "Second", "email": "second@example.com", "password": PASSWORD}
    assert client.post("/api/auth/setup", json=again).status_code == 404


def test_login_logout_and_session_cookie(client: TestClient, login) -> None:
    advisor = login("advisor", email="adv@example.com")
    cookie = advisor.cookies.get("lc_session")
    assert cookie
    assert advisor.get("/api/auth/me").json()["email"] == "adv@example.com"

    bad = client.post("/api/auth/login", json={"email": "adv@example.com", "password": "nope"})
    assert bad.status_code == 401

    assert advisor.post("/api/auth/logout").status_code == 204
    assert advisor.get("/api/auth/me").status_code == 401


def test_session_cookie_flags(client: TestClient, login) -> None:
    login("advisor", email="flags@example.com")
    response = client.post("/api/auth/login",
                           json={"email": "flags@example.com", "password": PASSWORD})  # fmt: skip
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "max-age=28800" in header
    assert "secure" not in header  # localhost


def test_tampered_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set("lc_session", "forged.value.here")
    assert client.get("/api/auth/me").status_code == 401


def test_admin_endpoints_need_admin(login) -> None:
    advisor = login("advisor")
    assert advisor.get("/api/admin/users").status_code == 403
    admin = login("admin")
    created = admin.post("/api/admin/users", json={"name": "New Advisor",
                         "email": "new@example.com", "password": PASSWORD})  # fmt: skip
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert admin.patch(f"/api/admin/users/{user_id}", json={"role": "admin"}).json()["role"] == (
        "admin"
    )
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/admin/users/{me['id']}", json={"role": "advisor"}).status_code == 422
