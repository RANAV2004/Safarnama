# accounts and sessions
import hashlib
import hmac
import logging
import math
import os
import re
import secrets
import time
from datetime import date

import jwt
from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from app import mailer
from app.db import connect, now_iso, rows
from app.limits import LIMITS

TOKEN_DAYS = 7
MAX_FAILS = 5
LOCK_SECONDS = 900
ITERATIONS = int(os.getenv("PASSWORD_ROUNDS", "200000"))
MIN_AGE = 13
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PUBLIC = "id, name, email, birth_date, role, banned, created, last_login"
RESET_SECONDS = 900
RESET_TRIES = 5
RESETS_PER_EMAIL = 3
COOKIE = "safarnama_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "safarnama"
DEV_ENVS = {"dev", "test"}


def dev_mode() -> bool:
    return os.getenv("SAFARNAMA_ENV", "") in DEV_ENVS


def load_secret() -> str:
    key = os.getenv("SECRET_KEY", "")
    if len(key) >= 32:
        return key
    if dev_mode():
        logging.getLogger("safarnama").warning("SECRET_KEY is missing or short, using a random one for this run")
        return secrets.token_hex(32)
    raise RuntimeError(
        "set SECRET_KEY to a random string of at least 32 characters, or SAFARNAMA_ENV=dev for local use"
    )


SECRET = load_secret()


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}


def check_password_rules(v: str) -> str:
    if len(v) < 8 or not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
        raise ValueError("password needs at least 8 characters with a letter and a number")
    if len(v) > 128:
        raise ValueError("password is too long")
    return v


class EmailIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v) or len(v) > 254:
            raise ValueError("enter a valid email address")
        return v


class LoginBody(EmailIn):
    password: str = Field(min_length=1, max_length=128)


class SignupBody(EmailIn):
    name: str = Field(min_length=1, max_length=60)
    birth_date: date
    password: str

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("enter your name")
        return v

    @field_validator("birth_date")
    @classmethod
    def check_birth(cls, v: date) -> date:
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if v > today or age > 120:
            raise ValueError("enter a real date of birth")
        if age < MIN_AGE:
            raise ValueError(f"you need to be at least {MIN_AGE} to use Safarnama")
        return v

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return check_password_rules(v)


class ForgotBody(EmailIn):
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return check_password_rules(v)


class ChangeBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return check_password_rules(v)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    except ValueError:
        return False
    return hmac.compare_digest(got.hex(), digest)


DUMMY_HASH = hash_password(secrets.token_hex(8))


def new_id(con) -> int:
    while True:
        uid = 10000 + secrets.randbelow(90000)
        if not con.execute("select 1 from users where id = ?", (uid,)).fetchone():
            return uid


def find(con, email: str | None = None, uid: int | None = None) -> dict | None:
    if email:
        cur = con.execute("select * from users where email = ?", (email,))
    else:
        cur = con.execute("select * from users where id = ?", (uid,))
    found = rows(cur)
    return found[0] if found else None


def public(u: dict) -> dict:
    return {k: u[k] for k in PUBLIC.split(", ")} | {"banned": bool(u["banned"])}


def make_token(u: dict, now: float | None = None) -> str:
    now = now or time.time()
    claims = {"sub": str(u["id"]), "tv": u["token_version"], "iat": int(now), "exp": int(now + TOKEN_DAYS * 86400)}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def session(u: dict) -> dict:
    return {"token": make_token(u), "user": public(u)}


def set_cookie(response: Response, token: str):
    response.set_cookie(
        COOKIE,
        token,
        max_age=TOKEN_DAYS * 86400,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "0" if dev_mode() else "1") == "1",
        samesite="lax",
        path="/",
    )


def clear_cookie(response: Response):
    response.delete_cookie(COOKIE, path="/")


def wait_message(seconds: int) -> str:
    mins = math.ceil(seconds / 60)
    return f"too many wrong tries, try again in {mins} minute{'s' if mins > 1 else ''}"


def sign_up(body: SignupBody) -> dict:
    with connect() as con:
        if find(con, email=body.email):
            raise HTTPException(409, "an account with this email already exists, sign in instead")
        uid = new_id(con)
        role = "admin" if body.email in admin_emails() else "user"
        con.execute(
            "insert into users (id, name, email, birth_date, password, role, created, last_login)"
            " values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uid,
                body.name,
                body.email,
                body.birth_date.isoformat(),
                hash_password(body.password),
                role,
                now_iso(),
                now_iso(),
            ),
        )
        return session(find(con, uid=uid))


