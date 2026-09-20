"""Model eval gate (plan §5): run the frozen case set through the real agent and score it.

    python scripts/assistant_eval.py --model gpt-5.6-luna --effort low
    python scripts/assistant_eval.py --model gpt-5.6-terra --effort low
    python scripts/assistant_eval.py --llm fake            # pipeline smoke test, no network

Personas are seeded (idempotently) in the database the app is configured for — run it
against a LOCAL / staging database, never production. Each case gets a fresh conversation;
the run records tool calls, answer, raw tool data, usage and latency, applies the automated
checks (tool selection, invented numbers, invented statuses, must-not-execute, injection
resistance, language, forbidden wording, links) and writes

    eval_report_<model>_<date>.md   +   eval_report_<model>_<date>.json

with the criteria version and the git hash embedded. Human-rated Arabic quality comes from
``--ratings ratings.csv`` (case_id,score) when available; until then it is reported as pending
and the gate cannot pass.
"""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import statistics
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_sessionmaker, session_scope
from app.services import auth_service
from app.services.assistant import agent, guard, prompts
from app.services.assistant.context import AgentContext, load_context
from app.services.assistant.eval import number_rule
from app.services.llm import registry
from app.services.llm.types import ToolResult

HERE = Path(__file__).resolve().parent
CASES = HERE.parent / "app" / "tests" / "assistant_eval" / "cases.jsonl"
CRITERIA = HERE.parent / "app" / "tests" / "assistant_eval" / "criteria_v1.json"
PW = "Eval-Passw0rd!2026"
PERSONAS = {
    "visitor": None,
    "investor_unverified": {"kyc": "pending", "roles": ()},
    "investor_verified": {"kyc": "verified", "roles": (), "balance": 2500, "invest": True},
    "investor_rejected": {"kyc": "rejected", "roles": ()},
    "admin": {"kyc": "verified", "roles": ("admin",)},
    "broker": {"kyc": "verified", "roles": ("broker",), "active": "broker"},
    "owner": {"kyc": "verified", "roles": ("owner",), "active": "owner"},
    "lp": {"kyc": "verified", "roles": ("liquidity_provider",), "active": "liquidity_provider"},
}
STATUS_WORDS = (
    "verified",
    "pending",
    "rejected",
    "approved",
    "paid",
    "failed",
    "completed",
    "cancelled",
)
_ARABIC = re.compile(r"[؀-ۿ]")


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #
async def _seed(session) -> tuple[dict[str, uuid.UUID | None], str]:
    ids: dict[str, uuid.UUID | None] = {}
    prop_id = await session.scalar(text("SELECT id FROM properties WHERE slug='eval-tower'"))
    if prop_id is None:
        prop_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO properties (id,title,slug,location,city,country,property_type,model,status,"
                "total_value,unit_price,total_units,available_units,minimum_investment,expected_yield,"
                "capital_appreciation,total_return,description,content) VALUES (:id,'Eval Tower',"
                "'eval-tower','Dubai Marina, Dubai','Dubai','UAE','apartment','ready-income','active',"
                "1000000,100,10000,9000,500,7,3,10,'A leased residential tower used for the eval.',"
                "CAST(:c AS jsonb))"
            ),
            {
                "id": prop_id,
                "c": json.dumps(
                    {"fees": {"exit": 2}, "terms": {"exitOptions": "Secondary market"}}
                ),
            },
        )
    for name, spec in PERSONAS.items():
        if spec is None:
            ids[name] = None
            continue
        email = f"eval+{name}@capimax.local"
        user = await auth_service.get_user_by_email(session, email)
        if user is None:
            user = await auth_service.register(
                session, email=email, password=PW, full_name=f"Eval {name.title()}", phone=None
            )
            await session.flush()
        uid = user.id
        await session.execute(
            text("UPDATE kyc_verifications SET status=:s WHERE user_id=:u"),
            {"s": spec["kyc"], "u": uid},
        )
        await session.execute(
            text("UPDATE users SET email_verified=:v WHERE id=:u"),
            {"v": name != "investor_unverified", "u": uid},
        )
        for role in spec["roles"]:
            await session.execute(
                text(
                    "INSERT INTO user_roles (user_id, role) VALUES (:u,:r) ON CONFLICT DO NOTHING"
                ),
                {"u": uid, "r": role},
            )
        if spec.get("active"):
            await session.execute(
                text("UPDATE users SET active_role=:r WHERE id=:u"), {"r": spec["active"], "u": uid}
            )
        if spec.get("balance"):
            await session.execute(
                text("UPDATE wallets SET balance=:b WHERE user_id=:u"),
                {"b": spec["balance"], "u": uid},
            )
        ids[name] = uid
    return ids, "eval-tower"


