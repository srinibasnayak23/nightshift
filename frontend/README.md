# Nightshift — Frontend (Phase 1: The Observer)

Real-time Live Log Viewer dashboard for the **Nightshift AI SRE Agent**, built with **Angular (standalone components)** and native WebSockets.

---

## Features

- ⚡ **Live WebSocket Log Streaming**: Connects to `ws://localhost:8000/ws/logs` with real-time log ingestion.
- 🔄 **Resilient Auto-Reconnection**: Gracefully handles backend restarts and offline states with live countdown timers and manual retry.
- 🎨 **Dark Ops Aesthetics**: Sleek dark console theme tailored for SREs with color-coded severity badges:
  - `INFO`: Cyan/Emerald badge
  - `WARN`: Amber/Yellow badge
  - `ERROR`: Rose/Red badge with edge glow
- ⏱️ **Newest Logs at the Top**: Live updates prepend to the top of the stream.
- 📜 **Smart Scroll Lock & "New Logs" Indicator**: When scrolling down to review older entries, automatic scrolling is safely held and a floating `"↓ N new logs"` banner appears to jump back to top.
- 🔍 **Real-Time Filtering & Search**: Instant filtering by log level (`ALL`, `ERRORS`, `WARNINGS`, `INFO`), service name, and free text.
- 🧪 **Offline Simulation Mode**: Built-in mock telemetry generator allowing full visual testing without requiring an active backend server.

---

## WebSocket Protocol Specification

The frontend connects to the backend WebSocket endpoint at:
```
ws://localhost:8000/ws/logs
```

### Expected Payload Shape (JSON)

```json
{
  "timestamp": "2026-08-23T12:00:00.000Z",
  "service": "payment-gw",
  "level": "error",
  "message": "ConnectionTimeoutException: upstream payment vault unreachable after 5000ms"
}
```

| Field | Type | Description |
|---|---|---|
| `timestamp` | `string` | ISO 8601 timestamp string (e.g., `2026-08-23T12:00:00Z`). |
| `service` | `string` | Originating service name (e.g., `auth-service`, `k8s-ingress`). |
| `level` | `string` | Log severity: `"info"`, `"warn"`, or `"error"`. |
| `message` | `string` | Log description or error details. |

---

## Getting Started

### Prerequisites

- **Node.js**: `v18.0.0` or newer (tested on Node v22)
- **npm**: `v9.0.0` or newer

### 1. Install Dependencies

From the `frontend/` directory:

```bash
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
Production artifacts will be placed in the `dist/` directory.

---

## Testing Without Backend (Simulate Logs)

If the backend WebSocket server is not running yet:
1. Open the dashboard at `http://localhost:4200`.
2. Notice the header displays `"Disconnected — retrying in Xs..."`.
3. Click the **"Simulate Logs"** button in the top right header (or click **"Simulate Sample Telemetry Stream"** in the empty state).
4. The dashboard will generate realistic synthetic multi-service cloud logs so you can inspect level badges, filters, search, and the smart scroll banner.
