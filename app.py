"""
app.py — thin web layer (v2). Every endpoint is scoped to a child (`user`).

    python -m uvicorn app:app --reload   ->   http://localhost:8000
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import board
import router

app = FastAPI(title="together-todo")
app.mount("/static", StaticFiles(directory="static"), name="static")


class Utterance(BaseModel):
    text: str
    user: int


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/users")
def get_users():
    return board.list_users()


@app.get("/board")
def get_board(user: int):
    return board.snapshot(user)


@app.post("/act")
def act(u: Utterance):
    """Single entry point for every channel (type/voice), scoped to a child."""
    out = router.handle(u.text, u.user)
    out["board"] = board.snapshot(u.user)
    return out


@app.post("/tap")
def tap(payload: dict):
    """Buttons skip the LLM: a pre-resolved Action for one child's card."""
    tool, tid, user = payload.get("tool"), payload.get("task_id"), payload.get("user")
    fn = {
        "start": lambda: board.start_task(tid),
        "complete": lambda: board.complete_task(tid, choice=payload.get("choice")),
        "reverse": lambda: board.reverse_task(tid),
        "rate": lambda: board.rate_task(tid, payload.get("stars", 3)),
        "predict": lambda: board.predict_tasks(user),
    }.get(tool)
    result = fn() if fn else {"ok": False, "error": "unknown tool"}
    return {"result": result, "board": board.snapshot(user)}
