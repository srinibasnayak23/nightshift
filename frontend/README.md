# Nightshift — Frontend (Phase 3: The Actor)

Real-time Live Log Viewer, AI Reasoning Terminal & Human-in-the-Loop Remediation Platform for the **Nightshift AI SRE Agent**, built with **Angular (standalone components)** and native WebSockets.

---

## 📋 Features

- ⚡ **Multi-Stream WebSocket Architecture**:
  - `ws://localhost:8000/ws/logs`: Live log ingestion stream.
  - `ws://localhost:8000/ws/agent-thoughts`: Real-time LangGraph agent reasoning stream (Thinking Terminal).
  - `ws://localhost:8000/ws/pending-approvals`: Live stream of actionable remediation proposals awaiting human approval.
- 🛡️ **Pending Approvals & Human-in-the-Loop Gateway**:
  - Live incident cards displaying plain-language root-cause hypothesis, diagnostic signature, suspect commit with direct GitHub links, and proposed action (`Restart Service` vs `Rollback Deployment`).
  - **Inline Safety Confirmation Barrier**: Requires explicit human operator confirmation before dispatching live commands to Render.
  - **Direct REST Integration**: Submits decision to `POST /incidents/{incident_id}/decision` and displays live execution results (deploy ID, status, and API messages).
  - **Decision & Execution History**: Audited list of past human decisions and Render outcomes.
- 🧠 **Thinking Terminal Panel**:
  - Live pipeline stepper (`Filter` → `Summarize` → `Fetch Diff` → `Correlate` → `Escalate` → `Execute`).
  - Active step pulsing loader and monospaced diagnostic thought trace.
  - Root-cause hypothesis card with suspect commit SHA and dynamic colored confidence meter.
  - Collapsible Git diff inspector.
- 🎛️ **Flexible Workspace Layouts**:
  - **Split View (Default)**: Side-by-side view (Logs on Left, Thinking Terminal on Right).
  - **Logs Stream**: Full-width live log viewer.
  - **Thinking Terminal**: Full-width AI reasoning workspace.
  - **Pending Approvals**: Dedicated human-in-the-loop control center with pending badge count.
- 🔄 **Resilient Auto-Reconnection**: Independent auto-reconnection and countdown timers for all WebSockets.
- 🧪 **Offline Simulation Mode**: Independent simulation buttons for Logs, Thinking traces, and Remediation Approvals for local offline testing.

---

## 📡 API & WebSocket Specifications

### 1. Raw Log Stream
- **URL**: `ws://localhost:8000/ws/logs`

### 2. Agent Thinking Stream
- **URL**: `ws://localhost:8000/ws/agent-thoughts`

### 3. Pending Approvals Stream
- **URL**: `ws://localhost:8000/ws/pending-approvals`
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

### 4. Human Decision REST Endpoint
- **URL**: `POST http://localhost:8000/incidents/{incident_id}/decision`
- **Body**:
```json
{
  "decision": "approved"
}
```
- **Response**:
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
      "message": "Successfully triggered restart for service BloHelp."
    }
  },
  "detail": "Incident inc-4b72ef1a remediation [restart] executed successfully."
}
```

---

## 🚀 Getting Started

### Prerequisites

- **Node.js**: `v18.0.0` or newer
- **npm**: `v9.0.0` or newer

### 1. Install Dependencies
```bash
cd frontend
npm install
```

### 2. Run the Development Server
```bash
npm start
# or
npx ng serve
```

Navigate your browser to:
```
http://localhost:4200
```

### 3. Build for Production
```bash
npm run build
```

---

## 🧪 Testing Offline (Without Backend)

1. Open `http://localhost:4200`.
2. In the top navigation bar, click **"Pending Approvals"**.
3. Click **"Simulate Restart"** or **"Simulate Rollback"** to spawn a realistic remediation proposal card.
4. Click **"Approve & Execute"** -> confirm the safety prompt -> preview the execution state transition.
