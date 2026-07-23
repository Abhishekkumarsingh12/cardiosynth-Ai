# CardioSynth AI

Secure, production-style scaffold for an ECG analysis web platform: **React + Vite + Tailwind** frontend, **FastAPI** backend, **PostgreSQL** (optional) or **SQLite** default, **JWT** authentication, and **real preprocessing + classifier** with **optional DDPM / parametric** synthetic ECG and rule-based assistants.

## Important

- **Not a medical device** — outputs are for research/education only, not a diagnosis.
- **Classifier** — with TensorFlow + `arrhythmia_model.h5`, uploads use real Keras inference. If the model cannot load and `ENABLE_MOCK_INFERENCE=false` (default), the API returns **HTTP 503** (no silent fake success).
- **Synthetic** — `POST /api/ecg/generate-synthetic/{id}` tries **DDPM** when `synthetic_generator_model.h5` loads; otherwise uses a **parametric** synthesizer (clearly labeled in response metadata), unless `SYNTHETIC_REQUIRE_DDPM=true` (then missing DDPM → **503**). There is **no** random-noise “success” pretend path.
- **No per-request training** — training scripts are offline only; the API loads frozen weights.

## Folder structure

```
project/
├── README.md
├── .env.example
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, /api router
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/                 # SQLAlchemy: users, ecg_*, assistant_logs
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── core/security.py        # JWT, password hashing
│   │   ├── services/               # auth, ECG pipeline, assistant (mock where marked)
│   │   ├── datasets/               # offline: PhysioNet downloaders + prepare_pipeline
│   │   ├── utils/csv_ecg.py        # CSV validation + first numeric column
│   │   └── api/
│   │       ├── deps.py             # get_current_user
│   │       └── routes/             # auth, ecg, assistant, dashboard
│   ├── datasets/                   # raw + processed data (gitignored when populated)
│   ├── ml_models/                  # exported .h5 from offline training (gitignored)
│   ├── setup_dataset.py            # offline download + NPZ build
│   ├── training/                   # offline train_*.py scripts
│   └── uploads/                    # user CSV uploads (gitignored)
└── frontend/
    ├── package.json
    ├── vite.config.js              # dev proxy → :8000
    ├── tailwind.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api/client.js
        ├── context/AuthContext.jsx
        ├── pages/                  # Login, Signup, Dashboard
        └── components/             # layout, ECG chart (Recharts)
```

## Top-level API (no `/api` prefix)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | JSON welcome (`version`, `build_id`, links to docs/health/debug) |
| GET | `/health` | Liveness JSON |
| GET | `/debug/model` | Classifier path, `model_loaded`, `mock_enabled` |
| GET | `/build-info` | Build id, route summary, classifier snapshot |
| GET | `/docs` | Swagger UI |

## API routes (under `/api`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/signup` | Register + JWT |
| POST | `/api/auth/login` | Login + JWT |
| GET | `/api/auth/me` | Current user (Bearer) |
| POST | `/api/auth/forgot-password` | Body: `{ "email" }` — always generic ack; dev: token logged server-side |
| POST | `/api/auth/reset-password` | Body: `{ "email", "token", "new_password" }` — invalidates token after success |
| POST | `/api/ecg/upload` | CSV upload → preprocess → classifier (503 if model unavailable) |
| GET | `/api/ecg/history` | List analyses |
| GET | `/api/ecg/analysis/{id}` | Detail + chart series |
| POST | `/api/ecg/generate-synthetic/{analysisId}` | JSON body optional: `target_class`, `num_samples`, `noise_scale`, `diversity_seed`, `num_beats`. Returns previews, metadata, quality; saves CSV |
| GET | `/api/ecg/synthetic-file/{syntheticRunId}` | Download generated CSV (owner-only) |
| GET | `/api/reports` | Report index (same rows as analyses + status) |
| GET | `/api/reports/{id}` | Report detail + chart + synthetic runs + enriched `risk_*` on `prediction_result` |
| GET | `/api/reports/{id}/export` | JSON export |
| GET | `/api/reports/{id}/export-pdf` | PDF report (waveform + saliency plot, risk, guidance text, disclaimer) |
| GET | `/api/ecg/explain/{analysisId}` | Classifier-window saliency (`importance`, `importance_normalized`, `window_waveform`) |
| DELETE | `/api/reports/{id}` | Delete analysis, upload file, synthetic artifacts on disk |
| DELETE | `/api/uploads/{id}` | Delete upload (and linked analysis/synthetics if present) |
| POST | `/api/assistant/chat` | Rule-based assistant + log |
| POST | `/api/assistant/report-guidance` | Report-based guidance (disclaimer in body) |
| GET | `/api/dashboard/summary` | Counts + last label |
| GET | `/api/dashboard/recent-analyses` | Table data |

