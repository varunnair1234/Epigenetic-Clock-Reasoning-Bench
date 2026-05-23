# Epigenetic Clock Visualization

Real-time 3D visualization of the 900-cell aging simulation using React + deck.gl.

## Features

- **Real-time simulation**: Watch 900 cells age over ~16 years
- **Interactive 3D grid**: Pan, zoom, and rotate the cell grid
- **Cell state colors**:
  - 🟢 Green = Normal
  - 🟡 Yellow = Stressed
  - 🔴 Red = Senescent
  - ⚫ Gray = Dead
- **Live statistics**: Senescent fraction, damage levels, etc.
- **Epigenetic clocks**: Real-time Horvath, GrimAge, and DunedinPACE values
- **Playback controls**: Play, pause, step, and reset

## Architecture

```
┌─────────────────┐      HTTP/JSON      ┌─────────────────┐
│  React Frontend │ ◄─────────────────► │  FastAPI Server │
│   (port 3000)   │                     │   (port 5000)   │
│                 │                     │                 │
│  - deck.gl viz  │                     │  - TissueModel  │
│  - Controls UI  │                     │  - Cell agents  │
│  - Stats panel  │                     │  - Simulation   │
└─────────────────┘                     └─────────────────┘
```

## Setup

### 1. Install Python Dependencies

```bash
# From project root
pip install fastapi uvicorn pydantic

# Or update from requirements.txt
pip install -r requirements.txt
```

### 2. Install Node.js Dependencies

```bash
cd visualization
npm install
```

## Running

### Terminal 1: Start FastAPI Backend

```bash
# From project root
python -m uvicorn visualization.api:app --reload --port 5000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:5000
INFO:     Application startup complete.
```

### Terminal 2: Start React Frontend

```bash
cd visualization
npm start
```

Browser should automatically open to `http://localhost:3000`

## API Endpoints

### `GET /api/init`
Initialize new simulation with 900 cells at step 0.

**Response:**
```json
{
  "cells": [
    {"x": 0, "y": 0, "state": "normal", "damage": 0.02, "telomere": 0.98},
    ...
  ],
  "stats": {
    "step": 0,
    "chronological_age_years": 40.0,
    "senescent_fraction": 0.03,
    "clocks": {
      "horvath": 40.2,
      "grimage_proxy": 39.8,
      "dunedinpace_proxy": 0.98
    }
  },
  "step": 0
}
```

### `POST /api/step`
Advance simulation by one step (1 month).

### `POST /api/reset`
Reset simulation to initial state.

### `GET /api/status`
Get current simulation status.

## Usage

1. Click **▶ Play** to run simulation automatically
2. Click **⏸ Pause** to pause
3. Click **⏭ Step** to advance one month at a time
4. Click **🔄 Reset** to restart from beginning

Watch the cells change color as they age:
- Normal cells accumulate damage → become **Stressed** (yellow)
- Stressed cells hit threshold → become **Senescent** (red)
- Senescent cells cluster due to SASP propagation
- Clock values update in real-time on the right panel

## Tech Stack

**Frontend:**
- React 18
- deck.gl 9.0 (WebGL visualization)
- Axios (HTTP client)

**Backend:**
- FastAPI (Python web framework)
- Uvicorn (ASGI server)
- MESA (agent-based modeling)

## Development

### Hot Reload

Both servers support hot reload:
- FastAPI: `--reload` flag automatically restarts on code changes
- React: Webpack dev server reloads on save

### Debugging

**Backend logs:**
```bash
# FastAPI logs to stdout
python -m uvicorn visualization.api:app --reload --port 5000 --log-level debug
```

**Frontend logs:**
- Open browser console (F12)
- Check Network tab for API calls

### Performance

- Simulation: ~0.5s per step (900 cells)
- Visualization: 60 FPS (deck.gl GPU-accelerated)
- Recommended: Run at 100-200ms per step for smooth animation

## Troubleshooting

### Port already in use
```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9

# Kill process on port 3000
lsof -ti:3000 | xargs kill -9
```

### CORS errors
- Make sure FastAPI is running on port 5000
- Check browser console for specific CORS error
- Verify `allow_origins` in `api.py` matches frontend URL

### Slow simulation
- Reduce speed in UI (increase ms/step)
- Run fewer steps
- Check CPU usage

## Next Steps

- [ ] Add intervention controls (senolytics, rapamycin)
- [ ] Export simulation data as video
- [ ] 3D hexagon grid instead of 2D
- [ ] Click cells to see individual methylation state
- [ ] Timeline scrubber to jump to specific steps
