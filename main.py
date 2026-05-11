import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from mcrcon import MCRcon
from pydantic import BaseModel


load_dotenv()

CONFIG_PATH = Path("config.json")
ACTIVE_INSTANCE_FILE = Path("active-instance.txt")
TOKEN = os.getenv("HEIMDALL_TOKEN")
AuthHeader = Annotated[str | None, Header()]
JsonObject = dict[str, Any]
UNAUTHORIZED_DETAIL = "Unauthorized"
RCON_UNAVAILABLE_DETAIL = "RCON is not available"
UNAUTHORIZED_RESPONSE = {
    401: {"description": UNAUTHORIZED_DETAIL},
}
SERVER_ALREADY_RUNNING_RESPONSE = {
    **UNAUTHORIZED_RESPONSE,
    409: {"description": "A Minecraft server already appears to be running"},
}
RCON_UNAVAILABLE_RESPONSE = {
    **UNAUTHORIZED_RESPONSE,
    409: {"description": RCON_UNAVAILABLE_DETAIL},
}
MINECRAFT_RUNNING_RESPONSE = {
    **UNAUTHORIZED_RESPONSE,
    409: {"description": "Minecraft appears to be running. Stop the server first."},
}

if not TOKEN:
    raise RuntimeError("Missing HEIMDALL_TOKEN in .env")


def load_config() -> JsonObject:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


config = load_config()
app = FastAPI(title="Heimdall Agent", version="0.1.0")


class StartRequest(BaseModel):
    instance: str


class StopRequest(BaseModel):
    shutdown_after: bool = False


class RconRequest(BaseModel):
    command: str


def read_active_instance() -> str | None:
    if not ACTIVE_INSTANCE_FILE.exists():
        return None

    active_instance = ACTIVE_INSTANCE_FILE.read_text(encoding="utf-8").strip()

    if not active_instance:
        return None

    if active_instance not in config["instances"]:
        return None

    return active_instance


def write_active_instance(instance_id: str) -> None:
    ACTIVE_INSTANCE_FILE.write_text(instance_id, encoding="utf-8")


def clear_active_instance() -> None:
    ACTIVE_INSTANCE_FILE.unlink(missing_ok=True)


def require_auth(authorization: str | None) -> None:
    expected = f"Bearer {TOKEN}"

    if authorization != expected:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_minecraft_online() -> bool:
    mc = config["minecraft"]
    return is_port_open("127.0.0.1", int(mc["server_port"]))


def is_rcon_online() -> bool:
    mc = config["minecraft"]
    return is_port_open(mc["rcon_host"], int(mc["rcon_port"]))


def send_rcon(command: str) -> str:
    mc = config["minecraft"]

    with MCRcon(
        host=mc["rcon_host"],
        password=mc["rcon_password"],
        port=int(mc["rcon_port"]),
    ) as rcon_connection:
        response = rcon_connection.command(command)

    return response


def run_shutdown(delay_seconds: int = 60) -> None:
    subprocess.Popen(
        [
            "shutdown",
            "/s",
            "/t",
            str(delay_seconds),
            "/c",
            "Minecraft host shutdown requested by Heimdall Agent.",
        ],
        shell=False,
    )


def cancel_shutdown() -> None:
    subprocess.Popen(["shutdown", "/a"], shell=False)


@app.get("/")
def root() -> JsonObject:
    return {
        "service": "heimdall-agent",
        "status": "running",
    }


@app.get("/instances", responses=UNAUTHORIZED_RESPONSE)
def instances(authorization: AuthHeader = None) -> JsonObject:
    require_auth(authorization)

    return {
        "instances": [
            {
                "id": instance_id,
                "name": instance["name"],
            }
            for instance_id, instance in config["instances"].items()
        ]
    }


@app.get("/status", responses=UNAUTHORIZED_RESPONSE)
def status(authorization: AuthHeader = None) -> JsonObject:
    require_auth(authorization)

    minecraft_online = is_minecraft_online()
    active_instance = read_active_instance() if minecraft_online else None

    if not minecraft_online:
        clear_active_instance()

    return {
        "minecraft_online": minecraft_online,
        "rcon_online": is_rcon_online(),
        "server_port": config["minecraft"]["server_port"],
        "rcon_port": config["minecraft"]["rcon_port"],
        "active_instance": active_instance,
    }


