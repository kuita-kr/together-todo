# together-todo — working agreements

## Release / PR workflow
- **Before merging any PR into `main`, ensure `README.md` and every other relevant
  doc in the repo (e.g. `.env.example`, any `docs/`) reflect the changes in that PR.**
  Update them as part of the same PR — never merge code whose docs have gone stale.
- Standard ship sequence: update docs → commit → push → open PR → merge into `main`.
- Commit messages end with the `Co-Authored-By: Claude` trailer; PR bodies end with
  the Claude Code generation line.

## Project shape
- In-memory sandbox (no DB). `board.py` = state + tools; `router.py` = route→dispatch;
  `app.py` = FastAPI (`/act`, `/tap`, `/board`, user CRUD, parent `/bag*`/`/words`/
  `/notes`/`/settings`/`/parent/*`); `static/index.html` = single-file UI.
- Parent mode is PIN-gated (default `0000`); parent actions are plain REST endpoints,
  not routed through the LLM.

## Verify changes
- Backend: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -c "..."` (Windows console
  needs the UTF-8 env for Korean output).
- UI: `.claude/launch.json` runs the app on port 8012 for the preview panel; drive it
  with the preview MCP tools (screenshots can time out in the sandbox — prefer
  `preview_eval`/DOM checks).
