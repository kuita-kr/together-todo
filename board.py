"""
board.py — the "world" the agent acts on.

This is the part that makes a TOOL-CALLING agent different from a RAG agent.
In your NHS Policy Navigator the tools were READ-ONLY (fetch chunks, nothing
changes). Here the tools have SIDE EFFECTS: they create cards and move them
between columns. The router decides *which* tool; this file is *what the tools
actually do*.

State is just an in-memory dict (resets when the server restarts). That is
deliberate for a learning sandbox — swap it for MongoDB later and nothing else
in the architecture has to change.
"""

from __future__ import annotations
from datetime import datetime, date
from collections import defaultdict
import itertools

# --- The board -------------------------------------------------------------
# Columns mirror the Korean Kanban you described:
#   todo  = 할 일      doing = 하는 중      done = 끝!
COLUMNS = ("todo", "doing", "done")

# A card carries BOTH languages so the same object can be shown on screen and
# read aloud by TTS. `kind` decides what UI/interaction a card gets.
#   binary   -> yes/no tap (e.g. 손 씻기 / Wash hands)
#   choice   -> pick one of `options` (e.g. 저녁 메뉴 고르기 / Pick dinner)
_id_counter = itertools.count(1)

board: dict[int, dict] = {}

# History log = the agent's MEMORY. Every completion/rating is appended here,
# which is what lets `predict_tasks` find patterns later. Same idea as logging
# every query to MongoDB in your NHS app, just for actions instead of queries.
history: list[dict] = []


def _seed():
    """A few starter cards so the board isn't empty in a demo."""
    register_task("손 씻기", "Wash hands", kind="binary")
    register_task("숙제하기", "Do homework", kind="binary")
    register_task("저녁 메뉴 고르기", "Pick dinner", kind="choice",
                  options=["김밥 / Gimbap", "비빔밥 / Bibimbap", "카레 / Curry"])


# --- The five TOOLS --------------------------------------------------------
# Each function is a "tool" the router can call. Notice they all return a small
# dict describing what happened — that result is what you'd narrate back to the
# child via TTS ("잘했어요! 손 씻기 끝!").

def register_task(korean: str, english: str = "", kind: str = "binary",
                  options: list[str] | None = None) -> dict:
    """TOOL: create a new card in the `todo` column."""
    cid = next(_id_counter)
    board[cid] = {
        "id": cid,
        "korean": korean,
        "english": english,
        "kind": kind,
        "options": options or [],
        "status": "todo",
        "stars": None,
        "choice": None,
    }
    return {"ok": True, "tool": "register", "card": board[cid]}


def start_task(task_id: int) -> dict:
    """TOOL: move a card todo -> doing (하는 중)."""
    card = _find(task_id)
    if not card:
        return {"ok": False, "error": f"no card {task_id}"}
    card["status"] = "doing"
    return {"ok": True, "tool": "start", "card": card}


def complete_task(task_id: int, choice: str | None = None) -> dict:
    """TOOL: move a card -> done (끝!). For choice cards, records the pick."""
    card = _find(task_id)
    if not card:
        return {"ok": False, "error": f"no card {task_id}"}
    card["status"] = "done"
    if choice:
        card["choice"] = choice
    _remember(card, event="complete")
    return {"ok": True, "tool": "complete", "card": card}


def rate_task(task_id: int, stars: int) -> dict:
    """TOOL: record a 1-5 star rating (e.g. 'want it again tomorrow?')."""
    card = _find(task_id)
    if not card:
        return {"ok": False, "error": f"no card {task_id}"}
    card["stars"] = max(1, min(5, int(stars)))
    _remember(card, event="rate")
    return {"ok": True, "tool": "rate", "card": card}


def predict_tasks(period: str = "tomorrow") -> dict:
    """
    TOOL (read-only): predict likely tasks using frequency x recency — NO ML.

    For each task name we score:  occurrences  weighted so that more recent
    days count more. Highest scores = most likely to recur. This is the
    lightweight "learns from the past" behaviour, the action-world cousin of
    your NHS app's 'use the best-scoring strategy after 5 runs' rule.
    """
    today = date.today()
    scores: dict[str, float] = defaultdict(float)
    for h in history:
        if h["event"] != "complete":
            continue
        age_days = (today - h["date"]).days
        recency_weight = 0.85 ** age_days          # decays ~15% per day
        liked_bonus = (h["stars"] or 3) / 3         # liked tasks score higher
        scores[h["korean"]] += recency_weight * liked_bonus
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "ok": True,
        "tool": "predict",
        "period": period,
        "ranked": [{"korean": k, "score": round(v, 2)} for k, v in ranked],
    }


# --- helpers ---------------------------------------------------------------
def _find(task_id) -> dict | None:
    try:
        return board.get(int(task_id))
    except (TypeError, ValueError):
        # allow matching by Korean name too, since a child's utterance gives a
        # name ("청소 다 했어") not an id. The router resolves name -> id.
        for c in board.values():
            if c["korean"] == task_id:
                return c
    return None


def _remember(card: dict, event: str):
    history.append({
        "korean": card["korean"],
        "event": event,
        "stars": card["stars"],
        "date": date.today(),
        "ts": datetime.now().isoformat(timespec="seconds"),
    })


def resolve_id(name_or_id) -> int | None:
    """Map a Korean task name OR an id to a card id (router needs this)."""
    c = _find(name_or_id)
    return c["id"] if c else None


def snapshot() -> dict:
    """Everything the frontend needs to render the board."""
    return {
        "columns": {col: [c for c in board.values() if c["status"] == col]
                    for col in COLUMNS},
        "history_count": len(history),
    }


_seed()
