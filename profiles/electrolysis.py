"""
Electrolysis Process Profile
=============================
Example use-case: controls a hydrogen/oxygen electrolysis cell.

Inputs (from MCU via MQTT):
  mcu/sensor/mcu_0/voltage_0   — cell voltage (V)
  mcu/sensor/mcu_0/current_0   — cell current (A)
  mcu/sensor/mcu_0/temp_0      — electrolyte temperature (°C)
  mcu/sensor/mcu_0/temp_1      — ambient / case temperature (°C)

Outputs (to MCU via MQTT):
  mcu/output/relay_0            — cell power relay (1=on, 0=off)
  mcu/output/pwm_0              — DC-DC converter PWM duty (0-255)
  mcu/output/estop              — emergency stop (any value triggers M112)

Safety limits (configurable via on_command "set_param"):
  max_cell_temp    — default 60 °C
  max_cell_voltage — default 30 V
  max_cell_current — default 20 A
  target_current   — default 10 A (simple current-target bang-bang)

Commands (via REST POST /api/command or MQTT controller/command):
  {"command": "start"}
  {"command": "stop"}
  {"command": "estop"}
  {"command": "set_param", "params": {"target_current": 8.0}}

Adapt this file to any process by replacing the sensor topics, setpoints,
and tick() logic. Copy it to profiles/<your_process>.py and set
CONTROLLER_PROFILE=<your_process> in .env.
"""
import asyncio
import logging
import threading
from dataclasses import dataclass, field

from app.base_profile import BaseProfile, ProfileState

log = logging.getLogger("profile.electrolysis")

# ── tuneable defaults ─────────────────────────────────────────────────────────
DEFAULT_TARGET_CURRENT = 10.0   # A
DEFAULT_MAX_TEMP        = 60.0  # °C
DEFAULT_MAX_VOLTAGE     = 30.0  # V
DEFAULT_MAX_CURRENT     = 20.0  # A

# MQTT sensor topics (must match mcu.yml sensor map)
TOPIC_VOLTAGE   = "mcu/sensor/mcu_0/voltage_0"
TOPIC_CURRENT   = "mcu/sensor/mcu_0/current_0"
TOPIC_TEMP_CELL = "mcu/sensor/mcu_0/temp_0"
TOPIC_TEMP_AMB  = "mcu/sensor/mcu_0/temp_1"

# MQTT output topics (must match mcu.yml output map)
OUT_RELAY = "mcu/output/relay_0"
OUT_PWM   = "mcu/output/pwm_0"
OUT_ESTOP = "mcu/output/estop"


@dataclass
class ElectrolysisState:
    mode: str = "idle"          # idle | running | paused | fault
    voltage: float = 0.0        # V
    current: float = 0.0        # A
    temp_cell: float = 0.0      # °C
    temp_amb: float  = 0.0      # °C
    power_w: float   = 0.0      # W  (calculated)
    relay_on: bool   = False
    pwm_duty: int    = 0        # 0-255
    alarms: list[str] = field(default_factory=list)


