"""
Klipper/Moonraker driver — polls the Moonraker HTTP API for sensor data
and sends GCode commands via the API.
"""
import logging
import time

import httpx

from bridge.drivers.base_driver import BaseDriver

log = logging.getLogger("driver.klipper")


class KlipperDriver(BaseDriver):
    def __init__(self, config: dict, mqtt):
        super().__init__(config, mqtt)
        self.base_url = config["moonraker_url"].rstrip("/")
        self._client = httpx.Client(timeout=5.0)

    def send_command(self, command: str) -> str | None:
        """Send a GCode command via Moonraker's /printer/gcode/script endpoint."""
        try:
            resp = self._client.post(
                f"{self.base_url}/printer/gcode/script",
                json={"script": command},
            )
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError:
            log.exception("[%s] Moonraker command failed: %s", self.id, command)
            return None

    def _get_object_query(self) -> dict:
        """Build a Moonraker printer objects query from configured sensors."""
        # sensor keys like "extruder" or "heater_bed"
        objects = {}
        for key in self.config.get("sensors", {}).keys():
            objects[key] = None   # None = request all fields
        return objects

    def _poll_loop(self):
        objects = self._get_object_query()
        if not objects:
            log.warning("[%s] No sensors configured, idle.", self.id)
            return

        while not self._stop_event.is_set():
            try:
                resp = self._client.post(
                    f"{self.base_url}/printer/objects/query",
                    json={"objects": objects},
                )
                resp.raise_for_status()
                data = resp.json().get("result", {}).get("status", {})
                sensor_map = self.config.get("sensors", {})
                for obj_key, topic in sensor_map.items():
                    obj_data = data.get(obj_key, {})
                    # Publish temperature (and target) if present
                    temp = obj_data.get("temperature")
                    if temp is not None:
                        self.mqtt.publish(topic, str(temp))
                self.mqtt.publish(f"mcu/raw/{self.id}", data)
            except Exception:
                log.exception("[%s] Moonraker poll error", self.id)

            self._stop_event.wait(self.poll_interval)

        self._client.close()
