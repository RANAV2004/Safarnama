# evals
import argparse
import json
import time
from pathlib import Path
from statistics import mean

from app import llm
from app.graph import plan_trip
from app.state import TripRequest, TripState
from app.tools.budget import BudgetTooLowError
from app.tools.checks import run_all_checks
from evals.baseline import single_llm, single_pass

HERE = Path(__file__).parent


def score(s: TripState, ms: float, tokens: int, cost: float) -> dict:
    issues = run_all_checks(s)
    complete = bool(s.selected_outbound and s.selected_return and (s.selected_stay or s.request.nights == 0) and s.days)
    return {
        "types": [i.type for i in issues],
        "complete": complete,
        "fits": complete and s.over_budget_by == 0,
        "over_by": s.over_budget_by,
        "violations": len(issues),
        "clean": complete and not issues,
        "ms": ms,
        "tokens": tokens,
        "cost": cost,
        "rounds": s.round,
        "places": len(s.selected_places),
    }


def run_system(name: str, fn, trips: list[dict]) -> list[dict]:
    rows = []
    for t in trips:
        req = TripRequest(**{k: v for k, v in t.items() if k not in ("id", "factor")})
        t0 = time.perf_counter()
        try:
            out = fn(req)
        except BudgetTooLowError:
            continue
        state, usage = out if isinstance(out, tuple) else (out, None)
        ms = (time.perf_counter() - t0) * 1000
        tokens = usage.tokens if usage else sum(e.tokens for e in state.trace)
        cost = usage.cost_usd if usage else sum(e.cost_usd for e in state.trace)
        rows.append({"trip": t["id"], "factor": t["factor"], **score(state, ms, tokens, cost)})
    print(f"{name}: {len(rows)} trips done")
    return rows


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    over = [r["over_by"] for r in rows if r["over_by"] > 0]
    return {
        "trips": n,
        "complete plans": f"{sum(r['complete'] for r in rows) / n:.0%}",
        "within budget": f"{sum(r['fits'] for r in rows) / n:.0%}",
        "avg overspend when over": f"Rs {mean(over):,.0f}" if over else "-",
        "plans with zero violations": f"{sum(r['clean'] for r in rows) / n:.0%}",
        "avg violations per plan": f"{mean(r['violations'] for r in rows):.2f}",
        "avg places per plan": f"{mean(r['places'] for r in rows):.1f}",
        "avg negotiation rounds": f"{mean(r['rounds'] for r in rows):.2f}",
        "avg latency": f"{mean(r['ms'] for r in rows):,.0f} ms",
        "avg tokens": f"{mean(r['tokens'] for r in rows):,.0f}",
        "avg cost": f"${mean(r['cost'] for r in rows):.4f}",
    }


def by_factor(rows: list[dict]) -> dict:
    out = {}
    for f in sorted({r["factor"] for r in rows}):
        sub = [r for r in rows if r["factor"] == f]
        out[f] = f"{sum(r['fits'] for r in sub)}/{len(sub)}"
    return out


def violation_types(rows: list[dict]) -> dict:
    out = {}
    for r in rows:
        for t in r["types"]:
            out[t] = out.get(t, 0) + 1
    return out


def table(results: dict[str, dict]) -> str:
    names = list(results)
    keys = list(next(iter(results.values())))
    lines = ["| metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines += [f"| {k} | " + " | ".join(str(results[n][k]) for n in names) + " |" for k in keys]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()
    trips = [json.loads(line) for line in (HERE / "trips.jsonl").read_text().splitlines() if line.strip()][: args.limit]
    systems = {"multi-agent": plan_trip, "single pass (no negotiation, no critic)": single_pass}
    if llm.enabled():
        systems["single LLM call"] = single_llm
    raw = {name: run_system(name, fn, trips) for name, fn in systems.items()}
    summary = {name: summarise(rows) for name, rows in raw.items()}
    fit = {name: by_factor(rows) for name, rows in raw.items()}
    mode = "LLM on" if llm.enabled() else "LLM off (rule based agents)"
    md = [
        f"# Eval results\n\nMode: {mode}. Trips: {len(trips)} from `evals/trips.jsonl`. Hard checks: `app/tools/checks.py`.\n",
        table(summary),
        "\n## Within budget by budget level\n\nBudget level is the trip budget divided by a fair cost estimate (0.6 very tight, 1.6 generous).\n",
    ]
    md.append("| budget level | " + " | ".join(fit) + " |\n|---|" + "---|" * len(fit))
    for f in next(iter(fit.values())):
        md.append(f"| {f} | " + " | ".join(fit[n][f] for n in fit) + " |")
    kinds = {name: violation_types(rows) for name, rows in raw.items()}
    all_kinds = sorted({k for v in kinds.values() for k in v})
    if all_kinds:
        md.append("\n## Violations by type\n")
        md.append("| type | " + " | ".join(kinds) + " |\n|---|" + "---|" * len(kinds))
        md += [f"| {k} | " + " | ".join(str(kinds[n].get(k, 0)) for n in kinds) + " |" for k in all_kinds]
    (HERE / "results.md").write_text("\n".join(md) + "\n")
    (HERE / "results.json").write_text(json.dumps(raw, indent=1))
    print(table(summary))


if __name__ == "__main__":
    main()
