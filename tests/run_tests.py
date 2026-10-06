"""
Run the test questions and score the agent.

    python tests/run_tests.py                     # all questions
    python tests/run_tests.py rat_trend danger    # just these
    python tests/run_tests.py --no-checker        # same questions without the checker

Comparing a run with and without --no-checker shows whether the checker earns its cost.
Each run saves a full report to tests/results/.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # so "agent" can be imported

from agent.agent import ask                    # noqa: E402
from agent.tools import open_sandbox           # noqa: E402
from tests.questions import QUESTIONS          # noqa: E402

RESULTS = Path(__file__).parent / "results"


def truth_value(sql):
    con = open_sandbox()
    value = con.execute(sql).fetchone()[0]
    con.close()
    return value


def grade(test, answer, stats):
    """Return a list of failed checks (empty list = pass)."""
    failures = []
    text = answer.lower()
    if "expect_any" in test and not any(p.lower() in text for p in test["expect_any"]):
        failures.append(f"none of {test['expect_any']} found")
    for phrase in test.get("expect_none", []):
        if phrase.lower() in text:
            failures.append(f"should not say '{phrase}'")
    if "max_queries" in test and stats["queries"] > test["max_queries"]:
        failures.append(f"ran {stats['queries']} queries, expected at most {test['max_queries']}")
    if "truth_sql" in test:
        value = truth_value(test["truth_sql"])
        forms = {str(value).lower()}
        if isinstance(value, int):
            forms.add(f"{value:,}")
        if not any(form in text for form in forms):
            failures.append(f"correct value {value} not in answer")
    return failures


def main():
    args = sys.argv[1:]
    use_checker = "--no-checker" not in args
    wanted = [a for a in args if not a.startswith("--")]
    tests = [t for t in QUESTIONS if not wanted or t["id"] in wanted]

    rows, report = [], []
    for test in tests:
        print(f"Running {test['id']}...", flush=True)
        started = time.time()
        answer, stats = ask(test["question"], verbose=False, use_checker=use_checker)
        seconds = time.time() - started
        failures = grade(test, answer, stats)
        rows.append((test["id"], not failures, stats, seconds))
        report.append(
            f"## {test['id']}: {'PASS' if not failures else 'FAIL'}\n\n"
            f"**Trap:** {test['trap']}\n\n**Question:** {test['question']}\n\n"
            f"**Failed checks:** {'; '.join(failures) or 'none'}\n\n"
            f"**Checker:** {stats['final_check']}"
            f"{' (after one revision)' if stats['revised'] else ''}"
            f"{'; open: ' + '; '.join(stats['open_problems']) if stats['open_problems'] else ''}\n\n"
            f"**Stats:** {stats['queries']} queries, {seconds:.0f}s, ${stats['cost_usd']:.3f}\n\n"
            f"```\n{answer.strip()}\n```\n"
        )
        print(f"  {'PASS' if not failures else 'FAIL: ' + '; '.join(failures)}")

    passed = sum(ok for _, ok, _, _ in rows)
    total_cost = sum(s["cost_usd"] for _, _, s, _ in rows)
    print(f"\n{'test':<18}{'result':<8}{'queries':>8}{'revised':>9}{'secs':>6}{'cost':>8}")
    for test_id, ok, stats, seconds in rows:
        print(f"{test_id:<18}{'pass' if ok else 'FAIL':<8}{stats['queries']:>8}"
              f"{'yes' if stats['revised'] else '':>9}{seconds:>6.0f}{stats['cost_usd']:>8.3f}")
    print(f"\n{passed}/{len(rows)} passed · total ${total_cost:.2f} · "
          f"checker {'on' if use_checker else 'off'}")

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    mode = "checker" if use_checker else "no-checker"
    out = RESULTS / f"{stamp}_{mode}.md"
    out.write_text(f"# Test run {stamp} ({mode})\n\n{passed}/{len(rows)} passed, "
                   f"${total_cost:.2f}\n\n" + "\n".join(report), encoding="utf-8")
    print(f"Full answers saved to {out}")


if __name__ == "__main__":
    main()
