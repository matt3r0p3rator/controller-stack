import json
import logging
import threading

import paho.mqtt.client as mqtt

log = logging.getLogger("mcu-bridge.mqtt")


class MQTTClient:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._subscriptions: dict[str, list] = {}
        self._lock = threading.Lock()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log.info("Connected to MQTT %s:%d", self._host, self._port)
            with self._lock:
                for topic in self._subscriptions:
                    client.subscribe(topic)
        else:
            log.error("MQTT connect failed: %s", reason_code)

    def _on_message(self, client, userdata, msg):
        with self._lock:
            handlers = list(self._subscriptions.get(msg.topic, []))
        for h in handlers:
            try:
                h(msg.topic, msg.payload)
            except Exception:
                log.exception("Handler error for topic %s", msg.topic)

    def subscribe(self, topic: str, handler):
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
