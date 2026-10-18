# RaceForesight — agent instructions

## Git — commit automatically

After finishing a coherent piece of work in this repo, **commit without waiting for the user to ask**. Prefer several small atomic commits over one large dump when the change spans distinct concerns.

### Commit style
- Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, …
- Short subject focused on **why**; optional 1–2 sentence body.
- One concern per commit (e.g. model vs UI vs eval artifacts).

### Safety
- Never update git config.
- Never force-push `main`/`master`, never destructive resets, unless the user explicitly asks.
- Never skip hooks (`--no-verify`, etc.) unless explicitly asked.
- Do not commit secrets (`.env`, credentials, keys).
- Do not create empty commits.

### Push
- After creating commits on this project, **push to `origin`** unless the user said not to push.

### Windows / Git Bash
- **Always run git via Git Bash**, not PowerShell — `git` is often missing from the PowerShell PATH on this machine.
- Prefer: `"D:\Outils\Git\bin\bash.exe" -lc 'cd /d/Dev/RaceForesight && git …'` (install: `D:\Outils\Git`).
- Pass commit messages with `-m` / `-F` only — never open an editor.
- This repo’s **local** `core.editor` is `true` (no UI). Global may still be VS Code `--wait`; do not change global unless the user asks. If an editor still opens, force with `git -c core.editor=true commit …`.
- From a Cursor PowerShell tool call, quote carefully or write the message to a file and `git commit -F thatfile`.

## Product context (short)
- **Strategy** = per-driver tyre / pit optimisation (race times under a plan).
- **Classification** = finishing-order ranker (grid + form + pace), not a re-sort of Strategy times.
- **Race time** = dedicated duration regressor (`session_result.duration`), not Classification order and not Strategy tyre times.
- Backend: FastAPI + XGBoost / XGBRanker + OpenF1. Frontend: Next.js.
- Model `.joblib` files are gitignored; JSON metrics/meta under `backend/app/models/artifacts/` may be committed. Retrain with `scripts/train_model.py`, `scripts/train_ranker.py`, and `scripts/train_race_time.py`.
