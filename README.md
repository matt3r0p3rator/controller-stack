# controller-stack

A local, fully open-source Docker stack for programmable industrial process control.
Ships with an example **electrolysis cell** profile — swap in your own profile for any process.

---

## Architecture

```
Browser / REST client
        │
     [Nginx :80]  ─── reverse proxy
        ├── /grafana/   → Grafana :3000   (dashboards)
        ├── /nodered/   → Node-RED :1880  (visual flow programming)
        └── /api/       → Controller :8000 (REST API)

[Controller (Python/FastAPI)]
  ↕ MQTT  ←→  [Mosquitto :1883 / :9001]  ←→  [MCU Bridge (Python)]
  ↕ InfluxDB                                         ↕ Serial / Klipper / Modbus
[InfluxDB :8086]                               [External MCU]
                                               (3D printer board, power supply, …)
```

| Service       | Image / Source                 | Purpose                                          |
|---------------|-------------------------------|--------------------------------------------------|
| mosquitto     | eclipse-mosquitto:2           | MQTT message bus                                 |
| influxdb      | influxdb:2.7                  | Time-series process data storage                 |
| grafana       | grafana/grafana-oss           | Real-time and historical dashboards              |
| nodered       | nodered/node-red              | Visual flow / sequence programming               |
| controller    | ./services/controller         | Control loop, profile engine, REST API           |
| mcu-bridge    | ./services/mcu-bridge         | Serial / Moonraker / Modbus MCU communication    |
| nginx         | nginx:alpine                  | Reverse proxy, single-port entry point           |

---

## Quick Start

### 1. Clone & configure

```bash
git clone <this-repo>
cd controller-stack
cp .env.example .env
# Edit .env — change passwords and tokens before exposing to a network
```

### 2. Configure your MCU

Edit `config/mcu-bridge/mcu.yml`. By default it expects a G-code serial device at `/dev/ttyUSB0`.

Adjust the `devices:` list in `docker-compose.yml` to match your system:
```yaml
devices:
  - /dev/ttyACM0:/dev/ttyACM0   # e.g. Klipper / Marlin USB
```

For a **Klipper/Moonraker** setup, uncomment the `klipper` entry in `mcu.yml` and point `moonraker_url` at your host.

### 3. Start the stack

```bash
docker compose up -d
```

### 4. Open the UI

| Interface  | URL                        |
|------------|---------------------------|
| Grafana    | http://localhost/grafana/  |
| Node-RED   | http://localhost/nodered/  |
| API docs   | http://localhost/api/docs  |
| InfluxDB   | http://localhost:8086      |

Default credentials are in `.env` (`admin` / `changeme123`) — **change them**.

---

## Controller API

Base URL: `http://localhost/api`

| Method | Path           | Description                    |
|--------|---------------|--------------------------------|
| GET    | `/state`       | Current process state snapshot |
| POST   | `/command`     | Send a command to the profile  |
| GET    | `/health`      | Liveness check                 |
| GET    | `/docs`        | Auto-generated OpenAPI UI      |

### Example commands (electrolysis profile)

```bash
# Start the electrolysis cell
curl -X POST http://localhost/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "start"}'

# Stop
curl -X POST http://localhost/api/command \
  -d '{"command": "stop"}'

# Emergency stop
curl -X POST http://localhost/api/command \
  -d '{"command": "estop"}'

# Adjust target current setpoint
curl -X POST http://localhost/api/command \
  -d '{"command": "set_param", "params": {"target_current": 8.0}}'
```

You can also publish commands directly to MQTT topic `controller/command`:
```json
{"command": "start"}
```

---

## MQTT Topics

| Topic                          | Direction         | Description                           |
|-------------------------------|-------------------|---------------------------------------|
| `controller/state`            | controller → bus  | Full state JSON every loop tick       |
| `controller/command`          | bus → controller  | Send commands to the active profile   |
| `controller/alarm`            | controller → bus  | Alarm events                          |
| `mcu/sensor/<id>/<name>`      | bridge → bus      | Individual sensor values              |
| `mcu/raw/<id>`                | bridge → bus      | Full raw sensor JSON from MCU         |
| `mcu/output/<channel>`        | bus → bridge      | Output commands to MCU channels       |

---

## Writing a Custom Profile

1. Copy `profiles/electrolysis.py` to `profiles/<your_process>.py`.
2. Edit the sensor topics, setpoints, `tick()` logic, and commands.
3. Set `CONTROLLER_PROFILE=<your_process>` in `.env`.
4. Restart: `docker compose restart controller`

A profile must implement `BaseProfile` (`services/controller/app/base_profile.py`):

```python
class Profile(BaseProfile):
    def setup(self, mqtt, influx, config): ...   # subscribe to sensors
    async def tick(self): ...                     # control logic, runs every second
    def get_state(self) -> ProfileState: ...      # return state snapshot
    def on_command(self, command, params): ...    # handle commands (optional)
    def teardown(self): ...                       # cleanup on shutdown (optional)
```

---

## Supported MCU Types

| Type      | How it works                                    | Config key      |
|-----------|-------------------------------------------------|-----------------|
| `serial`  | G-code or raw bytes over UART/USB serial        | `type: serial`  |
| `klipper` | Moonraker HTTP REST API                         | `type: klipper` |
| `modbus`  | Modbus RTU over serial (registers + coils)      | `type: modbus`  |

See `config/mcu-bridge/mcu.yml` for full example configuration of each type.

---

## Security Notes

- Change all default passwords and the InfluxDB token in `.env` before running on any shared network.
- Mosquitto is configured with `allow_anonymous true` by default (local lab use).
  Enable password auth by editing `config/mosquitto/mosquitto.conf`.
- The `mcu-bridge` container runs `privileged: true` for serial port access.
  Scope it down to only the required `devices:` entries.
- Node-RED editor is enabled by default. Set `NODERED_EDITOR=false` to disable in `.env`.