def sign_in(body: LoginBody, ip: str = "", now: float | None = None) -> dict:
    now = now or time.time()
    key = ("login", body.email, ip)
    wait = LIMITS.wait(key, MAX_FAILS, LOCK_SECONDS, now)
    if wait:
        raise HTTPException(429, wait_message(wait))
    with connect() as con:
        u = find(con, email=body.email)
        matched = password_matches(body.password, u["password"] if u else DUMMY_HASH)
        if not (u and matched):
            LIMITS.add(key, now)
            left = MAX_FAILS - LIMITS.count(key, LOCK_SECONDS, now)
            hint = f", {left} {'try' if left == 1 else 'tries'} left" if 0 < left < 3 else ""
            raise HTTPException(401, "wrong email or password" + hint)
        LIMITS.clear(key)
        if u["banned"]:
            raise HTTPException(403, "this account has been suspended, contact the Safarnama team")
        role = "admin" if u["email"] in admin_emails() else u["role"]
        con.execute("update users set last_login = ?, role = ? where id = ?", (now_iso(), role, u["id"]))
        return session(find(con, uid=u["id"]))


def code_hash(email: str, code: str) -> str:
    return hmac.new(SECRET.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def start_reset(body: EmailIn, now: float | None = None) -> dict:
    now = now or time.time()
    key = ("reset", body.email)
    if LIMITS.wait(key, RESETS_PER_EMAIL, RESET_SECONDS, now):
        return {"sent": True}
    LIMITS.add(key, now)
    with connect() as con:
        u = find(con, email=body.email)
        if not u or u["banned"]:
            return {"sent": True}
        code = f"{secrets.randbelow(10**6):06d}"
        con.execute(
            "insert into reset_codes (email, code, expires, tries) values (?, ?, ?, 0)"
            " on conflict(email) do update set code = excluded.code, expires = excluded.expires, tries = 0",
            (body.email, code_hash(body.email, code), now + RESET_SECONDS),
        )
    text = (
        f"Your Safarnama reset code is {code}. It works for 15 minutes. If you did not ask for it, ignore this email."
    )
    mailer.send(body.email, "Your Safarnama reset code", text)
    return {"sent": True}


def forgot_password(body: ForgotBody, now: float | None = None) -> dict:
    now = now or time.time()
    wrong = HTTPException(400, "that code is wrong or has expired, ask for a new one")
    with connect() as con:
        row = con.execute("select code, expires, tries from reset_codes where email = ?", (body.email,)).fetchone()
        if not row or row[1] < now or row[2] >= RESET_TRIES:
            raise wrong
        if not hmac.compare_digest(row[0], code_hash(body.email, body.code)):
            con.execute("update reset_codes set tries = tries + 1 where email = ?", (body.email,))
            con.commit()
            raise wrong
        con.execute("delete from reset_codes where email = ?", (body.email,))
        u = find(con, email=body.email)
        if not u or u["banned"]:
            raise wrong
        con.execute(
            "update users set password = ?, token_version = token_version + 1 where id = ?",
            (hash_password(body.new_password), u["id"]),
        )
        return session(find(con, uid=u["id"]))


def change_password(uid: int, body: ChangeBody, now: float | None = None) -> dict:
    now = now or time.time()
    key = ("change", uid)
    wait = LIMITS.wait(key, MAX_FAILS, LOCK_SECONDS, now)
    if wait:
        raise HTTPException(429, wait_message(wait))
    with connect() as con:
        u = find(con, uid=uid)
        if not password_matches(body.current_password, u["password"]):
            LIMITS.add(key, now)
            raise HTTPException(400, "your current password is wrong")
        LIMITS.clear(key)
        con.execute(
            "update users set password = ?, token_version = token_version + 1 where id = ?",
            (hash_password(body.new_password), uid),
        )
        return session(find(con, uid=uid))


bearer = HTTPBearer(auto_error=False)


def current_account(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    head = {"WWW-Authenticate": "Bearer"}
    token = creds.credentials if creds else request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "sign in first", headers=head)
    if not creds and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            raise HTTPException(403, "request blocked, reload the page and try again")
    try:
        claims = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(401, "session expired, sign in again", headers=head) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, "invalid session, sign in again", headers=head) from e
    with connect() as con:
        u = find(con, uid=int(claims["sub"]))
    if not u or u["token_version"] != claims.get("tv"):
        raise HTTPException(401, "your session ended, sign in again", headers=head)
    if u["banned"]:
        raise HTTPException(401, "this account has been suspended", headers=head)
    return u


def current_user(acc: dict = Depends(current_account)) -> str:
    return acc["email"]


def admin_account(acc: dict = Depends(current_account)) -> dict:
    if acc["role"] != "admin":
        raise HTTPException(403, "only admins can do that")
    return acc
