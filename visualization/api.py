"""FastAPI backend for cell simulation visualization.

Provides real-time simulation data to the React frontend.

Run with:
    uvicorn visualization.api:app --reload --port 5000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulation.tissue_model import TissueModel
from simulation.cell_agent import CellAgent

app = FastAPI(title="Epigenetic Clock Simulation API")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global simulation state
simulation_state = {
    "model": None,
    "step": 0
}


class CellData(BaseModel):
    x: int
    y: int
    state: str
    damage: float
    telomere: float


class SimulationResponse(BaseModel):
    cells: list[CellData]
    stats: dict
    step: int


@app.get("/")
async def root():
    return {"message": "Epigenetic Clock Simulation API", "status": "running"}


@app.get("/api/init", response_model=SimulationResponse)
async def init_simulation():
    """Initialize a new simulation."""
    # Create new tissue model
    model = TissueModel(chronological_start_age=40.0, seed=42)
    simulation_state["model"] = model
    simulation_state["step"] = 0

    # Get initial snapshot
    snapshot = model.snapshot()

    # Convert cells to frontend format
    cells = []
    for agent in model.agents:
        if hasattr(agent, 'pos') and agent.pos is not None:
            x, y = agent.pos
            cells.append(CellData(
                x=x,
                y=y,
                state=agent.state,
                damage=float(agent.damage),
                telomere=float(agent.telomere)
            ))

    return SimulationResponse(
        cells=cells,
        stats=snapshot,
        step=simulation_state["step"]
    )


@app.post("/api/step", response_model=SimulationResponse)
async def step_simulation():
    """Advance simulation by one step."""
    model = simulation_state.get("model")

    if model is None:
        # Initialize if not exists
        return await init_simulation()

    # Step the simulation
    model.step()
    simulation_state["step"] += 1

    # Get updated snapshot
    snapshot = model.snapshot()

    # Convert cells to frontend format
    cells = []
    for agent in model.agents:
        if hasattr(agent, 'pos') and agent.pos is not None:
            x, y = agent.pos
            cells.append(CellData(
                x=x,
                y=y,
                state=agent.state,
                damage=float(agent.damage),
                telomere=float(agent.telomere)
            ))

    return SimulationResponse(
        cells=cells,
        stats=snapshot,
        step=simulation_state["step"]
    )


@app.get("/api/status")
async def get_status():
    """Get current simulation status."""
    return {
        "initialized": simulation_state.get("model") is not None,
        "step": simulation_state.get("step", 0)
    }


@app.post("/api/reset")
async def reset_simulation():
    """Reset simulation to initial state."""
    return await init_simulation()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
