# Nightshift Backend — Phase 1: The Observer

Nightshift is an AI Site Reliability Engineering (SRE) agent. **Phase 1 (The Observer)** provides the foundation: a high-performance, real-time log ingestion pipeline that accepts structured log streams over REST and immediately broadcasts them to connected clients (like the Angular frontend dashboard) via WebSockets.

---

## 📋 Architecture & Features

- **FastAPI & Python 3.12**: Modern async ASGI backend.
- **`POST /logs/ingest`**: Ingests JSON log payloads, validates schema via Pydantic, and returns `202 Accepted`.
- **`WebSocket /ws/logs`**: Non-blocking real-time broadcasting hub streaming ingested logs to all connected frontend clients.
- **`GET /health`**: Fast health probe returning `{"status": "ok"}`.
- **CORS Enabled**: Out-of-the-box support for the Angular dashboard running on `http://localhost:4200`.
- **Log Simulator (`scripts/simulate_logs.py`)**: Standalone generator producing realistic microservice logs (info, warn, error) at random intervals (2–5s).

---

## 🛠️ Project Structure

```
backend/
├── app/
│   ├── core/
│   │   └── config.py              # Configuration & CORS settings
│   ├── models/
│   │   └── log.py                 # Pydantic schemas (LogPayload, IngestResponse, HealthResponse)
│   ├── routes/
│   │   ├── health.py              # GET /health
│   │   ├── logs.py                # POST /logs/ingest
│   │   └── websocket.py           # WebSocket /ws/logs
│   ├── services/
│   │   └── connection_manager.py  # WebSocket connection manager & async broadcaster
│   └── main.py                    # FastAPI app factory & lifespan
├── scripts/
│   └── simulate_logs.py           # Standalone log generation simulator
├── tests/
│   ├── conftest.py                # Pytest fixtures
│   └── test_api.py                # API & WebSocket test suite
├── requirements.txt               # Pinned dependencies
└── README.md                      # Backend documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.12 installed on your machine.
- *Note for Windows*: If Python was recently installed, restart your terminal or refresh the PATH in PowerShell:
  ```powershell
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
  ```

### 2. Create and Activate Virtual Environment

> [!TIP]
> The virtual environment `backend/venv` is already pre-configured with all dependencies. You can activate it directly:

**Windows (PowerShell):**
```powershell
cd backend
.\venv\Scripts\activate
```

**Windows (Command Prompt):**
```cmd
cd backend
venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
cd backend
source venv/bin/activate
```


### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 🏃 Running the Application

### 1. Start the FastAPI Server

In your first terminal (with the virtual environment activated inside `backend/`):

```bash
uvicorn app.main:app --reload --port 8000
```

- **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **WebSocket Stream**: `ws://localhost:8000/ws/logs`

### 2. Run the Standalone Log Simulator

In a second terminal (with the virtual environment activated inside `backend/`):

```bash
python scripts/simulate_logs.py
```

The simulator will generate continuous fake log lines across various services (`auth-service`, `payment-gateway`, `order-processor`, `inventory-api`, `notification-worker`, `ingress-router`) with a mix of `info`, `warn`, and `error` severities every 2–5 seconds and POST them to `http://localhost:8000/logs/ingest`.

#### Simulator Options:

```bash
# Custom ingestion URL and interval
python scripts/simulate_logs.py --url http://localhost:8000/logs/ingest --min-delay 1.0 --max-delay 3.0

# Generate a specific batch of logs (e.g. 50 logs) and exit
python scripts/simulate_logs.py --count 50
```

### 3. Connect Frontend Dashboard

Start the Angular frontend from the `frontend/` directory:

```bash
cd ../frontend
npm start
# or: ng serve
```

Open [http://localhost:4200](http://localhost:4200) in your browser. The dashboard connects to `ws://localhost:8000/ws/logs` and renders live logs as they are generated.

---

## 🧪 Running Tests

To run the automated test suite verifying all REST endpoints and WebSocket broadcasting:

```bash
pytest tests/ -v
```

---

## 📡 API Reference

### Health Check
- **Endpoint**: `GET /health`
- **Response**: `200 OK`
```json
{
  "status": "ok"
}
```

### Log Ingestion
- **Endpoint**: `POST /logs/ingest`
- **Headers**: `Content-Type: application/json`
- **Request Body**:
```json
{
  "timestamp": "2026-08-23T14:30:00.000Z",
  "service": "payment-gateway",
  "level": "info",
  "message": "Payment intent pi_384910 confirmed ($49.99 USD)"
}
```
- **Response**: `202 Accepted`
```json
{
  "status": "accepted",
  "detail": "Log accepted for processing and broadcasting"
}
```

### WebSocket Log Stream
- **Endpoint**: `ws://localhost:8000/ws/logs`
- **Payload Shape**:
```json
{
  "timestamp": "2026-08-23T14:30:00.000Z",
  "service": "payment-gateway",
  "level": "info",
  "message": "Payment intent pi_384910 confirmed ($49.99 USD)"
}
```
