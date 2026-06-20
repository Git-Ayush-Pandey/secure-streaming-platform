# Security Policy

## Secure Real-Time Screen Streaming Platform

This document describes the security architecture, trust assumptions, security controls, and known limitations of the Secure Real-Time Screen Streaming Platform.

---

# Overview

The platform is designed to provide secure, low-latency screen streaming over a local network while enforcing authentication, encryption, device trust management, and operational visibility.

Primary goals:

* Authenticate clients before granting access.
* Protect streaming traffic against unauthorized access.
* Maintain integrity of transmitted data.
* Prevent abuse through resource controls and rate limiting.
* Provide visibility through audit logging and monitoring.

---

# Security Architecture

The platform consists of:

* FastAPI backend
* React dashboard
* Windows streaming client
* WebSocket authentication channel
* Encrypted UDP transport
* Device trust registry

High-level flow:

```text
Client
   │
   │ Authentication
   ▼
FastAPI Backend
   │
   │ Session Establishment
   ▼
Encrypted UDP Stream
   │
   ▼
Dashboard / Client Rendering
```

---

# Authentication

Authentication is based on:

* Ed25519 identity keys
* Challenge-response verification
* Device approval workflow
* Session management

Clients must successfully complete authentication before streaming is permitted.

---

# Key Exchange

Session keys are established using:

* X25519 Elliptic Curve Diffie-Hellman
* HKDF-SHA256 key derivation

Session keys are unique per session and are not stored permanently.

---

# Encryption

Streaming traffic is protected using:

* AES-256-GCM authenticated encryption

Security properties:

* Confidentiality
* Integrity
* Authentication of encrypted packets

---

# Trust Model

The platform follows a Trust-On-First-Use (TOFU) model.

New devices:

1. Connect to the authentication service.
2. Enter a pending state.
3. Require operator approval.
4. Become trusted only after approval.

Operators may:

* Approve
* Allow Once
* Reject
* Block

trusted devices.

---

# Dashboard Security

Administrative functionality is protected through:

* Dashboard authentication tokens
* Localhost access restrictions
* WebSocket authentication
* Audit logging

Administrative actions are attributable to authenticated dashboard sessions.

---

# Session Security

Implemented protections include:

* Session expiration
* Session revocation
* Replay protection
* Nonce validation
* Session-specific encryption keys
* Session lifecycle tracking

Expired sessions are automatically removed.

---

# Transport Security

The UDP transport layer includes:

* Encrypted payloads
* Integrity validation
* Packet verification
* Replay protection
* Rate limiting
* Resource limits

Malformed packets are rejected before expensive processing.

---

# Availability Protections

The platform implements:

* Authentication rate limiting
* Resource limits
* Session limits
* Connection limits
* Automatic cleanup of expired state
* Defensive handling of malformed input

These controls help protect the service against accidental or abusive resource consumption.

---

# Logging and Monitoring

Security-relevant events are recorded, including:

* Authentication attempts
* Device approvals
* Device rejections
* Device blocking
* Session creation
* Session expiration
* Administrative actions

Log files are:

* Rotated automatically
* Size limited
* Persisted for troubleshooting and auditing

---

# Configuration Security

Configuration values are validated before use.

Configuration updates are written atomically to reduce the risk of corruption.

Secrets and private keys should never be committed to version control.

---

# Security Assumptions

This project assumes:

* The host operating system is trusted.
* Local administrators control access to the machine.
* Private keys remain private.
* Operators carefully review device approval requests.
* The deployment occurs on a trusted local network.

---

# Known Limitations

Current limitations include:

* No external certificate authority integration.
* No enterprise identity provider integration.
* No role-based access control.
* Designed for local-network deployment rather than public Internet exposure.
* Client-side key protection relies on local filesystem protections rather than platform-specific secure hardware.

---

# Recommended Operational Practices

Before publishing or deployment:

* Rotate keys if they were ever committed to version control.
* Verify `.gitignore` excludes all secrets and runtime data.
* Use unique dashboard authentication tokens.
* Review trusted devices periodically.
* Keep dependencies updated.

---

# Responsible Disclosure

If a security issue is discovered:

1. Do not publish exploit details publicly.
2. Provide a private report containing:

   * affected component
   * description
   * impact
   * reproduction steps
3. Allow time for remediation before public disclosure.

---

# Security Status

Implemented controls include:

* Mutual authentication
* Device trust workflow
* Challenge-response verification
* X25519 key exchange
* HKDF-derived session keys
* AES-GCM encryption
* Replay protection
* Session management
* Dashboard authentication
* Rate limiting
* Audit logging
* Configuration validation
* Resource controls

This project is intended as both a practical secure streaming platform and a security engineering portfolio project.