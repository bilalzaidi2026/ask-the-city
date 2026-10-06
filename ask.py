"""
Ask the city a question from the terminal.

    python ask.py "Which borough has the most rat complaints per resident?"
"""
import sys
import time

from agent.agent import ask

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Usage: python ask.py "your question"')
    question = " ".join(sys.argv[1:])
    print(f"\nQUESTION  {question}\n")

    started = time.time()
    answer, stats = ask(question)

    print("\n" + "=" * 70)
    print(answer)
    print("=" * 70)
    check = {"pass": "checker passed", "revise": "checker still has concerns",
             "skipped": "checker skipped"}[stats["final_check"]]
    revised = " after one revision" if stats["revised"] else ""
    print(f"{stats['tool_calls']} tool calls · {time.time() - started:.0f}s · "
          f"about ${stats['cost_usd']:.3f} · {check}{revised}")
    for problem in stats["open_problems"]:
        print(f"  open concern: {problem}")
