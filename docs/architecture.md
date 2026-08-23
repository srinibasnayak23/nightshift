# AI SRE Agent — Project Documentation

**Codename:** Autonomous Incident Response Agent
**Type:** Full-stack AI agent project (Web + Android + Cloud)
**Status:** Planning / Phase 1

---

## 1. Overview

### 1.1 Problem Statement
When a production service fails, the traditional response involves a human engineer being paged, manually digging through logs, correlating the failure with recent deployments, and applying a fix — often taking 30–60+ minutes even for well-understood issues.

### 1.2 Proposed Solution
An AI agent that:
1. Watches production logs continuously.
2. Detects anomalies and summarizes likely root causes using an LLM.
3. Correlates failures with recent code changes (git diffs).
4. Proposes a fix and requests human approval via a mobile push notification.
5. Executes the approved action (restart / rollback) through a standardized tool interface (MCP).

### 1.3 Success Metric
Reduce **time-to-diagnosis** (not necessarily time-to-deploy) from tens of minutes to under a minute, with every autonomous action gated by explicit human approval.

### 1.4 Non-Goals (v1)
- Fully autonomous deployment without human approval.
- Multi-cloud support (target one provider first — AWS or GCP).
- Handling non-log-based signals (metrics, traces) — log-based only for v1.

---

## 2. Architecture

### 2.1 High-Level Diagram (textual)

```
[Cloud Logs: CloudWatch/GCP Logging]
              |
              v
     [FastAPI Backend]
     ┌─────────────────────┐
     │  Log Ingestion       │
     │  LangGraph Agent     │──> [GitHub API: fetch diffs]
     │  MCP Tool Layer      │──> [Cloud Provider: restart/rollback]
     └─────────────────────┘
         |            |
         v            v
  [WebSocket]   [FCM Push Notification]
         |            |
         v            v
  [Angular Dashboard] [Android App]
   (live agent reasoning)  (approve/reject actions)
```

### 2.2 Components

| Component | Technology | Responsibility |
|---|---|---|
| Frontend (Control Plane) | Angular + WebSockets | Live view of agent's reasoning steps ("Chain of Thought") |
| Mobile (Human-in-the-Loop gateway) | Android (Kotlin) + FCM | Push notifications with one-tap Approve/Reject actions |
| Backend (Brain) | Python + FastAPI + LangGraph | Orchestrates detection → diagnosis → approval → action |
| Tool Layer | MCP (Model Context Protocol) | Standardized interface to cloud actions (restart, rollback) |
| LLM | Claude / Gemini (configurable) | Log summarization and root-cause hypothesis generation |

### 2.3 Data Flow
1. Cloud log line arrives → FastAPI ingestion endpoint (polling or push subscription).
2. Cheap non-LLM filter checks for anomaly signal (see §4.2).
3. If anomalous, LangGraph workflow runs: summarize → fetch diff → correlate → hypothesis.
4. Angular dashboard receives each step over WebSocket in real time.
5. If confidence is high enough, FCM notification sent to Android with proposed action.
6. Human approves/rejects on phone → webhook back to FastAPI.
7. On approval, MCP tool executes the action against the target environment.

---

## 3. Tech Stack

