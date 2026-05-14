"""
InfluxDB writer — batches data points for efficiency.
"""
import logging
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from app.settings import Settings

log = logging.getLogger("controller.influx")


class InfluxWriter:
    def __init__(self, settings: Settings):
        self._bucket = settings.influx_bucket
        self._org = settings.influx_org
        self._client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)

    def write(self, measurement: str, fields: dict, tags: dict | None = None):
        """Write a single data point."""
        point = Point(measurement)
        if tags:
            for k, v in tags.items():
                point = point.tag(k, str(v))
        for k, v in fields.items():
            point = point.field(k, v)
        point = point.time(datetime.now(timezone.utc), WritePrecision.NS)
        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
        except Exception:
            log.exception("InfluxDB write failed for measurement=%s", measurement)

    def close(self):
        self._client.close()
