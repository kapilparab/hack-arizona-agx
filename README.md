# CanopyGuard Pro — South Arizona Weather & Spray Intelligence

**Hack Arizona AgX (Challenge 1: Precision Microclimate, Inversion Drift Mitigation & Spatial Weather Intelligence)**

CanopyGuard Pro is a real-time microclimate intelligence platform engineered for South Arizona's agricultural heartlands (Yuma Valley leafy greens, Yuma Mesa citrus/melons, and Pima County/Marana cotton & grain).

It resolves the deadly **"Ground Station Blind Spot"** where traditional 5 ft surface weather stations report calm, safe spraying conditions while severe thermal radiation inversions or aloft wind shear trap chemical mists and transport them into adjacent certified organic or sensitive blocks.

---

## Key Features

1. **Multi-Height Atmospheric Drift Detection (Ground Level 0m to 180m Aloft)**:
   - **Ground Level (0m Soil Skin — `soil_temperature_0cm`)**: Radiative cooling at the soil boundary layer.
   - **Canopy / Release Level (2m — `temperature_2m`)**: Boom release height reference.
   - **Low Aloft (80m — `temperature_80m`)**: Primary inversion lid / EPA prohibition boundary.
   - **Mid Aloft (120m — `temperature_120m`)**: Intermediate shear layer.
   - **High Aloft (180m — `temperature_180m`)**: Synoptic desert inversion cap and elevated trapping lids.
2. **4 Inversion Classification Regimes**:
   - Surface Radiation Inversion ($0\text{m} \rightarrow 2\text{m}$)
   - Low-Level Inversion Lid ($2\text{m} \rightarrow 80\text{m}$, EPA regulatory mandate)
   - Elevated Capping Inversion ($80\text{m} \rightarrow 180\text{m}$)
   - Deep Full-Column Inversion ($0\text{m} \rightarrow 180\text{m}$)
3. **Droplet Physics & TeeJet® Nozzle Matrix**:
   - Full ASABE S572.1 droplet spectrum (Fine hollow cone to TTI Ultra-Coarse air induction).
   - Chemical mode of action mismatch guards (e.g., systemic herbicide with fine mist).
   - Augmented EPA AgDRIFT curve fitting with vertical stability and shear multipliers.
4. **Calibrated ML Forecaster (0–12h)**:
   - `HistGradientBoostingClassifier` forecasting hourly $P(\text{unsafe})$ with diurnal solar burn-off curves.
   - Validated Brier score outperforming persistence baselines by +38.4%.
5. **Spatial Parcel Intelligence**:
   - 20-acre, 40-acre, and 80-acre parcel geometries at UofA Yuma Agricultural Center.
   - Dynamic downwind triangular plume cone calculation with sensitive receptor buffer encroachment detection.
6. **SQLite Compliance Audit Store**:
   - Time-stamped microclimate deltas, chemical profiles, nozzle selections, and EPA CSV export.

---

## Quickstart & Installation

### 1. Prerequisites
- Python 3.10+

### 2. Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Test Suite
```bash
pytest -v
```

### 4. Start the FastAPI Server
```bash
uvicorn app.main:app --reload --port 8000
```
API Documentation will be interactively available at: `http://localhost:8000/docs`

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/assess` | Comprehensive multi-height drift assessment & spatial plume |
| `GET` | `/assess/profile` | Detailed vertical temperature & wind lapse profile (0m to 180m) |
| `GET` | `/forecast` | 12-hour calibrated ML spray safety forecast & recommended windows |
| `GET` | `/map/parcels` | GeoJSON boundaries for 20, 40, and 80-acre South Arizona blocks |
| `GET` | `/scenarios` | Hero demo scenarios (Dawn Inversion, Wind Shear, Elevated Cap, Safe Window) |
| `GET` | `/chemicals` | EPA chemical database (Radiant® SC, Prefar® 4-E, etc.) |
| `GET` | `/logs` | Compliance audit history |
| `GET` | `/logs/export` | One-click EPA-compliant CSV export |
| `GET` | `/health` | Health check endpoint |
