# auth tests
from datetime import date

import jwt
import pytest
from fastapi import HTTPException

from app import auth
from app.db import connect
from tests.conftest import sign_in

EMAIL = "Traveller@Example.com "
NEW = {"email": EMAIL, "name": "  Vansh   Rana ", "birth_date": "2002-04-22", "password": "goa2026trip"}


def signup(client, **kw):
    res = client.post("/auth/signup", json={**NEW, **kw})
    client.cookies.clear()
    return res


def test_sign_up_and_sign_in(client):
    res = signup(client)
    assert res.status_code == 201
    user = res.json()["user"]
    assert user["name"] == "Vansh Rana" and user["email"] == "traveller@example.com" and user["role"] == "user"
    assert 10000 <= user["id"] <= 99999 and "password" not in user
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {res.json()['token']}"}).json()
    assert me["id"] == user["id"] and me["birth_date"] == "2002-04-22"
    login = client.post("/auth/login", json={"email": "TRAVELLER@example.com", "password": "goa2026trip"})
    assert login.status_code == 200 and login.json()["user"]["last_login"]


def test_password_is_stored_hashed(client):
    signup(client)
    with connect() as con:
        stored = con.execute("select password from users").fetchone()[0]
    assert "goa2026trip" not in stored and stored.startswith("pbkdf2_sha256$")
    assert auth.password_matches("goa2026trip", stored) and not auth.password_matches("nope", stored)
    assert not auth.password_matches("x", "garbage")


def test_duplicate_email_rejected(client):
    signup(client)
    assert signup(client).status_code == 409


@pytest.mark.parametrize(
    "patch",
    [
        {"email": "not-an-email"},
        {"name": "   "},
        {"password": "short1"},
        {"password": "onlyletters"},
        {"password": "12345678"},
        {"birth_date": "2099-01-01"},
        {"birth_date": "1880-01-01"},
        {"birth_date": str(date.today().replace(year=date.today().year - 10))},
    ],
)
def test_bad_signups_rejected(client, patch):
    assert signup(client, **patch).status_code == 422


def test_wrong_password_and_lockout(client):
    signup(client)
    for i in range(auth.MAX_FAILS - 1):
        res = client.post("/auth/login", json={"email": EMAIL, "password": "wrong1234"})
        assert res.status_code == 401 and res.json()["detail"].startswith("wrong email or password")
        if i == auth.MAX_FAILS - 2:
            assert "1 try left" in res.json()["detail"]
    client.post("/auth/login", json={"email": EMAIL, "password": "wrong1234"})
    locked = client.post("/auth/login", json={"email": EMAIL, "password": "goa2026trip"})
    assert locked.status_code == 429 and "15 minutes" in locked.json()["detail"]


def test_lock_lifts(client):
    signup(client)
    body = auth.LoginBody(email=EMAIL, password="wrong1234")
    for _ in range(auth.MAX_FAILS):
        with pytest.raises(HTTPException):
            auth.sign_in(body, now=1000)
    assert auth.sign_in(auth.LoginBody(email=EMAIL, password="goa2026trip"), now=1000 + auth.LOCK_SECONDS)["token"]


def test_unknown_email(client):
    assert client.post("/auth/login", json={"email": "ghost@x.com", "password": "abc12345"}).status_code == 401


def reset_code(monkeypatch) -> list[str]:
    sent = []
    monkeypatch.setattr(auth.mailer, "send", lambda to, subject, body: sent.append(body.split()[5].rstrip(".")))
    return sent


