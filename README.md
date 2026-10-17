# RaceForesight

Predictive F1 race strategy — estimate lap times with XGBoost, simulate pit windows, and recommend the optimal tyre strategy for the full grid.

**Default target:** United States Grand Prix 2026 (Circuit of the Americas / Austin).

## Stack

- **Backend:** Python 3.12, FastAPI, pandas, XGBoost
- **Data:** [OpenF1](https://openf1.org/) (primary; other sources can be plugged in later)
- **Frontend:** Next.js 15, TypeScript, Tailwind CSS

## Quick start

### 1. Backend

```bash
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

Train the lap-time model (downloads/caches OpenF1 race data — be polite with rate limits):

```bash
python scripts/train_model.py --years 2024,2025 --max-sessions 15
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

Optional: copy `frontend/.env.local.example` to `frontend/.env.local` to point at another API URL.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check + model readiness |
| `GET /api/races` | Meetings (flag `is_default` = next GP) |
| `GET /api/races/{meeting_key}/strategy` | Optimal strategies for up to 20 drivers |
| `GET /api/races/{meeting_key}/strategy/{driver_number}` | Alternatives + degradation curve |

Use `meeting_key=0` to resolve the default (next) race.

## How it works

1. Ingest historical race laps / stints / pits from OpenF1
2. Train an XGBoost model on circuit-relative lap-time residuals
3. Enumerate legal dry 1-stop and 2-stop compound windows
4. Pick the strategy with the lowest predicted race time per driver

## Phase 2 (planned)

Predicted finishing order for the next GP (classification first, estimated times second).

## License

Educational / personal project. Formula 1 data via OpenF1 (community API, not affiliated with F1 / FIA / FOM).
