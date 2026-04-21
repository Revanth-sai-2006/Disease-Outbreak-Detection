# Early Disease Outbreak Detection Dashboard

A production-ready disease surveillance application that combines data ingestion, outbreak prediction, risk outlook generation, and a modern web dashboard for monitoring and decision support.

## What Has Been Built

This project now includes:

- A complete outbreak prediction pipeline.
- A Flask-based dashboard server.
- A cinematic/futuristic dashboard UI with glassmorphism styling.
- City-wise report generation from the UI.
- PHC alert automation controls (manual and automatic dispatch modes).
- Persistent dispatch logging for PHC alerts.
- GitHub-ready project structure with modular frontend assets.

## Core Features

### 1. Data Pipeline and Forecasting

- Reads surveillance data from configured sources.
- Performs feature engineering (lags, rolling windows, and signal features).
- Trains/uses outbreak model artifacts.
- Generates:
  - `outputs/pipeline_summary.json`
  - `outputs/region_outlook.json`
  - `outputs/alerts.csv`
  - `outputs/data_source_status.json`

### 2. Interactive Dashboard

- Live dashboard served at `http://127.0.0.1:5050`.
- KPI cards for surveillance metrics.
- Region-wise risk table with severity, trend, and disease family.
- City/region detail panel with recent detection context.
- Auto-refresh cycle for updated outputs.

### 3. City Search and Runtime Region Reports

- User can search any city from dashboard.
- Server generates city-specific runtime config files in `outputs/`.
- Pipeline reruns for selected city and returns city-specific report payload.

### 4. PHC Alert Dispatch (New)

- New dashboard section: **PHC Alert Automation**.
- Manual dispatch button: **Send PHC Alert Now**.
- Auto-dispatch toggle: sends alerts automatically on new outlook cycles.
- Server endpoint writes dispatch log:
  - `outputs/phc_alert_dispatch_log.json`
- Alert trigger logic dispatches for:
  - `alert == true`, or
  - severity in `high/critical`, or
  - outbreak probability >= 0.8

### 5. Theme and UI Experience

- Nebula (default) and Lumen theme modes.
- Theme preference persisted in browser storage.
- Modular frontend:
  - `outputs/index.html`
  - `outputs/styles.css`
  - `outputs/app.js`

## Backend API Endpoints

### Dashboard and Reports

- `GET /`
  - Serves dashboard UI.
- `GET /api/dashboard`
  - Returns summary, outlook, and source status.
- `GET /api/city-report?city=<name>`
  - Generates and returns city-specific report payload.

### PHC Alerts

- `POST /api/phc-alert-dispatch`
  - Dispatches PHC alerts.
  - Body:
    ```json
    {
      "mode": "manual"
    }
    ```
  - `mode` supports `manual` and `automatic`.
- `GET /api/phc-alert-dispatch`
  - Returns latest PHC dispatch log/status.

## Tech Stack

### Language and Runtime

- Python 3.x

### Backend

- Flask
- PyYAML
- Requests

### Data and ML

- Pandas
- NumPy
- Scikit-learn
- Joblib

### Visualization and Analysis

- Matplotlib
- Seaborn
- Jupyter notebooks (`notebooks/analysis.ipynb`)

### Testing

- Pytest

### Frontend

- HTML5
- CSS3 (custom design system + theme variables)
- Vanilla JavaScript (modular app logic)

## Project Structure

```text
AIDDE/
  config.yaml
  dashboard_server.py
  run_pipeline.py
  run_custom_regions.py
  requirements.txt
  src/outbreak_detection/
    data.py
    features.py
    modeling.py
    alerts.py
    outlook.py
    pipeline.py
    utils.py
    web_data.py
  outputs/
    index.html
    styles.css
    app.js
    pipeline_summary.json
    region_outlook.json
    alerts.csv
    data_source_status.json
    phc_alert_dispatch_log.json
  tests/
    test_alerts.py
    test_features.py
```

## How to Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run pipeline (optional first step)

```bash
python run_pipeline.py
```

### 3. Start dashboard server

```bash
python dashboard_server.py
```

### 4. Open dashboard

- Visit: `http://127.0.0.1:5050`

## PHC Contact Configuration (Optional)

If you want region-specific PHC contact details, add this section to `config.yaml`:

```yaml
notifications:
  phc_contacts:
    varanasi:
      phc_name: Varanasi Urban PHC
      channel: email
      destination: varanasi.phc@gov.in
```

If not provided, default contacts are generated in the format:

- `<region-slug>@local-phc.gov.in`

## Notes

- Current PHC dispatch is implemented as structured dispatch logging for operational workflow simulation.
- The architecture is ready to integrate real channels (SMTP, SMS gateways, WhatsApp API, webhook adapters) in the same dispatch flow.

## Deploy on Render

This repo is now Render-ready with:

- `render.yaml` (Blueprint service config)
- `runtime.txt` (Python runtime)
- `gunicorn` in requirements
- environment-based server port binding

### Option 1: One-time setup from Render Dashboard

1. Login to Render.
2. Click **New +** -> **Web Service**.
3. Connect your GitHub repo:
  - `Revanth-sai-2006/Disease-Outbreak-Detection`
4. Render should detect settings from `render.yaml`.
5. Click **Create Web Service**.

### Option 2: Manual service settings

If you choose manual setup instead of Blueprint:

- **Environment**: Python
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn dashboard_server:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`

After successful deploy, Render will provide a public URL for the dashboard.