@app.post("/start", responses=SERVER_ALREADY_RUNNING_RESPONSE)
def start_server(
    request: StartRequest,
    authorization: AuthHeader = None,
) -> JsonObject:
    require_auth(authorization)

    if request.instance not in config["instances"]:
        raise HTTPException(status_code=404, detail="Unknown instance")

    if is_minecraft_online():
        raise HTTPException(
            status_code=409,
            detail="A Minecraft server already appears to be running",
        )

    instance = config["instances"][request.instance]
    script = Path(instance["start_script"])
    working_dir = Path(instance["working_dir"])

    if not script.exists():
        raise HTTPException(status_code=500, detail=f"Start script not found: {script}")

    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        cwd=str(working_dir),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    write_active_instance(request.instance)

    return {
        "message": f"Starting instance {request.instance}",
        "instance": request.instance,
    }


@app.post("/stop", responses=RCON_UNAVAILABLE_RESPONSE)
def stop_server(
    request: StopRequest,
    authorization: AuthHeader = None,
) -> JsonObject:
    require_auth(authorization)

    if not is_rcon_online():
        raise HTTPException(status_code=409, detail=RCON_UNAVAILABLE_DETAIL)

    send_rcon("say Server will shut down in 10 seconds.")
    send_rcon("save-all")

    time.sleep(10)

    send_rcon("stop")
    clear_active_instance()

    if request.shutdown_after:
        time.sleep(15)
        run_shutdown(delay_seconds=60)

    return {
        "message": "Stop command sent",
        "shutdown_after": request.shutdown_after,
    }


@app.post("/rcon", responses=RCON_UNAVAILABLE_RESPONSE)
def rcon(
    request: RconRequest,
    authorization: AuthHeader = None,
) -> JsonObject:
    require_auth(authorization)

    command = request.command.strip()

    if not command:
        raise HTTPException(status_code=422, detail="Command must not be empty")

    if not is_rcon_online():
        raise HTTPException(status_code=409, detail=RCON_UNAVAILABLE_DETAIL)

    response = send_rcon(command)

    return {
        "command": command,
        "response": response,
    }


@app.get("/logs", responses=UNAUTHORIZED_RESPONSE)
def logs(
    lines: Annotated[int, Query()] = 50,
    authorization: AuthHeader = None,
) -> JsonObject:
    require_auth(authorization)

    if not is_minecraft_online():
        raise HTTPException(status_code=409, detail="No active instance known")

    active_instance = read_active_instance()

    if active_instance is None:
        raise HTTPException(status_code=409, detail="No active instance known")

    requested_lines = max(1, min(lines, 200))
    instance = config["instances"][active_instance]
    latest_log = Path(instance["working_dir"]) / "logs" / "latest.log"

    if not latest_log.exists():
        raise HTTPException(status_code=404, detail="latest.log not found")

    with latest_log.open("r", encoding="utf-8", errors="replace") as f:
        log_lines = f.readlines()

    return {
        "lines": requested_lines,
        "log": "".join(log_lines[-requested_lines:]),
    }


@app.post("/say", responses=RCON_UNAVAILABLE_RESPONSE)
def say(
    message: str,
    authorization: AuthHeader = None,
) -> JsonObject:
    require_auth(authorization)

    if not is_rcon_online():
        raise HTTPException(status_code=409, detail=RCON_UNAVAILABLE_DETAIL)

    response = send_rcon(f"say {message}")

    return {
        "message": message,
        "response": response,
    }


@app.get("/players", responses=RCON_UNAVAILABLE_RESPONSE)
def players(authorization: AuthHeader = None) -> JsonObject:
    require_auth(authorization)

    if not is_rcon_online():
        raise HTTPException(status_code=409, detail=RCON_UNAVAILABLE_DETAIL)

    response = send_rcon("list")

    return {
        "response": response,
    }


@app.post("/shutdown-host", responses=MINECRAFT_RUNNING_RESPONSE)
def shutdown_host(authorization: AuthHeader = None) -> JsonObject:
    require_auth(authorization)

    if is_minecraft_online():
        raise HTTPException(
            status_code=409,
            detail="Minecraft appears to be running. Stop the server first.",
        )

    run_shutdown(delay_seconds=60)

    return {
        "message": "Host shutdown scheduled in 60 seconds",
    }


@app.post("/cancel-shutdown", responses=UNAUTHORIZED_RESPONSE)
def cancel_host_shutdown(authorization: AuthHeader = None) -> JsonObject:
    require_auth(authorization)

    cancel_shutdown()

    return {
        "message": "Shutdown cancelled",
    }
