"""
Modbus RTU driver — reads holding registers / coils and writes coils/registers
via minimalmodbus.
"""
import logging
import time

import minimalmodbus

from bridge.drivers.base_driver import BaseDriver

log = logging.getLogger("driver.modbus")


class ModbusDriver(BaseDriver):
    def __init__(self, config: dict, mqtt):
        super().__init__(config, mqtt)
        self.port = config["port"]
        self.baud = int(config.get("baud", 9600))
        self.slave_id = int(config.get("slave_id", 1))
        self._instrument: minimalmodbus.Instrument | None = None

    def _open(self):
        inst = minimalmodbus.Instrument(self.port, self.slave_id)
        inst.serial.baudrate = self.baud
        inst.serial.timeout = 1
        self._instrument = inst
        log.info("[%s] Opened Modbus RTU on %s slave=%d", self.id, self.port, self.slave_id)

    def send_command(self, command: str) -> str | None:
        """
        Modbus doesn't use text commands. 'command' is ignored here.
        Output coil writes come through _on_output_command → write_coil directly.
        """
        log.debug("[%s] send_command not applicable for Modbus: %s", self.id, command)
        return None

    def _on_output_command(self, topic: str, payload: bytes):
        """Write a coil when an output MQTT message arrives."""
        coils = self.config.get("coils", {})
        coil_cfg = coils.get(topic)
        if coil_cfg is None:
            return
        address = coil_cfg["address"]
        try:
            value = int(payload.decode().strip())
            if self._instrument:
                self._instrument.write_bit(address, value, functioncode=5)
                log.debug("[%s] Wrote coil %d = %d", self.id, address, value)
        except Exception:
            log.exception("[%s] Coil write error for topic %s", self.id, topic)

    def _poll_loop(self):
        while not self._stop_event.is_set():
            if self._instrument is None:
                try:
                    self._open()
                except Exception:
                    log.warning("[%s] Cannot open Modbus %s, retrying in 5s...", self.id, self.port)
                    time.sleep(5)
                    continue

            for reg in self.config.get("registers", []):
                try:
                    raw = self._instrument.read_register(
                        reg["address"], number_of_decimals=0, functioncode=3
                    )
                    value = raw * float(reg.get("scale", 1.0))
                    self.mqtt.publish(reg["topic"], str(value))
                except Exception:
                    log.exception("[%s] Register read error @ 0x%04x", self.id, reg["address"])

            self._stop_event.wait(self.poll_interval)