def test_forgot_password(client, monkeypatch):
    old = signup(client).json()["token"]
    sent = reset_code(monkeypatch)
    assert client.post("/auth/forgot/start", json={"email": "ghost@x.com"}).json() == {"sent": True}
    assert sent == []
    assert client.post("/auth/forgot/start", json={"email": EMAIL}).json() == {"sent": True}
    code = sent[0]
    wrong = "000000" if code != "000000" else "111111"
    bad = client.post("/auth/forgot", json={"email": EMAIL, "code": wrong, "new_password": "newpass123"})
    assert bad.status_code == 400 and "wrong or has expired" in bad.json()["detail"]
    ok = client.post("/auth/forgot", json={"email": EMAIL, "code": code, "new_password": "newpass123"})
    assert ok.status_code == 200
    again = client.post("/auth/forgot", json={"email": EMAIL, "code": code, "new_password": "other1234"})
    assert again.status_code == 400
    client.cookies.clear()
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.post("/auth/login", json={"email": EMAIL, "password": "newpass123"}).status_code == 200
    assert client.post("/auth/login", json={"email": EMAIL, "password": "goa2026trip"}).status_code == 401


def test_reset_code_expires_and_locks_after_wrong_tries(client, monkeypatch):
    signup(client)
    sent = reset_code(monkeypatch)
    auth.start_reset(auth.EmailIn(email=EMAIL), now=1000)
    late = auth.ForgotBody(email=EMAIL, code=sent[0], new_password="newpass123")
    with pytest.raises(HTTPException):
        auth.forgot_password(late, now=1000 + auth.RESET_SECONDS + 1)
    auth.start_reset(auth.EmailIn(email=EMAIL))
    wrong = "000000" if sent[1] != "000000" else "111111"
    for _ in range(auth.RESET_TRIES):
        client.post("/auth/forgot", json={"email": EMAIL, "code": wrong, "new_password": "newpass123"})
    right = client.post("/auth/forgot", json={"email": EMAIL, "code": sent[1], "new_password": "newpass123"})
    assert right.status_code == 400


def test_reset_codes_are_rate_limited(client, monkeypatch):
    signup(client)
    sent = reset_code(monkeypatch)
    for _ in range(auth.RESETS_PER_EMAIL + 2):
        client.post("/auth/forgot/start", json={"email": EMAIL})
    assert len(sent) == auth.RESETS_PER_EMAIL


def test_banned_accounts_get_no_reset_code(client, monkeypatch):
    uid = signup(client).json()["user"]["id"]
    with connect() as con:
        con.execute("update users set banned = 1 where id = ?", (uid,))
    sent = reset_code(monkeypatch)
    client.post("/auth/forgot/start", json={"email": EMAIL})
    assert sent == []


def test_lockout_is_per_address_and_hides_unknown_emails(client):
    signup(client)
    body = auth.LoginBody(email=EMAIL, password="wrong1234")
    for _ in range(auth.MAX_FAILS):
        with pytest.raises(HTTPException):
            auth.sign_in(body, ip="1.1.1.1", now=1000)
    with pytest.raises(HTTPException) as locked:
        auth.sign_in(auth.LoginBody(email=EMAIL, password="goa2026trip"), ip="1.1.1.1", now=1001)
    assert locked.value.status_code == 429
    assert auth.sign_in(auth.LoginBody(email=EMAIL, password="goa2026trip"), ip="2.2.2.2", now=1001)["token"]
    ghost = auth.LoginBody(email="ghost@x.com", password="wrong1234")
    details = []
    for _ in range(auth.MAX_FAILS - 1):
        with pytest.raises(HTTPException) as e:
            auth.sign_in(ghost, ip="1.1.1.1", now=1000)
        details.append(e.value.detail)
    assert details[-1] == "wrong email or password, 1 try left"


def test_banned_user_learns_it_only_with_the_right_password(client):
    uid = signup(client).json()["user"]["id"]
    with connect() as con:
        con.execute("update users set banned = 1 where id = ?", (uid,))
    assert client.post("/auth/login", json={"email": EMAIL, "password": "wrong1234"}).status_code == 401
    assert client.post("/auth/login", json={"email": EMAIL, "password": "goa2026trip"}).status_code == 403


