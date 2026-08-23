# Nightshift Backend — Phase 3: The Actor

Nightshift is an AI Site Reliability Engineering (SRE) agent. 
- **Phase 1 (The Observer)**: High-performance log ingestion & real-time WebSocket broadcasting (`/ws/logs`).
- **Phase 2 (The Thinker)**: LangGraph-based incident reasoning pipeline that pre-filters log anomalies, analyzes error signatures, fetches suspect git diffs from GitHub (`srinibasnayak23/BloHelp`), and correlates them to generate an automated root-cause hypothesis with numeric confidence (0.0–1.0), streaming intermediate thoughts live over `/ws/agent-thoughts`.
- **Phase 3 (The Actor)**: Human-in-the-loop escalation, checkpointed approval gate, and automated remediation execution layer via Render API (`restart` vs `rollback`), broadcasting pending approvals over `/ws/pending-approvals`.

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
         ┌─────────┴─────────┐
         │ (confidence >= 0.7)│ (confidence < 0.7)
         ▼                   ▼
  [ escalate_node ]    [ low_confidence_node ] ───► [ END ]
         │ (Broadcasts to /ws/pending-approvals)
         ▼
[ await_human_node ] (LangGraph Checkpoint Interruption)
         │
         ├─── (POST /incidents/{id}/decision -> "rejected") ───► [ END ] (Logged)
         │
         └─── (POST /incidents/{id}/decision -> "approved")
                   │
                   ▼
            [ execute_node ] ─── (Tool: Render API restart / rollback)
                   │
                   ▼
                [ END ]
```

---

## 🛡️ Safety & Human-in-the-Loop Guardrails

1. **Explicit Human Approval Invariant**: `execute_node` enforces a runtime guardrail (`human_decision == "approved"`). No automated path exists to execute remediation without human authorization.
2. **Structured Audit Trail**: Every execution attempt logs a structured record containing timestamp, incident ID, target service, suspect commit, decision, and result.
3. **Resilient Failure Handling**: Render API connection errors and non-2xx responses are captured gracefully and surfaced in `execution_result` without crashing the reasoning workflow.

---

## 🛠️ Project Structure

```
backend/
├── app/
│   ├── agent/
│   │   ├── nodes/
│   │   │   ├── filter_node.py         # Non-LLM rule-based cost gate
│   │   │   ├── summarize_node.py      # LLM error diagnostics & structured summary
│   │   │   ├── fetch_diff_node.py     # GitHub diff fetching tool
│   │   │   ├── correlate_node.py      # LLM root-cause hypothesis & confidence
│   │   │   ├── escalate_node.py       # Action synthesis & WebSocket broadcasting
│   │   │   ├── low_confidence_node.py # Manual investigation routing
│   │   │   ├── await_human_node.py    # LangGraph checkpoint hold node
│   │   │   └── execute_node.py        # Render API execution & audit logging
│   │   ├── tools/
│   │   │   ├── github_diff.py         # GitHub REST API client + local git fallback
│   │   │   └── render_tool.py         # Render API client (restart & rollback deploys)
│   │   ├── graph.py                   # LangGraph StateGraph workflow & runner
│   │   ├── llm.py                     # Swappable LLM provider (Claude, Gemini, Mock)
│   │   └── state.py                   # IncidentState TypedDict & Pydantic models
│   ├── core/
│   │   └── config.py                  # Environment configurations & CORS
│   ├── models/
│   │   └── log.py                     # Pydantic models (LogPayload, IngestResponse, etc.)
│   ├── routes/
│   │   ├── health.py                  # GET /health
│   │   ├── incidents.py               # POST /incidents/{id}/decision & GET /incidents/pending
│   │   ├── logs.py                    # POST /logs/ingest
│   │   └── websocket.py               # WebSockets (/ws/logs, /ws/agent-thoughts, /ws/pending-approvals)
│   ├── services/
│   │   ├── approval_manager.py        # Pending approvals WebSocket & state manager
│   │   ├── connection_manager.py      # Raw log connection manager
│   │   └── thought_manager.py         # Agent thoughts WebSocket broadcaster
│   └── main.py                        # FastAPI application entrypoint
├── scripts/
│   └── simulate_logs.py               # Standalone continuous log generator
├── tests/
│   ├── conftest.py                    # Test fixtures
│   ├── test_api.py                    # REST & Phase 1-3 WebSocket / Approval tests
│   └── test_agent_graph.py            # Phase 2-3 LangGraph & node tests
├── .env.example                       # Environment template
├── requirements.txt                   # Pinned dependencies
└── README.md                          # Documentation
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
| `GITHUB_REPO` | `srinibasnayak23/BloHelp` | Target monitored repository |
| `GITHUB_COMMITS_LIMIT`| `5` | Number of recent commits to inspect |
| `CONFIDENCE_THRESHOLD`| `0.7` | Escalation threshold (0.0–1.0) |
| `RENDER_API_KEY` | `""` | Render API Key for automated remediation |
| `RENDER_TARGET_SERVICE_ID`| `""` | Monitored Render Service ID |
| `RENDER_BASE_URL` | `https://api.render.com/v1` | Render REST API Base URL |

> [!TIP]
> If no live API keys are provided, Nightshift automatically uses intelligent deterministic **Mock LLM & Simulated Render Tools** so all unit tests and local workflows run offline without spending tokens or touching production infrastructure!

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.12 installed on your machine.

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
- **Pending Approvals Stream**: `ws://localhost:8000/ws/pending-approvals`

### 2. Run the Standalone Log Simulator

In Terminal 2:
```powershell
cd backend
.\venv\Scripts\activate
python scripts/simulate_logs.py
```

---

## 🧪 Running Tests

To run the full test suite (27 automated tests covering Phase 1 ingestion, WebSocket broadcasting, LangGraph routing, structured LLM outputs, Render remediation tools, human approval endpoints, and safety guardrails):

```powershell
pytest tests/ -v
```

---

## 📡 API & WebSocket Reference

### 1. Submit Human Approval / Rejection Decision
`POST /incidents/{incident_id}/decision`
```json
{
  "decision": "approved"
}
```
Response:
```json
{
  "incident_id": "inc-4b72ef1a",
  "decision": "approved",
  "status": "executed",
  "action_type": "restart",
  "execution_result": {
    "status": "success",
    "action": "restart",
    "timestamp": "2026-08-23T14:45:02.120Z",
    "details": {
      "success": true,
      "message": "Successfully triggered restart for service srv-blohelp."
    }
  },
  "detail": "Incident inc-4b72ef1a remediation [restart] executed successfully."
}
```

### 2. Pending Approvals WebSocket Stream (`ws://localhost:8000/ws/pending-approvals`)
Broadcasts pending remediation approval requests in real time to connected clients (e.g., Android app):
```json
{
  "incident_id": "inc-4b72ef1a",
  "timestamp": "2026-08-23T14:45:00.000Z",
  "service": "BloHelp",
  "error_summary": "Fatal connection pool exhaustion and memory leak",
  "hypothesis": "Memory exhaustion due to unclosed database connections under concurrent load",
  "confidence": 0.88,
  "suspect_commit": "7f2a18b",
  "action_type": "restart",
  "status": "pending_approval"
}
```
