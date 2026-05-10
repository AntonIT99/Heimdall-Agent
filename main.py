import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from mcrcon import MCRcon
from pydantic import BaseModel


load_dotenv()

CONFIG_PATH = Path("config.json")
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
    ) as rcon:
        response = rcon.command(command)

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

    return {
        "minecraft_online": is_minecraft_online(),
        "rcon_online": is_rcon_online(),
        "server_port": config["minecraft"]["server_port"],
        "rcon_port": config["minecraft"]["rcon_port"],
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

    if request.shutdown_after:
        time.sleep(15)
        run_shutdown(delay_seconds=60)

    return {
        "message": "Stop command sent",
        "shutdown_after": request.shutdown_after,
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