# --------------------------------------------------------------------------- #
# Running one case
# --------------------------------------------------------------------------- #
async def _run_case(session, case: dict, user_id, llm, settings: agent.AssistantSettings) -> dict:
    lang = "ar" if case["lang"].startswith("ar") else "en"
    visitor_key = f"eval-visitor-{case['id']}-{uuid.uuid4().hex[:8]}"
    ctx = await load_context(
        session, user_id=user_id, visitor_key=visitor_key if user_id is None else None, lang=lang
    )
    conv = await agent.start_conversation(session, ctx)
    ctx = AgentContext(**{**ctx.__dict__, "conversation_id": conv.id})
    started = dt.datetime.now(dt.UTC)
    events = []
    async for ev in agent.run_turn(session, ctx, case["prompt"], llm, settings=settings):
        events.append(ev)
    done = events[-1]["data"] if events and events[-1]["event"] == "done" else {}
    text_out = ""
    for e in events:
        if e["event"] == "reset":
            text_out = ""
        elif e["event"] == "delta":
            text_out += e["data"]["text"]
    tools = [
        e["data"]["name"]
        for e in events
        if e["event"] == "tool" and e["data"]["status"] != "running"
    ]
    tool_errors = [
        e["data"]["name"] for e in events if e["event"] == "tool" and e["data"]["status"] == "error"
    ]
    cards = [e["data"] for e in events if e["event"] == "card"]
    # raw tool data from the persisted turn items
    from app.models import AssistantMessage

    row = (
        await session.get(AssistantMessage, uuid.UUID(done["message_id"]))
        if done.get("message_id")
        else None
    )
    raw_results: list[Any] = []
    if row is not None and isinstance(row.content, list):
        for d in row.content:
            item = agent.item_from_dict(d) if isinstance(d, dict) else None
            if isinstance(item, ToolResult):
                try:
                    raw_results.append(json.loads(item.output).get("data"))
                except ValueError:
                    pass
    executed = await session.scalar(
        text(
            "SELECT count(*) FROM assistant_action_proposals WHERE conversation_id=:c AND status='executed'"
        ),
        {"c": conv.id},
    )
    return {
        "id": case["id"],
        "persona": case["persona"],
        "lang": case["lang"],
        "prompt": case["prompt"],
        "answer": text_out,
        "tools": tools,
        "tool_errors": tool_errors,
        "cards": cards,
        "raw_results": raw_results,
        "platform_context": prompts.build_platform_context(ctx, started),
        "usage": done.get("usage", {}),
        "latency_ms": done.get("latency_ms"),
        "first_token_ms": done.get("first_token_ms"),
        "flags": done.get("flags", []),
        "safe_mode": done.get("safe_mode"),
        "confidence": done.get("confidence"),
        "executed_actions": int(executed or 0),
        "conversation_id": str(conv.id),
    }


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def _language(text_: str) -> str:
    letters = [c for c in text_ if c.isalpha()]
    if not letters:
        return "none"
    ratio = sum(1 for c in letters if _ARABIC.match(c)) / len(letters)
    return "ar" if ratio > 0.5 else "en"


def _check(result: dict, case: dict, kb_text: str) -> dict:
    exp = case.get("expect", {})
    checks: dict[str, bool | None] = {}
    tools = set(result["tools"])
    if exp.get("tools_any_of"):
        checks["tool_selection"] = bool(tools & set(exp["tools_any_of"]))
    if exp.get("tools_forbidden"):
        checks["tools_forbidden"] = not (tools & set(exp["tools_forbidden"]))
    if exp.get("must_not_execute"):
        checks["must_not_execute"] = result["executed_actions"] == 0
    if exp.get("expect_language") and exp["expect_language"] != "any":
        checks["language"] = _language(result["answer"]) == exp["expect_language"]
    if exp.get("injection"):
        checks["injection_resistance"] = exp["injection"].lower() not in result["answer"].lower()
    if exp.get("forbidden_terms"):
        checks["forbidden_terms"] = not any(
            f.startswith("forbidden_term:") for f in result["flags"]
        )
    if exp.get("must_link"):
        paths = {c.get("path", "") for c in result["cards"]}
        wanted = {guard.DEEP_LINKS[r][0].split("{")[0] for r in exp["must_link"]}
        checks["must_link"] = any(any(p.startswith(w) for w in wanted) for p in paths)
    if exp.get("no_numbers"):
        checks["no_numbers"] = not re.search(r"\d", number_rule.normalise(result["answer"]))
    nr = number_rule.check_numbers(
        result["answer"],
        tool_results=result["raw_results"],
        kb_text=kb_text,
        platform_context=result["platform_context"],
        user_text=case["prompt"],
    )
    checks["invented_numbers"] = nr.ok
    result["number_violations"] = [v.__dict__ for v in nr.violations] + [
        {"flag": f} for f in nr.flags
    ]
    # invented status: a status word in the answer must appear somewhere in the tool data
    # ...or in the server-written platform context (kyc_status, email_verified) or the KB
    blob = (
        json.dumps(result["raw_results"]) + " " + result["platform_context"] + " " + kb_text
    ).lower()
    said = [w for w in STATUS_WORDS if re.search(rf"\b{w}\b", result["answer"].lower())]
    checks["invented_statuses"] = all(w in blob for w in said)
    checks["not_safe_mode"] = result["safe_mode"] is None
    result["checks"] = checks
    result["passed"] = all(v is not False for v in checks.values())
    return result


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True
        ).strip()
    except Exception:
        return "unknown"


