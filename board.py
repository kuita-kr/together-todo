"""
board.py — the "world" the agent acts on (v2).

New in v2 (the features you asked for):
  • USERS with ages (two children, 4 & 8) — every card has an `owner`.
  • Cards are built from PARTS:  prefix + subject + verb.
    The verb is CONJUGATED BY COLUMN, so a card teaches tense as it moves:
        todo  양치 하기   ->  doing  양치 하는 중  ->  done  양치 했어!
    The verb part is recyclable (하다 powers 양치/숙제/정리), and the prefix is
    recyclable too (저녁/아침 + 메뉴).
  • GLOSSARY: house-approved phrasing. "양치질" or "이 닦기" both resolve to the
    simple card subject "양치", so a parent can speak naturally.
  • reverse_task: send a card BACK a column (parent assessment: "아직 안 했네").

Still just in-memory dicts — swap for MongoDB later, architecture unchanged.
"""

from __future__ import annotations
from datetime import datetime, date
from collections import defaultdict
import itertools

COLUMNS = ("todo", "doing", "done")

# --- Verb conjugation table (teaches tense as a card changes column) --------
# Korean conjugation is irregular, so we keep an explicit small table instead
# of a morphology engine. Add a verb = add a row. `tight` controls spacing for
# the spoken form: 양치+하기 -> "양치하기" (compound), 손+씻기 -> "손 씻기".
VERBS: dict[str, dict] = {
    "하다":    {"tight": True,  "todo": "하기",   "doing": "하는 중",   "done": "했어!"},
    "정리하다": {"tight": True,  "todo": "정리하기", "doing": "정리하는 중", "done": "정리했어!"},
    "씻다":    {"tight": False, "todo": "씻기",   "doing": "씻는 중",   "done": "씻었어!"},
    "고르다":  {"tight": False, "todo": "고르기", "doing": "고르는 중", "done": "골랐어!"},
    "먹다":    {"tight": False, "todo": "먹기",   "doing": "먹는 중",   "done": "먹었어!"},
    "읽다":    {"tight": False, "todo": "읽기",   "doing": "읽는 중",   "done": "읽었어!"},
}

# --- House glossary: casual / variant phrasing -> canonical card subject -----
# This is your "house-approved terms" map. Extend freely; this is the thing
# that lets you say "양치 했어?" and still hit the "양치" card.
GLOSSARY: dict[str, str] = {
    "양치질": "양치", "이 닦기": "양치", "이닦기": "양치", "이빨": "양치",
    "손씻기": "손", "손 씻기": "손",
    "밥": "저녁 메뉴", "저녁밥": "저녁 메뉴", "메뉴 고르기": "메뉴",
    "공부": "숙제", "책읽기": "책",
}

# --- State -----------------------------------------------------------------
_uid = itertools.count(1)
_cid = itertools.count(1)
users: dict[int, dict] = {}
board: dict[int, dict] = {}
history: list[dict] = []


# --- Users -----------------------------------------------------------------
def add_user(name: str, age: int) -> dict:
    uid = next(_uid)
    users[uid] = {"id": uid, "name": name, "age": int(age)}
    return users[uid]


# --- Composition: parts -> displayed / spoken Korean ------------------------
def parts(card: dict) -> dict:
    """Return the three display chips so the UI can show 'recycled' pieces."""
    ending = VERBS.get(card["verb"], {}).get(card["status"], "")
    return {"prefix": card.get("prefix", ""), "subject": card["subject"], "ending": ending}


def spoken(card: dict) -> str:
    """Natural joined form for TTS (correct tense for the current column)."""
    p = parts(card)
    v = VERBS.get(card["verb"], {})
    core = (p["subject"] + p["ending"]) if v.get("tight") else (p["subject"] + " " + p["ending"]).strip()
    return (p["prefix"] + " " + core).strip()


# --- TOOLS -----------------------------------------------------------------
def register_task(owner: int, subject: str, english: str = "", verb: str = "하다",
                  prefix: str = "", kind: str = "binary",
                  options: list[str] | None = None) -> dict:
    """TOOL: create a card for a specific child, built from parts."""
    cid = next(_cid)
    board[cid] = {
        "id": cid, "owner": int(owner),
        "prefix": prefix, "subject": subject, "verb": verb,
        "english": english, "kind": kind, "options": options or [],
        "status": "todo", "stars": None, "choice": None,
    }
    return {"ok": True, "tool": "register", "card": _view(board[cid])}


