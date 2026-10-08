"""
Graded evaluation: run every test question, then have a grader score each answer.

    python tests/evaluate.py              # all questions
    python tests/evaluate.py danger weather

An answer PASSES when its simple checks pass AND the grader gives at least 3 on every
dimension and an average of at least 4. Writes:
  tests/results/<time>_eval.md   full report: answers, scores and the grader's reasons
  web/scorecard.json             summary the website shows publicly
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent import CHECKER_MODEL, MODEL, ask, price_of   # noqa: E402
from tests.grader import GRADER_MODEL, RUBRIC, grade          # noqa: E402
from tests.questions import QUESTIONS                         # noqa: E402
from tests.run_tests import grade as simple_checks, truth_value  # noqa: E402

ROOT = Path(__file__).parent.parent
PARALLEL = 4  # questions answered at the same time


def evaluate_one(test):
    started = time.time()
    try:
        answer, stats = ask(test["question"], verbose=False)
    except Exception as err:
        answer, stats = f"ERROR: {err}", {"queries": 0, "charts": [], "evidence": [],
                                          "cost_usd": 0.0, "final_check": "skipped"}
    seconds = time.time() - started
    failures = simple_checks(test, answer, stats)
    true = truth_value(test["truth_sql"]) if "truth_sql" in test else None
    graded = grade(test, answer, stats.get("evidence", []), true)
    scores = graded["scores"]
    grader_cost = 0.0
    if graded.get("usage"):
        p_in, p_out = price_of(GRADER_MODEL)
        grader_cost = (graded["usage"].input_tokens * p_in
                       + graded["usage"].output_tokens * p_out) / 1_000_000
    passed = (not failures and bool(scores) and min(scores.values()) >= 3
              and graded["average"] >= 4)
    print(f"  {'PASS' if passed else 'FAIL'}  {test['id']:<20} "
          f"{' '.join(f'{k[:4]}={v}' for k, v in scores.items())}", flush=True)
    return {"id": test["id"], "question": test["question"], "trap": test["trap"],
            "passed": passed, "failed_checks": failures, "scores": scores,
            "reasons": graded["reasons"], "average": graded["average"],
            "answer": answer, "charts": len(stats.get("charts", [])),
            "queries": stats.get("queries", 0), "checker": stats.get("final_check"),
            "seconds": round(seconds), "agent_cost": stats.get("cost_usd", 0.0),
            "grader_cost": round(grader_cost, 4)}


def main():
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")]
    tests = [t for t in QUESTIONS if not wanted or t["id"] in wanted]
    print(f"Evaluating {len(tests)} questions, {PARALLEL} at a time...")
    started = time.time()
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        results = list(pool.map(evaluate_one, tests))

    graded = [r for r in results if r["scores"]]
    averages = {dim: round(sum(r["scores"][dim] for r in graded) / len(graded), 2)
                for dim in RUBRIC} if graded else {}
    passed = sum(r["passed"] for r in results)
    agent_cost = sum(r["agent_cost"] for r in results)
    grader_cost = sum(r["grader_cost"] for r in results)

    print(f"\n{'dimension':<10}{'average':>8}")
    for dim, avg in averages.items():
        print(f"{dim:<10}{avg:>8.2f}")
    print(f"\n{passed}/{len(results)} passed · answers ${agent_cost:.2f} + grading "
          f"${grader_cost:.2f} · {time.time() - started:.0f}s")

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    lines = [f"# Graded evaluation {stamp}", "",
             f"{passed}/{len(results)} passed. Agent {MODEL}, checker {CHECKER_MODEL}, "
             f"grader {GRADER_MODEL}.", "",
             "| Dimension | Average (1-5) |", "|---|---|"]
    lines += [f"| {d} | {a} |" for d, a in averages.items()]
    for r in results:
        lines += ["", f"## {r['id']}: {'PASS' if r['passed'] else 'FAIL'}", "",
                  f"**Question:** {r['question']}  ", f"**Trap:** {r['trap']}  ",
                  f"**Simple checks:** {'; '.join(r['failed_checks']) or 'all passed'}  ",
                  f"**Stats:** {r['queries']} queries, {r['charts']} charts, {r['seconds']}s, "
                  f"${r['agent_cost']:.3f}", ""]
        lines += [f"- **{d}: {r['scores'].get(d, '?')}** {r['reasons'].get(d, '')}" for d in RUBRIC]
        lines += ["", "```", r["answer"].strip(), "```"]
    out = ROOT / "tests" / "results" / f"{stamp}_eval.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    if not wanted:  # only a full run updates the public scorecard
        scorecard = {
            "run_at": datetime.now().isoformat(timespec="minutes"),
            "models": {"agent": MODEL, "checker": CHECKER_MODEL, "grader": GRADER_MODEL},
            "questions": len(results), "passed": passed, "averages": averages,
            "rubric": RUBRIC,
            "cost_per_answer_usd": round(agent_cost / len(results), 3),
            "results": [{k: r[k] for k in ("id", "question", "trap", "passed", "scores",
                                           "reasons", "seconds", "charts")} for r in results],
        }
        (ROOT / "web" / "scorecard.json").write_text(json.dumps(scorecard, indent=2),
                                                     encoding="utf-8")
        print("Scorecard written to web/scorecard.json")
    print(f"Full report: {out}")


if __name__ == "__main__":
    main()