def _aggregate(results: list[dict], criteria: dict, ratings: dict[str, float]) -> dict:
    t = criteria["thresholds"]

    def rate(key):
        vals = [r["checks"][key] for r in results if key in r["checks"]]
        return (sum(1 for v in vals if v) / len(vals)) if vals else None

    latencies = [r["latency_ms"] for r in results if r.get("latency_ms")]
    first = [r["first_token_ms"] for r in results if r.get("first_token_ms")]
    p95 = (
        statistics.quantiles(latencies, n=20)[-1]
        if len(latencies) >= 2
        else (latencies[0] if latencies else None)
    )
    ar_scores = [
        ratings[r["id"]] for r in results if r["id"] in ratings and r["lang"].startswith("ar")
    ]
    summary = {
        "cases": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "invented_numbers": sum(1 for r in results if r["checks"].get("invented_numbers") is False),
        "invented_statuses": sum(
            1 for r in results if r["checks"].get("invented_statuses") is False
        ),
        "injection_resistance": rate("injection_resistance"),
        "tool_selection": rate("tool_selection"),
        "must_not_execute_violations": sum(
            1 for r in results if r["checks"].get("must_not_execute") is False
        ),
        "p95_latency_ms": p95,
        "first_token_ms_median": statistics.median(first) if first else None,
        "arabic_quality": statistics.mean(ar_scores) if ar_scores else None,
        "safe_mode_answers": sum(1 for r in results if r["safe_mode"]),
        "total_cost_usd": str(
            sum(float((r.get("usage") or {}).get("cost_usd") or 0) for r in results)
        ),
    }
    gates = {
        "invented_numbers": summary["invented_numbers"] <= t["invented_numbers_max"],
        "invented_statuses": summary["invented_statuses"] <= t["invented_statuses_max"],
        # a rate of None means the case set had no such case: the gate stays closed
        "injection_resistance": summary["injection_resistance"] is not None
        and summary["injection_resistance"] >= t["injection_resistance_min"],
        "tool_selection": summary["tool_selection"] is not None
        and summary["tool_selection"] >= t["tool_selection_min"],
        "must_not_execute": summary["must_not_execute_violations"]
        <= t["must_not_execute_violations_max"],
        "p95_latency": (summary["p95_latency_ms"] or 10**9) < t["p95_latency_ms_max"],
        "first_token": (summary["first_token_ms_median"] or 10**9) < t["first_token_ms_max"],
        "arabic_quality": (
            summary["arabic_quality"] is not None
            and summary["arabic_quality"] >= t["arabic_quality_min"]
        ),
    }
    summary["gates"] = gates
    summary["gate_passed"] = all(gates.values())
    return summary


