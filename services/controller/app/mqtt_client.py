"""
MQTT client wrapper — async-compatible using paho in a thread executor.
"""
import json
import logging
import threading
from typing import Callable

import paho.mqtt.client as mqtt

from app.settings import Settings

log = logging.getLogger("controller.mqtt")


class MQTTClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._subscriptions: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()
        self._client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
        self._client.loop_start()

    # ── internal callbacks ────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log.info("Connected to MQTT broker at %s:%d",
                     self._settings.mqtt_host, self._settings.mqtt_port)
            with self._lock:
                for topic in self._subscriptions:
                    client.subscribe(topic)
        else:
            log.error("MQTT connection failed, reason_code=%s", reason_code)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        with self._lock:
            handlers = list(self._subscriptions.get(topic, []))
        for handler in handlers:
            try:
                handler(topic, msg.payload)
            except Exception:
                log.exception("Error in MQTT handler for topic %s", topic)

    # ── public API ────────────────────────────────────────────────────────────

    def subscribe(self, topic: str, handler: Callable):
        with self._lock:
            self._subscriptions.setdefault(topic, []).append(handler)
            self._client.subscribe(topic)

    def publish(self, topic: str, payload, retain: bool = False):
        if not isinstance(payload, (str, bytes)):
            payload = json.dumps(payload)
        self._client.publish(topic, payload, retain=retain)

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
