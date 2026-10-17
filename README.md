# RaceForesight

Predictive F1 race strategy — estimate lap times with XGBoost, simulate pit windows, and recommend the optimal tyre strategy for the full grid.

**Default target:** United States Grand Prix 2026 (Circuit of the Americas, Austin).

## Stack

- **Backend:** Python, FastAPI, pandas, XGBoost
- **Data:** [OpenF1](https://openf1.org/) (primary), extensible to other sources
- **Frontend:** Next.js, TypeScript, Tailwind CSS

## Quick start

### Backend

```bash
cd backend
py -3.12 -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Train the lap-time model (first run / refresh):

```bash
python scripts/train_model.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/races` | Available meetings (default = next GP) |
| `GET /api/races/{meeting_key}/strategy` | Optimal strategies for all 20 drivers |
| `GET /api/races/{meeting_key}/strategy/{driver_number}` | Strategy detail for one driver |

## License

Educational / personal project. Formula 1 data via OpenF1 (community API, not affiliated with F1/FIA/FOM).