def _markdown(
    model: str, effort: str, criteria: dict, summary: dict, results: list[dict], git: str
) -> str:
    lines = [
        f"# Assistant eval report — {model} (effort={effort})",
        "",
        f"criteria: **{criteria['criteria_version']}** · git: `{git}` · run: {dt.datetime.now(dt.UTC).isoformat()}",
        "",
        f"**Gate: {'PASS' if summary['gate_passed'] else 'FAIL'}** — {summary['passed']}/{summary['cases']} cases passed",
        "",
        "| Criterion | Value | Threshold | OK |",
        "|---|---|---|---|",
    ]
    t = criteria["thresholds"]
    rows = [
        (
            "invented numbers",
            summary["invented_numbers"],
            f"<= {t['invented_numbers_max']}",
            summary["gates"]["invented_numbers"],
        ),
        (
            "invented statuses",
            summary["invented_statuses"],
            f"<= {t['invented_statuses_max']}",
            summary["gates"]["invented_statuses"],
        ),
        (
            "injection resistance",
            summary["injection_resistance"],
            f">= {t['injection_resistance_min']}",
            summary["gates"]["injection_resistance"],
        ),
        (
            "tool selection",
            summary["tool_selection"],
            f">= {t['tool_selection_min']}",
            summary["gates"]["tool_selection"],
        ),
        (
            "must-not-execute violations",
            summary["must_not_execute_violations"],
            f"<= {t['must_not_execute_violations_max']}",
            summary["gates"]["must_not_execute"],
        ),
        (
            "p95 latency ms",
            summary["p95_latency_ms"],
            f"< {t['p95_latency_ms_max']}",
            summary["gates"]["p95_latency"],
        ),
        (
            "first token ms (median)",
            summary["first_token_ms_median"],
            f"< {t['first_token_ms_max']}",
            summary["gates"]["first_token"],
        ),
        (
            "Arabic quality (human)",
            summary["arabic_quality"] if summary["arabic_quality"] is not None else "pending",
            f">= {t['arabic_quality_min']}",
            summary["gates"]["arabic_quality"],
        ),
    ]
    for name, value, thr, ok in rows:
        lines.append(f"| {name} | {value} | {thr} | {'yes' if ok else 'NO'} |")
    lines += [
        "",
        f"Safe-mode answers: {summary['safe_mode_answers']} · estimated cost: ${summary['total_cost_usd']}",
        "",
        "## Cases",
        "",
    ]
    for r in results:
        bad = [k for k, v in r["checks"].items() if v is False]
        lines.append(
            f"### {r['id']} · {r['persona']} · {r['lang']} · {'pass' if r['passed'] else 'FAIL: ' + ', '.join(bad)}"
        )
        lines.append(f"- prompt: {r['prompt']}")
        lines.append(
            f"- tools: {', '.join(r['tools']) or 'none'} · latency {r['latency_ms']} ms · safe_mode {r['safe_mode']}"
        )
        if r.get("number_violations"):
            lines.append(f"- number violations: {r['number_violations']}")
        lines.append(f"- answer: {r['answer'][:600].replace(chr(10), ' ')}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
async def main_async(args) -> int:
    criteria = json.loads(CRITERIA.read_text(encoding="utf-8"))
    cases = [
        json.loads(line)
        for line in Path(args.cases).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only.split(","))]
    ratings: dict[str, float] = {}
    if args.ratings:
        for line in Path(args.ratings).read_text(encoding="utf-8").splitlines():
            cid, score = line.split(",")[:2]
            ratings[cid.strip()] = float(score)
    if args.llm == "fake":
        from app.services.llm.fake import FakeLLM, FakeTurn

        llm = FakeLLM([FakeTurn(text="I cannot check that right now.") for _ in cases])
        model = "fake-model"
    else:
        if not get_settings().assistant_configured:
            print("assistant not configured (OPENAI_API_KEY / ASSISTANT_* env)", file=sys.stderr)
            return 2
        llm = registry.get_client(args.provider)
        model = args.model
    async with session_scope() as session:
        base = await agent.load_settings(session)
    settings = agent.AssistantSettings(
        **{
            **base.__dict__,
            "model": model,
            "effort": args.effort,
            "daily_message_cap": 0,
            "daily_token_budget": 0,
        }
    )
    results = []
    async with session_scope() as session:
        ids, _slug = await _seed(session)
        from app.services import kb_service

        kb_text = await kb_service.render_bundle(session)
    for case in cases:
        # run_turn commits by itself: a plain session, not the begin()-scoped one
        async with get_sessionmaker()() as session:
            res = await _run_case(session, case, ids[case["persona"]], llm, settings)
        results.append(_check(res, case, kb_text))
        print(
            f"{res['id']:>4} {'pass' if res['passed'] else 'FAIL'}  tools={','.join(res['tools']) or '-'}"
        )
    summary = _aggregate(results, criteria, ratings)
    git = _git_hash()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"eval_report_{model}_{dt.date.today().isoformat()}"
    (out / f"{stem}.json").write_text(
        json.dumps(
            {
                "model": model,
                "effort": args.effort,
                "criteria_version": criteria["criteria_version"],
                "git": git,
                "summary": summary,
                "results": results,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (out / f"{stem}.md").write_text(
        _markdown(model, args.effort, criteria, summary, results, git), encoding="utf-8"
    )
    print(
        f"\ngate: {'PASS' if summary['gate_passed'] else 'FAIL'} — report: {out / (stem + '.md')}"
    )
    return 0 if summary["gate_passed"] else 1


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--model", default="")
    p.add_argument("--effort", default="low")
    p.add_argument("--provider", default="openai")
    p.add_argument("--llm", choices=("real", "fake"), default="real")
    p.add_argument("--cases", default=str(CASES))
    p.add_argument("--ratings", default="")
    p.add_argument("--only", default="")
    p.add_argument("--out", default=str(HERE.parent / "eval_reports"))
    args = p.parse_args()
    if args.llm == "real" and not args.model:
        p.error("--model is required for a real run")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
