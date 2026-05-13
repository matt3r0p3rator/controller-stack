"""
Serial driver — communicates with firmware over UART/USB serial.
Supports G-code style (e.g. Klipper serial, Marlin, custom) and
raw/JSON-lines protocols.
"""
import logging
import time
import serial

from bridge.drivers.base_driver import BaseDriver

log = logging.getLogger("driver.serial")


class SerialDriver(BaseDriver):
    def __init__(self, config: dict, mqtt):
        super().__init__(config, mqtt)
        self.port = config["port"]
        self.baud = int(config.get("baud", 115200))
        self.protocol = config.get("protocol", "gcode")
        self._serial: serial.Serial | None = None

    def _open(self):
        self._serial = serial.Serial(self.port, self.baud, timeout=1)
        log.info("[%s] Opened serial port %s @ %d baud", self.id, self.port, self.baud)

    def send_command(self, command: str) -> str | None:
        if self._serial is None or not self._serial.is_open:
            log.warning("[%s] Serial not open, cannot send: %s", self.id, command)
            return None
        try:
            self._serial.write((command.strip() + "\n").encode())
            self._serial.flush()
            response = self._serial.readline().decode(errors="replace").strip()
            log.debug("[%s] >> %s  << %s", self.id, command, response)
            return response
        except serial.SerialException:
            log.exception("[%s] Serial write failed", self.id)
            return None

    def _request_sensors(self) -> dict:
        """
        Request sensor readings. For G-code firmware: M105 returns temperatures.
        Override for custom protocols.
        """
        readings = {}
        if self.protocol == "gcode":
            response = self.send_command("M105")  # Report temperatures
            if response:
                readings.update(self._parse_m105(response))
        return readings

    @staticmethod
    def _parse_m105(line: str) -> dict:
        """Parse 'ok T:25.2 /0.0 B:24.8 /0.0 ...' into a flat dict."""
        result = {}
        for token in line.split():
            if ":" in token:
                key, _, val = token.partition(":")
                val = val.split("/")[0]  # strip target temp
                try:
                    result[key] = float(val)
                except ValueError:
                    pass
        return result

    def _poll_loop(self):
        while not self._stop_event.is_set():
            if self._serial is None:
                try:
                    self._open()
                except serial.SerialException:
                    log.warning("[%s] Cannot open %s, retrying in 5s...", self.id, self.port)
                    time.sleep(5)
                    continue

            try:
                readings = self._request_sensors()
                sensor_map = self.config.get("sensors", {})
                for mcu_key, topic in sensor_map.items():
                    if mcu_key in readings:
                        self.mqtt.publish(topic, str(readings[mcu_key]))
                # Publish raw readings as JSON for convenience
                if readings:
                    self.mqtt.publish(f"mcu/raw/{self.id}", readings)
            except Exception:
                log.exception("[%s] Poll error, reopening serial.", self.id)
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None

            self._stop_event.wait(self.poll_interval)

        if self._serial and self._serial.is_open:
            self._serial.close()
