"""Base class for all MCU drivers."""
import threading
from abc import ABC, abstractmethod


class BaseDriver(ABC):
    def __init__(self, config: dict, mqtt):
        self.config = config
        self.mqtt = mqtt
        self.id = config.get("id", "unknown")
        self.poll_interval = float(config.get("poll_interval", 1.0))
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Subscribe to output topics
        for topic, template in config.get("outputs", {}).items():
            mqtt.subscribe(topic, self._on_output_command)

    def _on_output_command(self, topic: str, payload: bytes):
        """Route an output MQTT message to the driver's send method."""
        template = self.config.get("outputs", {}).get(topic)
        if template is None:
            return
        try:
            value = payload.decode().strip()
            cmd = template.format(value=value) if "{value}" in template else template
            self.send_command(cmd)
        except Exception:
            import logging
            logging.getLogger(f"driver.{self.id}").exception("Output command error")

    @abstractmethod
    def send_command(self, command: str) -> str | None:
        """Send a command to the MCU. Return response if applicable."""

    @abstractmethod
    def _poll_loop(self):
        """Background thread: read sensors, publish to MQTT."""

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name=f"driver-{self.id}")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
