"""
PLC Bridge Profile
==================
Connects the MQTT sensor/output layer to an OpenPLC Runtime instance
running IEC 61131-3 programs (Ladder Logic, Structured Text, FBD, etc.)
via Modbus TCP.

Data flow:
    MCU sensors → MQTT → [this profile] → OpenPLC Modbus TCP (%QW100+)
    OpenPLC Modbus TCP (%QW0+) → [this profile] → MQTT → mcu-bridge → MCU

Register layout (configured in config/controller/plc_map.yml):
    %QW0   – %QW99  : OUTPUT zone — PLC writes here, bridge reads and publishes
    %QW100 – %QW199 : INPUT zone  — bridge writes sensor values, PLC reads

In your OpenPLC Structured Text / Ladder program:
    voltage_raw := QW100;   (* centivolts — divide by 100 for real value *)
    current_raw := QW101;
    temp_raw    := QW102;
    ... your control logic ...
    QW0 := relay_cmd;       (* 0 = off, 1 = on *)
    QW1 := pwm_duty;        (* 0–255 *)
    QW2 := estop_flag;      (* non-zero triggers emergency stop *)

To activate this profile:
    Set CONTROLLER_PROFILE=plc_bridge in your .env or docker-compose.yml
    (or set it directly: environment: PROFILE: plc_bridge)
"""
import logging
import os
import threading
from pathlib import Path

import yaml
from pymodbus.client import ModbusTcpClient

from app.base_profile import BaseProfile, ProfileState

log = logging.getLogger("profile.plc_bridge")

CONFIG_PATH = os.environ.get("PLC_MAP", "/app/config/plc_map.yml")


def _load_map() -> dict:
    path = Path(CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError(f"plc_map.yml not found at {CONFIG_PATH}")
    with open(path) as f:
        return yaml.safe_load(f)


class Profile(BaseProfile):
    """Bridges MQTT ↔ OpenPLC Runtime via Modbus TCP."""

    def __init__(self):
        self._cfg = _load_map()
        plc = self._cfg["openplc"]
        self._host = plc["host"]
        self._port = int(plc.get("port", 502))
        self._unit = int(plc.get("unit_id", 1))

        self._inputs: list[dict] = self._cfg.get("inputs", [])
        self._outputs: list[dict] = self._cfg.get("outputs", [])

        # Latest sensor values keyed by topic
        self._sensor_values: dict[str, float] = {}
        # Latest output values read from the PLC
        self._plc_outputs: dict[int, int] = {}
        # Previous output values — for trigger_only detection
        self._prev_outputs: dict[int, int] = {}

        self._lock = threading.Lock()
        self._mode = "idle"
        self._mqtt = None
        self._client: ModbusTcpClient | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def setup(self, mqtt, influx, config: dict) -> None:
        self._mqtt = mqtt
        self._client = ModbusTcpClient(self._host, port=self._port)

        # Subscribe to every sensor topic declared in plc_map.yml
        for inp in self._inputs:
            topic = inp["topic"]
            mqtt.subscribe(topic, self._make_sensor_handler(topic))

        log.info("PLC bridge ready — OpenPLC at %s:%d", self._host, self._port)

    def teardown(self) -> None:
        if self._client:
            self._client.close()

    # ── MQTT sensor handlers ──────────────────────────────────────────────────

    def _make_sensor_handler(self, topic: str):
        def handler(t, payload: bytes):
            try:
                value = float(payload.decode().strip())
                with self._lock:
                    self._sensor_values[topic] = value
            except (ValueError, AttributeError):
                log.warning("Could not parse sensor payload on %s: %s", topic, payload)
        return handler

    # ── control tick ──────────────────────────────────────────────────────────

    async def tick(self) -> None:
        with self._lock:
            if self._mode != "running":
                return
            sensor_snapshot = dict(self._sensor_values)

        if not self._client.connected:
            if not self._client.connect():
                log.warning("Cannot connect to OpenPLC at %s:%d — skipping tick",
                            self._host, self._port)
                return

        # 1. Write sensor values into PLC INPUT zone (holding registers 100+)
        for inp in self._inputs:
            value = sensor_snapshot.get(inp["topic"])
            if value is None:
                continue
            scale = float(inp.get("scale", 1))
            raw = int(round(value * scale))
            raw = max(0, min(65535, raw))   # clamp to uint16
            result = self._client.write_register(inp["register"], raw, slave=self._unit)
            if result.isError():
                log.warning("Modbus write error on register %d: %s", inp["register"], result)

        # 2. Read PLC OUTPUT zone (holding registers 0–99)
        if not self._outputs:
            return

        max_reg = max(o["register"] for o in self._outputs)
        result = self._client.read_holding_registers(0, max_reg + 1, slave=self._unit)
        if result.isError():
            log.warning("Modbus read error: %s", result)
            return

        registers = result.registers

        with self._lock:
            for out in self._outputs:
                reg = out["register"]
                if reg >= len(registers):
                    continue
                raw = registers[reg]
                scale = float(out.get("scale", 1))
                value = raw / scale if scale != 1 else raw
                self._plc_outputs[reg] = value

                trigger_only = out.get("trigger_only", False)
                prev = self._prev_outputs.get(reg)

                should_publish = (
                    not trigger_only
                    or (trigger_only and raw != 0 and raw != prev)
                )

                if should_publish:
                    self._mqtt.publish(out["topic"], str(int(raw)))
                    log.debug("PLC output register %d → %s = %s", reg, out["topic"], raw)

                self._prev_outputs[reg] = raw

    # ── state snapshot ────────────────────────────────────────────────────────

    def get_state(self) -> ProfileState:
        with self._lock:
            measurements = {
                inp["topic"].split("/")[-1]: self._sensor_values.get(inp["topic"], 0.0)
                for inp in self._inputs
            }
            outputs = {
                f"reg_{out['register']}_{out['topic'].split('/')[-1]}": self._plc_outputs.get(out["register"], 0)
                for out in self._outputs
            }
            return ProfileState(
                mode=self._mode,
                measurements=measurements,
                outputs=outputs,
                metadata={"plc_host": f"{self._host}:{self._port}"},
            )

    # ── commands ──────────────────────────────────────────────────────────────

    def on_command(self, command: str, params: dict) -> dict:
        if command == "start":
            with self._lock:
                self._mode = "running"
            log.info("PLC bridge started.")
            return {"ok": True}
        elif command == "stop":
            with self._lock:
                self._mode = "idle"
            # Zero out MCU outputs on stop
            if self._mqtt:
                for out in self._outputs:
                    self._mqtt.publish(out["topic"], "0")
            log.info("PLC bridge stopped.")
            return {"ok": True}
        elif command == "estop":
            with self._lock:
                self._mode = "idle"
            if self._mqtt:
                self._mqtt.publish("mcu/output/relay_0", "0")
                self._mqtt.publish("mcu/output/pwm_0", "0")
                self._mqtt.publish("mcu/output/estop", "1")
            log.warning("PLC bridge emergency stop.")
            return {"ok": True}
        return {"ok": False, "error": f"Unknown command: {command}"}
