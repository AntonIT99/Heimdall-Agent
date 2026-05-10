# Heimdall Agent

Heimdall Agent is a lightweight Windows-based Minecraft server control service designed for home infrastructure setups.

It is intended to run locally on the Minecraft host machine and later integrate with a Discord bot running on another system (for example a Raspberry Pi).

The agent provides:

- Minecraft server lifecycle management
- RCON-based remote control
- Clean server shutdown and saving
- Host shutdown support
- Simple HTTP API for automation
- Wake-on-LAN compatible infrastructure

---

# Features

## Current Features

- Start Minecraft server instances
- Stop Minecraft servers cleanly using RCON
- Save worlds before shutdown
- Send chat messages through RCON
- Query online players
- Host shutdown scheduling
- Token-based API authentication
- Config-based server instance management

## Planned Features

- Discord bot integration
- Automatic Wake-on-LAN startup
- Server status embeds
- Player monitoring
- Automatic idle shutdown
- Multi-instance orchestration
- Startup/shutdown notifications
- Metrics and logging

---

# Architecture

```text
Discord Bot (Raspberry Pi)
            ↓
     Heimdall Agent
        (Windows)
            ↓
       Minecraft
```

The Raspberry Pi acts as the permanent control center.

The Windows machine hosts Minecraft and runs Heimdall Agent locally.

---

# Requirements

- Windows 10/11
- Python 3.13+
- Java Minecraft server with RCON enabled

---

# Installation

## Clone repository

```bash
git clone https://github.com/YOUR_USERNAME/heimdall-agent.git
cd heimdall-agent
```

---

## Create virtual environment (recommended)

```powershell
python -m venv .venv
```

Activate:

```powershell
.venv\Scripts\activate
```

---

## Install dependencies

```powershell
pip install -r requirements.txt
```

---

# Configuration

## Create config files

Copy:

```text
config.json.example -> config.json
.env.example -> .env
```

---

## Configure `.env`

```env
HEIMDALL_TOKEN=change-this-secret-token
```

---

## Configure `config.json`

Example:

```json
{
  "host": "0.0.0.0",
  "port": 9090,
  "minecraft": {
    "rcon_host": "127.0.0.1",
    "rcon_port": 25575,
    "rcon_password": "CHANGE_ME",
    "server_port": 25565
  },
  "instances": {
    "cobblemon": {
      "name": "Cobblemon",
      "start_script": "C:\\Games\\Minecraft Servers\\Cobblemon\\start.bat",
      "working_dir": "C:\\Games\\Minecraft Servers\\Cobblemon"
    }
  }
}
```

---

# Minecraft RCON Setup

In your `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=YOUR_PASSWORD
```

Restart the Minecraft server afterwards.

---

# Running the Agent

```powershell
uvicorn main:app --host 0.0.0.0 --port 9090
```

---

# API Authentication

All protected endpoints require:

```http
Authorization: Bearer YOUR_TOKEN
```

---

# API Endpoints

## Status

```http
GET /status
```

---

## List Instances

```http
GET /instances
```

---

## Start Server

```http
POST /start
```

Body:

```json
{
  "instance": "cobblemon"
}
```

---

## Stop Server

```http
POST /stop
```

Body:

```json
{
  "shutdown_after": false
}
```

---

## Send Chat Message

```http
POST /say?message=Hello
```

---

## List Players

```http
GET /players
```

---

## Shutdown Host

```http
POST /shutdown-host
```

---

## Cancel Shutdown

```http
POST /cancel-shutdown
```

---

# Example Requests

## PowerShell

```powershell
curl -H "Authorization: Bearer YOUR_TOKEN" `
http://127.0.0.1:9090/status
```

---

## Start Minecraft

```powershell
curl -X POST `
http://127.0.0.1:9090/start `
-H "Authorization: Bearer YOUR_TOKEN" `
-H "Content-Type: application/json" `
-d "{\"instance\":\"cobblemon\"}"
```

---

# Security Notes

## IMPORTANT

Do NOT expose Heimdall Agent directly to the internet.

Recommended setup:

```text
Discord Bot
    ↓
Raspberry Pi
    ↓
Local network only
    ↓
Heimdall Agent
```

Recommended:

- No router port forwarding
- Local network only
- Strong RCON passwords
- Strong API token
- Discord-side permission checks

---

# Wake-on-LAN

Heimdall Agent is designed to work together with Wake-on-LAN setups.

Typical flow:

```text
Discord command
    ↓
Wake Windows host
    ↓
Wait for Heimdall Agent
    ↓
Start Minecraft
```

---

# Project Goals

Heimdall is intended to become a lightweight home infrastructure orchestration system focused on:

- Minecraft server management
- Discord integration
- Remote lifecycle control
- Automation
- Home lab orchestration

---

# License

MIT License