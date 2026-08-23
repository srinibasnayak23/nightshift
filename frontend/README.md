# Nightshift — Frontend (Phase 2: The Thinker)

Real-time Live Log Viewer & AI Reasoning Dashboard for the **Nightshift AI SRE Agent**, built with **Angular (standalone components)** and native WebSockets.

---

## 📋 Features

- ⚡ **Dual WebSocket Streaming**:
  - `ws://localhost:8000/ws/logs`: Live log ingestion stream.
  - `ws://localhost:8000/ws/agent-thoughts`: Real-time LangGraph agent reasoning stream (Thinking Terminal).
- 🧠 **Thinking Terminal Panel**:
  - Live 4-node pipeline stepper (`Filter` → `Summarize` → `Fetch Diff` → `Correlate`).
  - Active step pulsing loader and monospaced diagnostic thought trace.
  - Cost-gate nominal badge: Clear `"No anomaly detected — pipeline stopped"` when non-anomalous logs skip expensive LLM steps.
  - **Root-Cause Hypothesis Card**: High-visibility hypothesis callout, suspect commit SHA pill, and dynamic colored confidence meter (🔴 Low < 50%, 🟡 Moderate 50–79%, 🟢 High ≥ 80%).
  - **Collapsible Git Diff Inspector**: Review suspect commit diff patches right from the terminal.
  - **Trace History Accordion**: Review past incident investigations with timestamps, service tags, and confidence scores.
- 🎛️ **Flexible Workspace Layouts**:
  - **Split View (Default)**: Side-by-side view (Logs on Left, Thinking Terminal on Right).
  - **Logs Stream**: Full-width live log viewer.
  - **Thinking Terminal**: Full-width AI reasoning workspace.
- 🔄 **Resilient Auto-Reconnection**: Independent auto-reconnection and countdown timers for both WebSockets.
- 🎨 **Dark Ops Aesthetics**: Sleek dark console theme tailored for SREs with glowing status indicators and glassmorphic panels.
- 🧪 **Offline Simulation Mode**: Independent simulation buttons for both Log telemetry and Agent thinking traces for local offline testing without a running backend.

---

## 📡 WebSocket Specifications

### 1. Raw Log Stream
- **URL**: `ws://localhost:8000/ws/logs`
```json
{
  "timestamp": "2026-08-23T14:30:00.000Z",
  "service": "payment-gateway",
  "level": "error",
  "message": "Database deadlock encountered during transaction #84102"
}
```

### 2. Agent Thinking Stream
- **URL**: `ws://localhost:8000/ws/agent-thoughts`
```json
{
  "timestamp": "2026-08-23T14:30:01.120Z",
  "node": "correlate_node",
  "status": "completed",
  "thought": "Hypothesis generated (Confidence: 88.0%): The incident was caused by commit 7f2a18b...",
  "confidence": 0.88,
  "state": {
    "is_anomaly": true,
    "error_summary": "Database deadlock in payment-gateway",
    "git_diff": "Commit 7f2a18b: Added unindexed foreign key...",
    "suspect_commit": "7f2a18b",
    "hypothesis": "The incident was caused by commit 7f2a18b...",
    "confidence": 0.88
  }
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
2. In the top navigation, click **"Simulate Logs"** to generate live multi-service logs.
3. In the **Thinking Terminal** header, click **"Simulate Anomaly"** to run a complete 4-step AI incident investigation trace, or click **"Simulate Nominal"** to preview a cost-gated non-anomaly stop.
