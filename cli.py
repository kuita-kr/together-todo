"""
cli.py — study route -> dispatch in the terminal (v2). Pick a child first.

    python cli.py

Try (as 서연, age 4):     양치 했어   /   손 씻을게   /   장난감 정리했어
Try (as 민준, age 8):     숙제 다 했어  ->  then as a parent:  숙제 아직 안 했어
Watch the verb conjugate as a card moves columns, and 'reverse' send it back.
Type 'switch' to change child, 'q' to quit.
"""

import board
import router

LABELS = {"todo": "할 일", "doing": "하는 중", "done": "끝!"}


def show(owner):
    snap = board.snapshot(owner)
    u = snap["user"]
    print("\n" + "=" * 56)
    print(f"  {u['name']} ({u['age']}살)")
    for col in board.COLUMNS:
        cards = snap["columns"][col]
        names = ", ".join(
            c["spoken"] + (f" ★{c['stars']}" if c["stars"] else "") for c in cards) or "—"
        print(f"  {LABELS[col]:<8} {names}")
    print("=" * 56)


def pick_user():
    us = board.list_users()
    print("누구세요? Pick a child:")
    for u in us:
        print(f"  {u['id']}. {u['name']} ({u['age']}살)")
    raw = input("number > ").strip()
    ids = {str(u["id"]): u["id"] for u in us}
    return ids.get(raw, us[0]["id"])


def main():
    print("together-todo — tool-calling sandbox (v2)\n")
    owner = pick_user()
    show(owner)
    while True:
        try:
            utt = input("\n💬  ")
        except (EOFError, KeyboardInterrupt):
            break
        cmd = utt.strip().lower()
        if cmd in {"q", "quit", "exit"}:
            break
        if cmd in {"switch", "u", "user"}:
            owner = pick_user(); show(owner); continue
        out = router.handle(utt, owner)
        a = out["action"]
        print(f"   router  -> tool={a['tool']}  "
              f"args={ {k: v for k, v in a.items() if v and k != 'tool'} }")
        res = out["result"]
        if res.get("tool") == "predict":
            top = ", ".join(f"{r['subject']}({r['score']})" for r in res["ranked"][:3])
            print("   predict -> " + (top or "no history yet"))
        else:
            print(f"   result  -> {'OK' if res.get('ok') else 'warn ' + str(res)}")
        show(owner)


if __name__ == "__main__":
    main()
