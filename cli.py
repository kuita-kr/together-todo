"""
cli.py — study the agent in your terminal, no server, no API key.

    python cli.py

Type things a child might say (Korean or English) and watch the router pick a
tool and the board change. This is the fastest way to *feel* route -> dispatch
before tomorrow's meeting.

Examples to try:
    손 씻기 다 했어            -> complete
    숙제 시작할게             -> start
    저녁 별점 5점             -> rate
    내일 뭐 할까?            -> predict
    양치질 추가해줘           -> register
"""

import board
import router


def show():
    snap = board.snapshot()
    labels = {"todo": "할 일 (To do)", "doing": "하는 중 (Doing)", "done": "끝! (Done)"}
    print("\n" + "=" * 52)
    for col in board.COLUMNS:
        cards = snap["columns"][col]
        names = ", ".join(
            f"{c['korean']}" + (f"★{c['stars']}" if c['stars'] else "")
            for c in cards) or "—"
        print(f"  {labels[col]:<20} {names}")
    print("=" * 52)


def main():
    print("together-todo — tool-calling sandbox")
    print("Type a child's message; 'q' to quit. (USE_GEMINI=1 to use the LLM)\n")
    show()
    while True:
        try:
            utt = input("\n👧  ")
        except (EOFError, KeyboardInterrupt):
            break
        if utt.strip().lower() in {"q", "quit", "exit"}:
            break
        out = router.handle(utt)
        a = out["action"]
        print(f"   router  -> tool={a['tool']}  args="
              f"{ {k: v for k, v in a.items() if v and k != 'tool'} }")
        ok = out["result"].get("ok")
        if out["result"].get("tool") == "predict":
            ranked = out["result"]["ranked"][:3]
            print("   predict -> " + (", ".join(
                f"{r['korean']}({r['score']})" for r in ranked) or "no history yet"))
        else:
            print(f"   result  -> {'✅' if ok else '⚠️ ' + str(out['result'])}")
        show()


if __name__ == "__main__":
    main()
