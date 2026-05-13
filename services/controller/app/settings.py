from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MQTT
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883

    # InfluxDB
    influx_url: str = "http://influxdb:8086"
    influx_token: str = "super-secret-token-change-me"
    influx_org: str = "controller"
    influx_bucket: str = "process"

    # Controller
    profile: str = "electrolysis"
    log_level: str = "INFO"
