"""
BaseProfile — abstract base class that every process profile must implement.

A profile encapsulates:
  - What sensor topics to subscribe to
  - What setpoints / parameters it manages
  - The control logic executed each loop tick
  - How it reports state and alarms
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProfileState:
    """Snapshot of the profile's current state, published to MQTT and the API."""
    mode: str = "idle"           # idle | running | paused | fault
    setpoints: dict = field(default_factory=dict)
    measurements: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    alarms: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class BaseProfile(ABC):

    # ── lifecycle ─────────────────────────────────────────────────────────────

    @abstractmethod
    def setup(self, mqtt, influx, config: dict) -> None:
        """
        Called once on startup. Subscribe to MQTT sensor topics, load config,
        initialize internal state.
        """

    @abstractmethod
    async def tick(self) -> None:
        """
        Called every control loop interval. Implement PID, FSM, sequence
        logic, safety checks, output commands here.
        """

    @abstractmethod
    def get_state(self) -> ProfileState:
        """Return current ProfileState snapshot."""

    # ── command handling ──────────────────────────────────────────────────────

    def on_command(self, command: str, params: dict) -> dict:
        """
        Handle a command received via MQTT or REST API.
        Override to support profile-specific commands.
        Returns a dict with at least {"ok": bool}.
        """
        return {"ok": False, "error": f"Unknown command: {command}"}

    # ── helpers (optional override) ───────────────────────────────────────────

    def teardown(self) -> None:
        """Called on shutdown. Override for cleanup."""