- **Backend:** Python 3.12, FastAPI, LangGraph, MCP SDK
- **Frontend:** Angular (latest stable), native WebSocket client
- **Mobile:** Android (Kotlin), Firebase Cloud Messaging
- **Cloud:** AWS CloudWatch Logs (or GCP Cloud Logging) — pick one for v1
- **LLM Provider:** Claude or Gemini API (abstracted behind a single interface so it's swappable)
- **Version Control Integration:** GitHub REST API for commit/diff retrieval
- **Data store (state/history):** Postgres or SQLite for incident history and agent decisions

---

## 4. Agent Design (LangGraph)

### 4.1 State Schema

```python
class IncidentState(TypedDict):
    raw_log: str
    is_anomaly: bool
    error_summary: str
    git_diff: str
    suspect_commit: str
    hypothesis: str
    confidence: float
    human_decision: str | None
```

### 4.2 Nodes

| Node | Type | Purpose |
|---|---|---|
| `filter_node` | Non-LLM | Regex/threshold-based anomaly pre-filter — cost control gate |
| `summarize_node` | LLM | Raw log → structured error summary |
| `fetch_diff_node` | Tool call | Pulls recent commit diffs for the affected service |
| `correlate_node` | LLM | Error summary + diff → hypothesis + explicit confidence score |
| `escalate_node` | Logic | Packages hypothesis into FCM notification payload |
| `low_confidence_node` | Logic | Sends raw findings only, flags for manual investigation |
| `await_human_node` | Blocking/webhook | Waits for Approve/Reject decision from Android |
| `execute_node` | MCP tool call | Executes restart/rollback, only on approval |

### 4.3 Edges / Control Flow
- `filter_node` → (`is_anomaly`?) → `summarize_node` **or** END
- `summarize_node` → `fetch_diff_node` → `correlate_node`
- `correlate_node` → (`confidence` ≥ 0.7?) → `escalate_node` **or** `low_confidence_node`
- `escalate_node` → `await_human_node` → (`human_decision`?) → `execute_node` **or** END

The confidence-gated branch is the core design decision: the agent explicitly distinguishes "confident enough to propose a fix" from "not confident — escalate raw data only."

---

## 5. Roadmap

### Phase 1 — The Observer (Weeks 1–3)
**Goal:** Connectivity and data pipeline, no intelligence yet.
- FastAPI service connects to cloud log source (CloudWatch/GCP Logging).
- Angular dashboard streams logs in real time via WebSocket.
- Android app configured with FCM, receives basic "Server Down" alerts.
- **Done when:** a real log line appears in the Angular dashboard within ~2 seconds of being emitted.

### Phase 2 — The Thinker (Weeks 4–7)
**Goal:** Intelligence via LangGraph (see §4 for full graph).
- Implement filter → summarize → fetch diff → correlate pipeline.
- Add "Thinking Terminal" UI in Angular showing step-by-step reasoning.
- Add the confidence-based conditional branch (§4.3).
- **Done when:** given a seeded error + a real commit, the agent produces a hypothesis referencing the correct commit, visible live in the dashboard.

### Phase 3 — The Actor (Weeks 8–12)
**Goal:** Autonomous action behind a human approval gate.
- Define MCP tools: `restart_service`, `rollback_deployment`.
- Build Android "Quick Action" notification: long-press → see proposed fix → Approve/Reject.
- Wire approval decision back into the LangGraph `await_human_node`.
- **Done when:** an approved action executes against a staging/sandbox environment (never real prod) and the result is reflected back in the dashboard.

---

## 6. Security & Safety Considerations

- **No direct production execution.** All `execute_node` actions in the demo/portfolio version target a staging environment or a disposable container, never a real production service.
- **Explicit approval required** for every state-changing action — no auto-deploy path in v1.
- **Audit trail:** every hypothesis, confidence score, and human decision is logged to the data store for later review.
- **Rejected actions are logged, not discarded** — useful signal for later tuning of the confidence threshold.
- **MCP tool definitions version-pinned** against a specific spec version to avoid protocol drift mid-project.

---

## 7. First 48 Hours

1. **Backend:** Scaffold a FastAPI project. Write a script using the Claude or Gemini API to summarize a pasted "fake" error log from a text file.
2. **Frontend:** Build a single Angular component that displays that summary.
3. Confirm both run end-to-end locally before moving to real cloud log integration.

---

## 8. Open Decisions

- [ ] AWS vs GCP for v1 (pick one, don't build both).
- [ ] Claude vs Gemini as primary LLM (should be abstracted regardless).
- [ ] Postgres vs SQLite for incident history store.
- [ ] Staging environment target for Phase 3 execution testing.
