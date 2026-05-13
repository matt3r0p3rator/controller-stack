"""
MCU Bridge — main entry point.
Loads mcu.yml, spins up a driver per MCU, connects to MQTT.
"""
import logging
import os
import signal
import time

import yaml

from bridge.mqtt_client import MQTTClient
from bridge.drivers.serial_driver import SerialDriver
from bridge.drivers.klipper_driver import KlipperDriver
from bridge.drivers.modbus_driver import ModbusDriver

log = logging.getLogger("mcu-bridge")

CONFIG_PATH = os.environ.get("MCU_CONFIG", "/app/config/mcu.yml")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


DRIVER_MAP = {
    "serial":  SerialDriver,
    "klipper": KlipperDriver,
    "modbus":  ModbusDriver,
}


def main():
    logging.basicConfig(level=LOG_LEVEL)
    cfg = load_config(CONFIG_PATH)

    mqtt_host = os.environ.get("MQTT_HOST", "mosquitto")
    mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))
    mqtt = MQTTClient(mqtt_host, mqtt_port)

    drivers = []
    for mcu_cfg in cfg.get("mcus", []):
        mcu_type = mcu_cfg.get("type", "serial")
        driver_cls = DRIVER_MAP.get(mcu_type)
        if driver_cls is None:
            log.warning("Unknown MCU type '%s' for id '%s', skipping.", mcu_type, mcu_cfg.get("id"))
            continue
        driver = driver_cls(mcu_cfg, mqtt)
        driver.start()
        drivers.append(driver)
        log.info("Started driver: %s (%s)", mcu_cfg.get("id"), mcu_type)

    if not drivers:
        log.warning("No MCU drivers configured. Bridge is idle.")

    stop = False

    def _shutdown(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while not stop:
        time.sleep(1)

    for driver in drivers:
        driver.stop()
    mqtt.stop()
    log.info("MCU bridge stopped.")


if __name__ == "__main__":
    main()
