# Development Guide

## Prerequisites

- Python 3.12+
- Home Assistant development environment

## Setup

```bash
# Clone the repository
git clone https://github.com/CorSeptem/GardenaSmartHome.git
cd GardenaSmartHome

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements_dev.txt

# Run tests
pytest tests/
```

## Project Structure

```
custom_components/gardena_smart_system/
├── __init__.py          # Integration setup/unload
├── manifest.json        # HA integration manifest
├── config_flow.py       # UI configuration flow
├── const.py             # Constants and configuration
├── coordinator.py       # Data update coordinator
├── api/
│   ├── auth.py          # OAuth2 authentication
│   ├── client.py        # REST API client
│   └── websocket.py     # WebSocket real-time updates
├── entities/
│   ├── base.py          # Base entity class
│   ├── lawn_mower.py    # Mower entity
│   ├── valve.py         # Valve entity
│   └── sensor.py        # Sensor + binary sensor entities
├── services.yaml        # Service definitions
└── translations/        # UI translations
```

## Running Tests

```bash
pytest tests/ -v
pytest tests/test_auth.py -v    # Auth tests only
pytest tests/ --cov              # With coverage
```

## Validation

```bash
# Run hassfest (HA integration validator)
python -m script.hassfest --integration-path custom_components/gardena_smart_system

# Lint
ruff check custom_components/
```

## Key Design Decisions

1. **No external dependencies**: Only uses `aiohttp` which is bundled with HA
2. **WebSocket-first**: Real-time updates via WebSocket, REST API only for initial load and fallback
3. **Non-blocking SSL**: SSL context created in executor to avoid blocking the event loop (fixes issue #315)
4. **Proactive token refresh**: Token refreshed 5 minutes before expiry without disconnecting WebSocket
5. **Proper resource cleanup**: All WebSocket connections closed on integration unload (fixes issue #313)
