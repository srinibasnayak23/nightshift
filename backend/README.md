# Nightshift Backend — Phase 2: The Thinker

Nightshift is an AI Site Reliability Engineering (SRE) agent. 
- **Phase 1 (The Observer)**: High-performance log ingestion & real-time WebSocket broadcasting.
- **Phase 2 (The Thinker)**: LangGraph-based incident reasoning pipeline that pre-filters log anomalies, analyzes error signatures, fetches suspect git diffs from GitHub, and correlates them to generate an automated root-cause hypothesis with numeric confidence (0.0–1.0), streaming intermediate thoughts live over `/ws/agent-thoughts`.

---

## 📋 Architecture & Pipeline Flow

```
[ POST /logs/ingest ]
       │
       ├───► [ /ws/logs ] (Raw log stream for frontend dashboard)
       │
       └───► [ LangGraph Incident Pipeline (Async Background Task) ]
                   │
                   ▼
             [ filter_node ] ─── (is_anomaly == False) ───► [ END ] (Cost gate: non-LLM)
                   │
             (is_anomaly == True)
                   ▼
            [ summarize_node ] ─── (LLM Error Analysis: type, service, component)
                   │
                   ▼
           [ fetch_diff_node ] ─── (Tool: GitHub REST API + Local Git Fallback)
                   │
                   ▼
           [ correlate_node ] ─── (LLM Root-Cause Hypothesis & Strict Confidence 0.0-1.0)
                   │
                   ▼
                [ END ]
                   │
                   ▼
       [ /ws/agent-thoughts ] (Real-time stream for Thinking Terminal)
```

---

## 🛠️ Project Structure

```
backend/
├── app/
│   ├── agent/
│   │   ├── nodes/
│   │   │   ├── filter_node.py       # Non-LLM rule-based cost gate
│   │   │   ├── summarize_node.py    # LLM error diagnostics & structured summary
│   │   │   ├── fetch_diff_node.py   # GitHub diff fetching tool
│   │   │   └── correlate_node.py    # LLM root-cause hypothesis & confidence
│   │   ├── tools/
│   │   │   └── github_diff.py       # GitHub REST API client + local git fallback
│   │   ├── graph.py                 # LangGraph StateGraph workflow & runner
│   │   ├── llm.py                   # Swappable LLM provider (Claude, Gemini, Mock)
│   │   └── state.py                 # IncidentState TypedDict & Pydantic output models
│   ├── core/
│   │   └── config.py                # Environment configurations & CORS
│   ├── models/
│   │   └── log.py                   # Pydantic models (LogPayload, IngestResponse, HealthResponse)
│   ├── routes/
│   │   ├── health.py                # GET /health
│   │   ├── logs.py                  # POST /logs/ingest
│   │   └── websocket.py             # WebSockets (/ws/logs & /ws/agent-thoughts)
│   ├── services/
│   │   ├── connection_manager.py    # Raw log connection manager
│   │   └── thought_manager.py       # Agent thoughts WebSocket broadcaster
│   └── main.py                      # FastAPI application entrypoint
├── scripts/
│   └── simulate_logs.py             # Standalone continuous log generator
├── tests/
│   ├── conftest.py                  # Test fixtures
│   ├── test_api.py                  # REST & Phase 1 WebSocket tests
│   └── test_agent_graph.py          # Phase 2 LangGraph & thoughts stream tests
├── requirements.txt                 # Pinned dependencies
└── README.md                        # Documentation
```

---

## ⚙️ Environment Configuration

Create a `.env` file in `backend/` or configure environment variables:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | auto-detected | `anthropic`, `gemini`, or `mock` (defaults to `mock` if no keys set) |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key (for Claude 3.5 / 3.7 Sonnet) |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Claude model name |
| `GEMINI_API_KEY` | `""` | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name |
| `GITHUB_TOKEN` | `""` | GitHub Personal Access Token (for fetching commit diffs) |
| `GITHUB_REPO` | `srinibasnayak23/nightshift` | Target repository (`owner/repo`) |
| `GITHUB_COMMITS_LIMIT`| `5` | Number of recent commits to inspect |

> [!TIP]
> If no `ANTHROPIC_API_KEY` or `GEMINI_API_KEY` is provided, Nightshift automatically uses an intelligent deterministic **Mock LLM Provider** and local git history so all tests and workflows run offline without spending tokens!

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.12 installed on your machine.
- *Note for Windows*: If Python was recently installed, refresh the PATH in PowerShell:
  ```powershell
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
  ```

### 2. Activate Virtual Environment & Install Dependencies

```powershell
cd backend
.\venv\Scripts\activate
pip install -r requirements.txt
```

---

## 🏃 Running the Application

### 1. Start the FastAPI Server

In Terminal 1:
```powershell
cd backend
.\venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

- **Interactive API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **Raw Log Stream**: `ws://localhost:8000/ws/logs`
- **Agent Thinking Stream**: `ws://localhost:8000/ws/agent-thoughts`

### 2. Run the Standalone Log Simulator

In Terminal 2:
```powershell
cd backend
.\venv\Scripts\activate
python scripts/simulate_logs.py
```

---

## 🧪 Running Tests

To run the full test suite (16 automated tests covering Phase 1 ingestion, WebSocket broadcasting, LangGraph routing, structured LLM outputs, and thoughts streaming):

```powershell
pytest tests/ -v
```

---

## 📡 WebSocket API Reference

### 1. Raw Log Stream (`ws://localhost:8000/ws/logs`)
Broadcasts every ingested log to connected dashboard tables.
```json
{
  "timestamp": "2026-08-23T14:30:00.000Z",
  "service": "payment-gateway",
  "level": "error",
  "message": "Database deadlock encountered during transaction #84102"
}
```

### 2. Agent Thinking Terminal Stream (`ws://localhost:8000/ws/agent-thoughts`)
Streams live step-by-step reasoning from the LangGraph incident pipeline:
```json
{
  "timestamp": "2026-08-23T14:30:01.120Z",
  "node": "correlate_node",
  "status": "completed",
  "thought": "Hypothesis generated (Confidence: 88.0%): The incident was triggered by commit 7f2a18b...",
  "confidence": 0.88,
  "state": {
    "hypothesis": "The incident was triggered by commit 7f2a18b altering database transaction boundaries...",
    "confidence": 0.88
  }
}
```
