"""
app.py — thin web layer. Matches your NHS Policy Navigator shape:
serve a single-file frontend + a couple of JSON endpoints.

    python -m uvicorn app:app --reload     ->   http://localhost:8000

The frontend is just ONE MORE CHANNEL. A tapped button and a typed/spoken
sentence both POST to /act, which calls the same router.handle(). Swap the
brain (rules vs Gemini) with USE_GEMINI=1 and nothing here changes.
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


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/board")
def get_board():
    return board.snapshot()


@app.post("/act")
def act(u: Utterance):
    """The single entry point for every channel: route -> dispatch -> state."""
    out = router.handle(u.text)
    out["board"] = board.snapshot()
    return out


@app.post("/tap")
def tap(payload: dict):
    """Buttons skip the LLM and call a tool directly (fast, always-correct).
    Same dispatch target as /act — just a pre-resolved Action."""
    tool = payload.get("tool")
    tid = payload.get("task_id")
    fn = {
        "start": lambda: board.start_task(tid),
        "complete": lambda: board.complete_task(tid, choice=payload.get("choice")),
        "rate": lambda: board.rate_task(tid, payload.get("stars", 3)),
        "predict": board.predict_tasks,
    }.get(tool)
    result = fn() if fn else {"ok": False, "error": "unknown tool"}
    return {"result": result, "board": board.snapshot()}
