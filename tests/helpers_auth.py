"""Test helper: register + log in a synthetic user and attach the bearer token to a TestClient."""
import itertools
import os
import tempfile
import uuid

_counter = itertools.count(1)
PASSWORD = "Synthetic-Passw0rd-" + "xyz"


_DB_PATH = None


def use_temp_database(prefix="rdtest_"):
    """Point DATABASE_URL at ONE fresh SQLite file per test process (idempotent) BEFORE the app is imported / started."""
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = os.path.join(tempfile.mkdtemp(prefix=prefix), "app.db")
    os.environ["DATABASE_URL"] = "sqlite:///" + _DB_PATH.replace("\\", "/")
    os.environ["AUTO_MIGRATE"] = "1"
    return _DB_PATH


def register_and_login(client, email=None, password=PASSWORD):
    email = email or f"user{next(_counter)}-{uuid.uuid4().hex[:6]}@example.test"
    r = client.post("/api/auth/register", json={"email": email, "password": password, "display_name": "Synthetic User"})
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    return {"email": email, "token": body["access_token"], "headers": {"Authorization": "Bearer " + body["access_token"]}, "user": body["user"]}


def authed_client(client, **kw):
    """Log a fresh user in and make the client send the token by default. Returns the user dict."""
    u = register_and_login(client, **kw)
    client.headers.update(u["headers"])
    return u
