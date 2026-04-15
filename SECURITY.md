# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Anima, please report it responsibly:

1. **Do NOT open a public GitHub issue** for security vulnerabilities
2. Email us at: **security@fullive.ai**
3. Include a detailed description of the vulnerability
4. Include steps to reproduce if possible

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## Security Considerations

### API Keys and Secrets

- Never commit `.env` files or API keys to the repository
- Use `.env.example` as a template with placeholder values
- LLM API keys are stored locally and never transmitted to third parties

### MQTT Broker

- The default MQTT configuration allows anonymous connections for local development
- For production deployments, configure authentication on your MQTT broker
- Use TLS for MQTT connections in production environments

### Device Access

- Device tokens (e.g., Xiaomi MIoT tokens) are stored locally in the `data/` directory
- Tokens are never logged or transmitted outside of device communication
- The QR-based authentication flow avoids storing cloud passwords

### Network Exposure

- The backend listens on `0.0.0.0:8080` by default — restrict this in production
- The MQTT broker binds to `0.0.0.0:1883` — restrict to local network in production
- Use a reverse proxy with TLS for any public-facing deployment
