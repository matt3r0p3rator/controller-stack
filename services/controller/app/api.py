"""
REST API — exposes controller state and command endpoints.
"""
import json
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class CommandRequest(BaseModel):
    command: str
    params: dict = {}


@router.get("/state")
def get_state(request: Request):
    controller = request.app.state.controller
    state = controller.profile.get_state()
    return {
        "mode": state.mode,
        "setpoints": state.setpoints,
        "measurements": state.measurements,
        "outputs": state.outputs,
        "alarms": state.alarms,
        "metadata": state.metadata,
    }


@router.post("/command")
def send_command(cmd: CommandRequest, request: Request):
    controller = request.app.state.controller
    result = controller.profile.on_command(cmd.command, cmd.params)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Command failed"))
    return result


@router.get("/health")
def health():
    return {"status": "ok"}