## Run instructions

### Stop old backend processes (avoid stale uvicorn on port 8000)

An **old** uvicorn can keep **:8000** and answer `/health` while **missing newer routes** (e.g. `/debug/model` → 404). Always free the port or use a new port before starting the current code.

**macOS / Linux — find what is using 8000:**

```bash
lsof -iTCP:8000 -sTCP:LISTEN
```

**Stop those PIDs** (replace `<pid>`):

```bash
kill <pid>
# if it respawns or ignores:
kill -9 <pid>
```

**Optional — kill all uvicorn processes (aggressive):**

```bash
pkill -f "uvicorn app.main:app"
```

**Verify the port is free:**

```bash
lsof -iTCP:8000 -sTCP:LISTEN   # should print nothing
```

**Confirm you are on the new build after start:**

```bash
curl -s http://127.0.0.1:8000/ | python3 -m json.tool
curl -s http://127.0.0.1:8000/debug/model | python3 -m json.tool
```

Startup logs also print a **banner** with `build_id`, `version`, **PID**, classifier `model_loaded`, and these URLs.

### 1. Backend (from scratch)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Optional: improve image/PDF ingestion (OCR + waveform extraction)
pip install -r requirements-ingestion.txt
# Classifier inference (required for real predictions, default strict 503 if missing):
pip install "tensorflow>=2.13,<2.16"   # or see backend/requirements-tensorflow.txt
cp ../.env.example .env      # optional: SECRET_KEY, DATABASE_URL, API_ADVERTISED_PORT
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Set **`API_ADVERTISED_HOST`** / **`API_ADVERTISED_PORT`** in `backend/.env` to match `--host` / `--port` so `/` and logs show correct links.

If `DATABASE_URL` is unset, SQLite is used at `backend/cardiosynth.db`.

### 2. Frontend (from scratch)

```bash
cd frontend
npm install
npm run dev
```

### URLs after startup

| What | URL |
|------|-----|
| JSON root (confirms build) | http://127.0.0.1:8000/ |
| Classifier debug | http://127.0.0.1:8000/debug/model |
| Build / routes summary | http://127.0.0.1:8000/build-info |
| Swagger | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/health |
| Web UI (Vite) | http://127.0.0.1:5173 (or the port Vite prints) |

Use **`http://` not `https://`**. The Vite dev server proxies `/api` to the backend (default `http://127.0.0.1:8000` in `vite.config.js`).

### 3. Production build (frontend)

```bash
cd frontend
npm run build
npm run preview   # or serve dist/ behind nginx/CDN
```

Point the SPA at your API origin and configure CORS on the backend for that origin.

## CSV format

- `.csv` only for this version.
- The parser prefers columns named **ecg** / **signal** / **lead_ii**, then the first non-time numeric column.
- Example:

```csv
time,ecg
0,0.1
1,0.15
2,0.12
```

## Replacing mock AI modules

- `app/services/ecg_preprocessing.py` — real denoise / resample / peak detection.
- `app/services/ecg_prediction.py` — TensorFlow classifier path + strict 503 when unavailable (unless `ENABLE_MOCK_INFERENCE=true`).
- `app/services/synthetic_ecg.py` — orchestrates **DDPM** (`synthetic_ddpm/`) and **parametric** fallback; metadata `generation_backend` is the source of truth.
- `app/services/assistant_service.py` — rules today; optional LLM with clinical guardrails later.

## Dataset auto-download & offline training (section 16)

**Rule:** dataset downloads and model training **never** run during HTTP requests or user uploads. The API stays on the path: upload → preprocess → mock predict → respond. Heavy work is **manual / admin-only**.

### Layout

| Path | Purpose |
|------|---------|
| `backend/datasets/mit_bih/mitdb/` | Raw MIT-BIH (`mitdb`) files from PhysioNet (via `wfdb`) |
| `backend/datasets/processed/mit_bih_beats.npz` | Segmented, z-scored beat windows + labels |
| `backend/ml_models/arrhythmia_model.h5` | Trained classifier (Keras) |
| `backend/ml_models/synthetic_generator_model.h5` | Trained DDPM ε-model (optional; see `training/train_synthetic_ddpm.py`) |
| `backend/app/datasets/` | Reusable downloaders + `prepare_pipeline.py` |
| `backend/setup_dataset.py` | Download (if missing) + build NPZ |
| `backend/training/train_classifier.py` | Offline classifier training |
| `backend/training/train_synthetic_ddpm.py` | Offline DDPM training (writes `synthetic_generator_model.h5`) |

