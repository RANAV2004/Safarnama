# make admin
import sys

from app.db import connect


def main(email: str) -> int:
    with connect() as con:
        n = con.execute("update users set role = 'admin' where email = ?", (email.strip().lower(),)).rowcount
    print(f"{email} is now an admin" if n else f"no account for {email}, sign up first")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(
        main(sys.argv[1]) if len(sys.argv) == 2 else print("usage: python -m scripts.make_admin you@example.com") or 2
    )
