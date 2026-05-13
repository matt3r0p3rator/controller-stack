"""
controller-stack — Process Controller Core
==========================================
Entry point. Starts the FastAPI app, loads the active process profile,
connects to MQTT and InfluxDB, and runs the control loop.
"""
import asyncio
import logging
import os
import signal

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.settings import Settings
from app.mqtt_client import MQTTClient
from app.influx_writer import InfluxWriter
from app.profile_loader import load_profile
from app.controller import ProcessController
from app.api import router

log = logging.getLogger("controller")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    logging.basicConfig(level=settings.log_level)

    log.info("Starting controller — profile: %s", settings.profile)

    mqtt = MQTTClient(settings)
    influx = InfluxWriter(settings)
    profile = load_profile(settings.profile)

    controller = ProcessController(
        settings=settings,
        mqtt=mqtt,
        influx=influx,
        profile=profile,
    )

    app.state.controller = controller

    loop = asyncio.get_event_loop()
    task = loop.create_task(controller.run())

    # Graceful shutdown
    def _shutdown(*_):
        task.cancel()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    await controller.stop()
    log.info("Controller stopped.")


app = FastAPI(
    title="Industrial Process Controller",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api")
