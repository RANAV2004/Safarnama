# smoke test
import sys
from datetime import date, timedelta

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
TRIP = {
    "origin": "Delhi",
    "destination": "Jaipur",
    "start_date": str(date.today() + timedelta(days=30)),
    "end_date": str(date.today() + timedelta(days=32)),
    "budget_inr": 15000,
    "travellers": 2,
}


def main():
    with httpx.Client(base_url=API, timeout=30) as c:
        assert c.get("/health").json()["ok"]
        account = {"email": "smoke@example.com", "password": "smoke1234"}
        res = c.post("/auth/signup", json={**account, "name": "Smoke Test", "birth_date": "1999-01-01"})
        token = (res if res.status_code == 201 else c.post("/auth/login", json=account)).json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        c.cookies.clear()
        assert c.post("/plan", json=TRIP).status_code == 401
        plan = c.post("/plan", json=TRIP, headers=auth).raise_for_status().json()
        assert plan["days"] and plan["total_cost"] > 0 and plan["trip_id"]
        assert any(t["id"] == plan["trip_id"] for t in c.get("/trips", headers=auth).json())
        pdf = c.post("/plan/pdf", json=plan, headers=auth).raise_for_status()
        assert pdf.content.startswith(b"%PDF")
    print(
        f"smoke test passed: {len(plan['days'])} days, total Rs {plan['total_cost']:,}, pdf {len(pdf.content):,} bytes"
    )


if __name__ == "__main__":
    main()