def test_cookie_session_needs_the_csrf_header(client):
    res = client.post("/auth/signup", json=NEW)
    assert "httponly" in res.headers["set-cookie"].lower() and "samesite=lax" in res.headers["set-cookie"].lower()
    assert client.get("/auth/me").status_code == 200
    body = {"current_password": "goa2026trip", "new_password": "fresh12345"}
    assert client.post("/auth/change-password", json=body).status_code == 403
    ok = client.post("/auth/change-password", json=body, headers={"x-requested-with": "safarnama"})
    assert ok.status_code == 200 and client.get("/auth/me").status_code == 200
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_change_password_guesses_are_limited(client):
    head = {"Authorization": f"Bearer {signup(client).json()['token']}"}
    body = {"current_password": "nope", "new_password": "fresh12345"}
    codes = [
        client.post("/auth/change-password", json=body, headers=head).status_code for _ in range(auth.MAX_FAILS + 1)
    ]
    assert codes[-1] == 429


def test_secret_key_is_required_outside_dev(monkeypatch):
    monkeypatch.setenv("SAFARNAMA_ENV", "")
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(RuntimeError):
        auth.load_secret()
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    assert auth.load_secret() == "x" * 40
    monkeypatch.setenv("SAFARNAMA_ENV", "dev")
    monkeypatch.setenv("SECRET_KEY", "")
    assert len(auth.load_secret()) == 64


def test_auth_requests_are_limited_per_address(client, monkeypatch):
    from app import api

    monkeypatch.setattr(api, "AUTH_PER_IP", 3)
    codes = [client.post("/auth/login", json={"email": f"a{i}@x.com", "password": "x"}).status_code for i in range(4)]
    assert codes == [401, 401, 401, 429]


def test_change_password(client):
    token = signup(client).json()["token"]
    head = {"Authorization": f"Bearer {token}"}
    assert (
        client.post(
            "/auth/change-password", json={"current_password": "nope", "new_password": "fresh12345"}, headers=head
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/auth/change-password", json={"current_password": "goa2026trip", "new_password": "weak"}, headers=head
        ).status_code
        == 422
    )
    res = client.post(
        "/auth/change-password", json={"current_password": "goa2026trip", "new_password": "fresh12345"}, headers=head
    )
    assert res.status_code == 200 and client.get("/auth/me", headers=head).status_code == 401
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {res.json()['token']}"}).status_code == 200


def test_admin_emails_become_admins(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "boss@x.com, other@x.com")
    assert signup(client, email="boss@x.com").json()["user"]["role"] == "admin"
    monkeypatch.setenv("ADMIN_EMAILS", "")
    signup(client, email="later@x.com")
    monkeypatch.setenv("ADMIN_EMAILS", "later@x.com")
    assert (
        client.post("/auth/login", json={"email": "later@x.com", "password": "goa2026trip"}).json()["user"]["role"]
        == "admin"
    )


def test_make_admin_script(client, capsys):
    from scripts.make_admin import main

    signup(client)
    assert main("traveller@example.com") == 0 and main("ghost@x.com") == 1
    assert "is now an admin" in capsys.readouterr().out


def test_bad_tokens_refused(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    u = {"id": 12345, "token_version": 0}
    expired = auth.make_token(u, now=1000)
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).json()["detail"]
        == "session expired, sign in again"
    )
    forged = jwt.encode(
        {"sub": "12345", "tv": 0, "exp": 9999999999}, "a-wrong-secret-that-is-long-enough-for-hs256", algorithm="HS256"
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    ghost = auth.make_token(u)
    assert (
        client.get("/auth/me", headers={"Authorization": f"Bearer {ghost}"}).json()["detail"]
        == "your session ended, sign in again"
    )


def test_ids_are_unique(client, monkeypatch):
    first = signup(client).json()["user"]["id"]
    picks = iter([first - 10000, first - 10000, 5])
    monkeypatch.setattr(auth.secrets, "randbelow", lambda n: next(picks))
    assert signup(client, email="second@x.com").json()["user"]["id"] == 10005


def test_helper_signs_in(client):
    head = sign_in(client, name="Asha")
    assert client.get("/auth/me", headers=head).json()["name"] == "Asha"