def start_task(task_id: int) -> dict:
    c = board.get(task_id)
    if not c:
        return {"ok": False, "error": f"no card {task_id}"}
    c["status"] = "doing"
    return {"ok": True, "tool": "start", "card": _view(c)}


def complete_task(task_id: int, choice: str | None = None) -> dict:
    c = board.get(task_id)
    if not c:
        return {"ok": False, "error": f"no card {task_id}"}
    c["status"] = "done"
    if choice:
        c["choice"] = choice
    _remember(c, "complete")
    return {"ok": True, "tool": "complete", "card": _view(c)}


def reverse_task(task_id: int) -> dict:
    """TOOL (parent assessment): send a card BACK one column.
    done -> doing -> todo. This is the 'examine / not really finished' action."""
    c = board.get(task_id)
    if not c:
        return {"ok": False, "error": f"no card {task_id}"}
    order = {"done": "doing", "doing": "todo", "todo": "todo"}
    c["status"] = order[c["status"]]
    _remember(c, "reverse")
    return {"ok": True, "tool": "reverse", "card": _view(c)}


def rate_task(task_id: int, stars: int) -> dict:
    c = board.get(task_id)
    if not c:
        return {"ok": False, "error": f"no card {task_id}"}
    c["stars"] = max(1, min(5, int(stars)))
    _remember(c, "rate")
    return {"ok": True, "tool": "rate", "card": _view(c)}


def predict_tasks(owner: int, period: str = "tomorrow") -> dict:
    """TOOL (read-only): per-child frequency x recency prediction, no ML."""
    today = date.today()
    scores: dict[str, float] = defaultdict(float)
    for h in history:
        if h["event"] != "complete" or h["owner"] != int(owner):
            continue
        recency = 0.85 ** (today - h["date"]).days
        liked = (h["stars"] or 3) / 3
        scores[h["subject"]] += recency * liked
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return {"ok": True, "tool": "predict", "period": period,
            "ranked": [{"subject": k, "score": round(v, 2)} for k, v in ranked]}


# --- Resolve a spoken name -> a card id, scoped to one child ----------------
def normalize(text: str) -> str:
    """Apply the house glossary so variant phrasing maps to a card subject."""
    for variant, canonical in GLOSSARY.items():
        if variant in text:
            text = text.replace(variant, canonical)
    return text


def resolve_id(name_or_id, owner: int) -> int | None:
    try:
        cid = int(name_or_id)
        return cid if cid in board else None
    except (TypeError, ValueError):
        pass
    text = normalize(str(name_or_id))
    cands = [c for c in board.values() if c["owner"] == int(owner)]
    for c in cands:                       # exact subject match
        if c["subject"] in text:
            return c["id"]
    for c in cands:                       # 2-char Korean prefix fallback
        if c["subject"][:2] and c["subject"][:2] in text:
            return c["id"]
    return None


# --- helpers / views -------------------------------------------------------
def _view(c: dict) -> dict:
    """Card enriched with composed display fields for the frontend + TTS."""
    return {**c, "parts": parts(c), "spoken": spoken(c)}


def _remember(c: dict, event: str):
    history.append({"subject": c["subject"], "owner": c["owner"], "event": event,
                    "stars": c["stars"], "date": date.today(),
                    "ts": datetime.now().isoformat(timespec="seconds")})


def snapshot(owner: int) -> dict:
    cards = [c for c in board.values() if c["owner"] == int(owner)]
    return {
        "user": users.get(int(owner)),
        "columns": {col: [_view(c) for c in cards if c["status"] == col]
                    for col in COLUMNS},
        "history_count": sum(1 for h in history if h["owner"] == int(owner)),
    }


def list_users() -> list[dict]:
    return list(users.values())


def _seed():
    # Two children of different ages -> age-appropriate starter cards.
    minjun = add_user("민준", 8)
    seoyeon = add_user("서연", 4)
    # 4-year-old: simple binary, recycling 하다 / 씻다 / 정리하다
    register_task(seoyeon["id"], "손", "Wash hands", verb="씻다")
    register_task(seoyeon["id"], "양치", "Brush teeth", verb="하다")
    register_task(seoyeon["id"], "장난감", "Tidy toys", verb="정리하다")
    # 8-year-old: includes a choice card composed from prefix + subject
    register_task(minjun["id"], "숙제", "Homework", verb="하다")
    register_task(minjun["id"], "책", "Read a book", verb="읽다")
    register_task(minjun["id"], "메뉴", "Pick dinner", verb="고르다", prefix="저녁",
                  kind="choice", options=["김밥 / Gimbap", "비빔밥 / Bibimbap", "카레 / Curry"])


_seed()
