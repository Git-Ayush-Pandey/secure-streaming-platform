# Secure Real-Time Screen Streaming Platform

## Overview

**Problem:** Securely streaming a selected screen region in real time over a local network requires robust authentication, encrypted transport, and reliable delivery.

**Purpose:** This repository provides a complete, reusable framework that enables:
- Secure screen capture on a host machine.
- Authenticated client access via X25519 key exchange.
- Encrypted UDP streaming of video frames.
- Real‑time monitoring and device‑trust management through a web dashboard.

**Architecture Summary**
```
Screen Capture → Encoding → Encryption → Transport → Client Rendering (Dashboard)
```
## Screenshots

### Dashboard Interface

![Dashboard](images/dashboard.png)

Administrative dashboard for monitoring stream health, managing device trust, reviewing security statistics, and configuring streaming parameters in real time.

### Secure Real-Time Streaming

![Client Stream](images/client_stream.png)

Live demonstration of encrypted low-latency screen streaming, showing the source content (left) and the authenticated client receiving the stream in real time (right).

## Features

### Server Features
- Secure WebSocket authentication with X25519 key exchange and challenge‑response.
- Session lifecycle management (single‑use and persistent sessions).
- Rate limiting and DoS protection.
- REST API for server configuration and status.
- Detailed logging and health endpoint.

### Client Features
- Asynchronous connection manager with automatic reconnect logic.
- Configurable screen capture region, resolution, FPS, and quality.
- Automatic session key derivation and encrypted UDP packets.
- Graceful shutdown and single‑use session revocation.

### Security Features
- Mutual authentication using Ed25519 identities and challenge-response verification.
- X25519 key exchange with HKDF-derived session keys.
- AES-GCM authenticated encryption for streaming traffic.
- Replay protection using session validation and nonce tracking.
- Dashboard authentication with token-based access control.
- Rate limiting for authentication and streaming endpoints.
- Atomic configuration writes and configuration validation.
- Structured audit logging for security-relevant actions.
- Server and client private keys excluded from version control.

### Streaming Features
- UDP streaming with configurable quality presets.
- Server reassembles encrypted frames and forwards them to the dashboard.
- Support for dynamic reconfiguration without restarting the server.

### Dashboard Features
- Token-protected administrative dashboard.
- Real-time device list with pending approvals.
- Live video preview of streamed screen content.
- Security statistics (rate limits, session counts, stream health).
- Audit visibility for security-related actions.
- Ability to approve, allow-once, block, reject, trust, and revoke devices.

## Architecture Overview
```
Screen Capture
  ↓
Encoding (frame compression)
  ↓
Encryption (session key)
  ↓
Transport (UDP packets)
  ↓
Client Rendering (React dashboard)
```

## Project Structure
```
secure web Server/
│
├─ WindowsClient/                # Python client application
│   ├─ .env, .env.example
│   ├─ .venv/                    # Virtual environment (ignored)
│   ├─ config/                    # Logging and settings
│   ├─ core/                      # Connection manager, state machine, etc.
│   ├─ data/                      # Runtime data (logs, caches)
│   ├─ ui/                        # Video window UI (Tkinter/OpenCV)
│   └─ main.py                    # Entry point
│
├─ server/                        # FastAPI backend
│   ├─ backend/
│   │   ├─ config.py             # Server configuration handling
│   │   ├─ services/             # auth, capture, crypto, stream, logger
│   │   └─ main.py                # FastAPI app and lifespan
│   ├─ frontend/                  # React + Vite dashboard
│   │   ├─ src/                  # React source (components, pages)
│   │   ├─ public/, dist/        # Static assets and build output
│   │   └─ package.json
│   ├─ .gitignore
│   └─ run.py                     # Helper to launch FastAPI with uvicorn
│
├─ .gitignore                    # Repository‑wide ignore rules
└─ README.md (this file)
```

## Requirements
- **Python** ≥ 3.10 (client and server)
- **Node.js** ≥ 18 (frontend)
- **Operating System:** Windows 10/11 (tested)

## Running the Server
```bash
# From the repository root
cd server
uvicorn backend.main:app --host 0.0.0.0 --port 8765
```
The REST API is available at `http://localhost:8765` and the dashboard at `http://localhost:5173`.

## Running the Client
```bash
cd WindowsClient
python main.py
```
The client will connect to the server, handle authentication, and start streaming the captured screen region.

## Configuration
- **Environment variables** (client): see `.env.example` for keys such as `SERVER_HOST`, `SERVER_PORT`, `CAPTURE_X`, `CAPTURE_Y`, etc.
- **Config files** (server): `backend/config.py` stores `server_config.json` under `backend/data/config/`.

## Dashboard Overview
- **Device List** – shows pending, trusted, blocked devices.
- **Live Video** – renders the streamed screen content.
- **Security Panel** – displays rate‑limit stats, session counts, and recent logs.
- **Controls** – approve, allow‑once, block, or reject devices directly from the UI.

## Security Model

- **Authentication** – Ed25519 identity keys with signed challenge-response verification.
- **Key Exchange** – Ephemeral X25519 exchange with HKDF-SHA256 session key derivation.
- **Encryption** – AES-GCM authenticated encryption protects streaming traffic.
- **Trust Workflow** – New devices enter a pending state and require operator approval.
- **Dashboard Security** – Administrative endpoints require dashboard authentication and localhost access controls.
- **Replay Protection** – Session validation and nonce tracking prevent packet reuse.
- **Rate Limiting** – Authentication and streaming services enforce configurable resource limits.
- **Audit Logging** – Security-sensitive actions are recorded for traceability.
- **Session Lifecycle** – Sessions expire automatically and may be revoked by policy.

## Troubleshooting
- **Server fails to start** – ensure no other process is using port 8765; check logs (`backend/data/logs/`).
- **Client cannot connect** – verify `SERVER_HOST` and `SERVER_PORT` in `.env`; ensure firewall allows UDP traffic.
- **Video is blank** – check capture region coordinates and that the screen/camera is accessible.
- **Authentication errors** – ensure the server’s private/public keys exist in `backend/data/keys/` and are not listed in the repo.

## Future Improvements
- Docker containers for easier deployment.
- TLS termination for the FastAPI server.
- Mobile client implementation.
- Support for multiple simultaneous video streams.

## Security Documentation

Additional security details, trust assumptions, and known limitations are documented in [SECURITY.md](SECURITY.md).


## License
This project is licensed under the MIT License.
Copyright (c) 2026 Ayush Pandey