### Commands

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt

# 1) Download MIT-BIH when absent, then segment / normalize into NPZ
python setup_dataset.py

# Quick test on a subset of records:
# python setup_dataset.py --max-records 5

# 2) Install training stack (TensorFlow is large; not required for the API alone)
pip install -r requirements-training.txt

# 3) Train models (writes .h5 under ml_models/)
python training/train_classifier.py
python training/train_synthetic_ddpm.py
```

**Extensibility:** add another PhysioNet DB by subclassing `app.datasets.base.BasePhysioNetDataset`, registering it in `app.datasets.registry.REGISTRY`, and adding a preparation function alongside `build_mit_bih_processed_npz`.

**Classifier inference (API):** upload runs `predict_ecg()` → Butterworth bandpass → 187-sample window → z-score → Keras `arrhythmia_model.h5`. Default **`ENABLE_MOCK_INFERENCE=false`**: if weights or TensorFlow are missing, **HTTP 503** (no fake `model_unavailable` body). A **dummy** `.h5` is written only when **`ENABLE_MOCK_INFERENCE=true`** and bootstrap training fails. On startup, if weights are missing and TensorFlow is installed, bootstrap may run `training/train_classifier.py` once (`ECG_CLASSIFIER_BOOTSTRAP_QUICK=1` by default). Set `SKIP_CLASSIFIER_AUTO_BOOTSTRAP=true` to skip. Optional `ECG_AUTO_PREPARE_DATASET=true` runs `setup_dataset.py` when NPZ is missing. Weights: `backend/ml_models/arrhythmia_model.h5` or `ECG_CLASSIFIER_MODEL_PATH`. Input shape `(batch, 187, 1)` float32.

**Export / train:** run `python setup_dataset.py` then `python training/train_classifier.py` to produce a compatible `.h5`.

**Synthetic ECG:** `POST /api/ecg/generate-synthetic/{analysisId}` tries conditional 1D DDPM (`app/services/synthetic_ddpm/`) when weights load. Weights: `backend/ml_models/synthetic_generator_model.h5` or `ECG_DDPM_MODEL_PATH`. Align `ECG_DDPM_NUM_TIMESTEPS`, `ECG_DDPM_SCHEDULE`, and `ECG_DDPM_SIGNAL_LENGTH` with training. Offline train:

```bash
cd backend
source .venv/bin/activate
python training/train_synthetic_ddpm.py
```

Generated CSVs live under `uploads/synthetic/{user_id}/`; DB row metadata is in `synthetic_ecg.mock_metadata` (legacy column name) and includes `generation_backend`: `ddpm_conditional` or `procedural_parametric`. Set **`SYNTHETIC_REQUIRE_DDPM=true`** to forbid procedural output (missing/broken DDPM → HTTP **503**). Set **`SYNTHETIC_PROCEDURAL_ENABLED=false`** to disable parametric fallback entirely when DDPM is unavailable.

**Report storage:** Each upload creates one `ecg_uploads` row and one `ecg_analysis` row (1:1). CSV bytes are on disk at `ecg_uploads.stored_path`. Deleting a report (`DELETE /api/reports/{id}`) removes the analysis row, upload row, upload file, and any synthetic CSV paths recorded for that analysis.

**Quick tests (with JWT from `/api/auth/login`):**

1. **Synthetic:** `POST /api/ecg/generate-synthetic/1` with body `{"num_samples":360,"target_class":"N","noise_scale":0.05}`. Expect JSON with `preview_reference`, `preview_synthetic`, `metadata.generation_backend`. Then `GET /api/ecg/synthetic-file/{run.id}` for CSV.
2. **Delete:** `DELETE /api/reports/1` — then `GET /api/dashboard/summary` should show fewer analyses; Dashboard auto-refreshes when the UI dispatches `cardiosynth-data-changed` or the tab regains visibility.
3. **Dashboard:** After delete, open Dashboard — counts and “Last rhythm” should reflect remaining rows or **N/A** when empty.

---

© CardioSynth AI demo scaffold — use at your own risk for research and education.
