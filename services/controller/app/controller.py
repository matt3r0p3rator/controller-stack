"""
ProcessController — main control loop orchestrator.
"""
import asyncio
import json
import logging

from app.settings import Settings
from app.mqtt_client import MQTTClient
from app.influx_writer import InfluxWriter
from app.base_profile import BaseProfile

log = logging.getLogger("controller.loop")

LOOP_INTERVAL = 1.0   # seconds — overridden by profile if needed


class ProcessController:
    def __init__(
        self,
        settings: Settings,
        mqtt: MQTTClient,
        influx: InfluxWriter,
        profile: BaseProfile,
    ):
        self.settings = settings
        self.mqtt = mqtt
        self.influx = influx
        self.profile = profile
        self._running = False

        # Subscribe to inbound commands
        mqtt.subscribe("controller/command", self._handle_command)

        # Initialise profile
        profile.setup(mqtt=mqtt, influx=influx, config={})

    # ── command handler (runs in MQTT thread) ─────────────────────────────────

    def _handle_command(self, topic: str, payload: bytes):
        try:
            msg = json.loads(payload)
            command = msg.get("command", "")
            params = msg.get("params", {})
            result = self.profile.on_command(command, params)
            self.mqtt.publish("controller/command/response", result)
        except Exception:
            log.exception("Error handling command payload: %s", payload)

    # ── main loop ─────────────────────────────────────────────────────────────

    async def run(self):
        self._running = True
        log.info("Control loop started (%.1fs interval)", LOOP_INTERVAL)
        while self._running:
            try:
                await self.profile.tick()
                state = self.profile.get_state()

                # Publish state to MQTT
                self.mqtt.publish("controller/state", {
                    "mode": state.mode,
                    "setpoints": state.setpoints,
                    "measurements": state.measurements,
                    "outputs": state.outputs,
                    "alarms": state.alarms,
                })

                # Publish alarms separately if any
                if state.alarms:
                    for alarm in state.alarms:
                        self.mqtt.publish("controller/alarm", {"alarm": alarm})

                # Persist measurements to InfluxDB
                if state.measurements:
                    self.influx.write(
                        measurement="process",
                        fields=state.measurements,
                        tags={"profile": self.settings.profile, "mode": state.mode},
                    )

            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Unhandled error in control loop tick")

            await asyncio.sleep(LOOP_INTERVAL)

        log.info("Control loop exited.")

    async def stop(self):
        self._running = False
        self.profile.teardown()
        self.mqtt.stop()
        self.influx.close()
