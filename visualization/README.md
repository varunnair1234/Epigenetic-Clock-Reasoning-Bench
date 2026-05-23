# Epigenetic Clock Visualization API

FastAPI backend for the 900-cell aging simulation.

**Frontend removed.** Connect your Lovable frontend to this API.

## Start Backend

```bash
python -m uvicorn visualization.api:app --reload --port 5000
```

API docs: http://localhost:5000/docs

## Endpoints

- `GET /api/init` - Initialize simulation
- `POST /api/step` - Advance one month  
- `POST /api/reset` - Reset simulation
- `GET /api/status` - Get status

## Response Format

```json
{
  "cells": [{"x": 0, "y": 0, "state": "normal", "damage": 0.02, "telomere": 0.98}],
  "stats": {"clocks": {"horvath": 40.2, "grimage_proxy": 39.8}, ...},
  "step": 0
}
```

Connect your frontend to `http://localhost:5000`