class Profile(BaseProfile):
    """Electrolysis cell controller profile."""

    def __init__(self):
        self._state = ElectrolysisState()
        self._lock  = threading.Lock()
        self._mqtt  = None
        self._influx = None

        # Setpoints — can be updated at runtime via on_command
        self.target_current = DEFAULT_TARGET_CURRENT
        self.max_temp        = DEFAULT_MAX_TEMP
        self.max_voltage     = DEFAULT_MAX_VOLTAGE
        self.max_current     = DEFAULT_MAX_CURRENT

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def setup(self, mqtt, influx, config: dict) -> None:
        self._mqtt   = mqtt
        self._influx = influx

        mqtt.subscribe(TOPIC_VOLTAGE,   self._on_voltage)
        mqtt.subscribe(TOPIC_CURRENT,   self._on_current)
        mqtt.subscribe(TOPIC_TEMP_CELL, self._on_temp_cell)
        mqtt.subscribe(TOPIC_TEMP_AMB,  self._on_temp_amb)

        log.info("Electrolysis profile ready. Target current: %.1f A", self.target_current)

    # ── MQTT sensor callbacks (run in MQTT thread) ────────────────────────────

    def _on_voltage(self, topic, payload):
        with self._lock:
            self._state.voltage = self._parse_float(payload)

    def _on_current(self, topic, payload):
        with self._lock:
            self._state.current = self._parse_float(payload)

    def _on_temp_cell(self, topic, payload):
        with self._lock:
            self._state.temp_cell = self._parse_float(payload)

    def _on_temp_amb(self, topic, payload):
        with self._lock:
            self._state.temp_amb = self._parse_float(payload)

    @staticmethod
    def _parse_float(payload) -> float:
        try:
            return float(payload.decode().strip())
        except (ValueError, AttributeError):
            return 0.0

    # ── control tick ──────────────────────────────────────────────────────────

    async def tick(self) -> None:
        with self._lock:
            s = self._state
            mode = s.mode

        if mode == "fault":
            return   # stay in fault until cleared by "stop" or "estop"

        if mode != "running":
            return   # idle / paused — do nothing

        alarms: list[str] = []

        # ── safety checks ────────────────────────────────────────────────────
        if s.temp_cell > self.max_temp:
            alarms.append(f"OVER_TEMP_CELL: {s.temp_cell:.1f}°C > {self.max_temp}°C")

        if s.voltage > self.max_voltage:
            alarms.append(f"OVER_VOLTAGE: {s.voltage:.2f}V > {self.max_voltage}V")

        if s.current > self.max_current:
            alarms.append(f"OVER_CURRENT: {s.current:.2f}A > {self.max_current}A")

        if alarms:
            log.warning("Alarm(s): %s", alarms)
            self._emergency_stop(alarms)
            return

        # ── simple bang-bang current control ────────────────────────────────
        # Increase PWM duty if below target; decrease if above.
        # Replace with a PID controller for real applications.
        with self._lock:
            duty = s.pwm_duty
            current = s.current

        tolerance = 0.5   # A hysteresis band

        if current < self.target_current - tolerance:
            duty = min(255, duty + 5)
        elif current > self.target_current + tolerance:
            duty = max(0, duty - 5)

        with self._lock:
            s.pwm_duty   = duty
            s.power_w    = round(s.voltage * s.current, 2)
            s.alarms     = alarms

        self._mqtt.publish(OUT_PWM, str(duty))
        log.debug("Tick: V=%.2f I=%.2f T=%.1f PWM=%d", s.voltage, s.current, s.temp_cell, duty)

    # ── state snapshot ────────────────────────────────────────────────────────

    def get_state(self) -> ProfileState:
        with self._lock:
            s = self._state
            return ProfileState(
                mode=s.mode,
                setpoints={
                    "target_current_A": self.target_current,
                    "max_temp_C":       self.max_temp,
                    "max_voltage_V":    self.max_voltage,
                    "max_current_A":    self.max_current,
                },
                measurements={
                    "voltage_V":   s.voltage,
                    "current_A":   s.current,
                    "power_W":     s.power_w,
                    "temp_cell_C": s.temp_cell,
                    "temp_amb_C":  s.temp_amb,
                },
                outputs={
                    "relay": int(s.relay_on),
                    "pwm_duty": s.pwm_duty,
                },
                alarms=list(s.alarms),
            )

    # ── commands ──────────────────────────────────────────────────────────────

    def on_command(self, command: str, params: dict) -> dict:
        if command == "start":
            return self._start()
        elif command == "stop":
            return self._stop()
        elif command == "estop":
            self._emergency_stop(["Manual emergency stop"])
            return {"ok": True}
        elif command == "set_param":
            return self._set_param(params)
        return {"ok": False, "error": f"Unknown command: {command}"}

    def _start(self) -> dict:
        with self._lock:
            if self._state.mode == "fault":
                return {"ok": False, "error": "In fault state. Send 'stop' to reset."}
            self._state.mode     = "running"
            self._state.relay_on = True
            self._state.pwm_duty = 0
        self._mqtt.publish(OUT_RELAY, "1")
        log.info("Electrolysis started.")
        return {"ok": True}

    def _stop(self) -> dict:
        with self._lock:
            self._state.mode     = "idle"
            self._state.relay_on = False
            self._state.pwm_duty = 0
            self._state.alarms   = []
        self._mqtt.publish(OUT_RELAY, "0")
        self._mqtt.publish(OUT_PWM,   "0")
        log.info("Electrolysis stopped.")
        return {"ok": True}

    def _emergency_stop(self, alarms: list[str]):
        with self._lock:
            self._state.mode     = "fault"
            self._state.relay_on = False
            self._state.pwm_duty = 0
            self._state.alarms   = alarms
        self._mqtt.publish(OUT_RELAY, "0")
        self._mqtt.publish(OUT_PWM,   "0")
        self._mqtt.publish(OUT_ESTOP, "1")   # triggers M112 on MCU
        log.error("EMERGENCY STOP. Alarms: %s", alarms)

    def _set_param(self, params: dict) -> dict:
        valid = {"target_current", "max_temp", "max_voltage", "max_current"}
        updated = {}
        for k, v in params.items():
            if k not in valid:
                return {"ok": False, "error": f"Unknown parameter: {k}"}
            try:
                setattr(self, k, float(v))
                updated[k] = float(v)
            except (TypeError, ValueError):
                return {"ok": False, "error": f"Invalid value for {k}: {v}"}
        log.info("Parameters updated: %s", updated)
        return {"ok": True, "updated": updated}

    def teardown(self) -> None:
        self._stop()
