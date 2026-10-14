# Dyson Lightcycle Morph — Home Assistant Integration (HACS)

A native **Home Assistant integration** to control the **Dyson Lightcycle Morph lamp** (Desk 552 / Floor 520 / 427) over Bluetooth Low Energy (BLE) — no Dyson cloud required.

This is a HACS-friendly re-implementation of the reverse-engineered CLI/BLE code in the sibling `dyson` project. It runs **inside Home Assistant** as a custom component (no external daemon needed) and is installable via **HACS**.

## Features

- **Light entity** — power on/off, brightness (100–1000 lm), color temperature (2700–6500 K)
- **Preset modes** as a select: Synchronised (solar/circadian), Study, Relax, Precision
- **Switches** for the ambient-light auto-brightness sensor and the PIR movement sensor
- **Buttons** for the sunrise wake-up routine and solar-location sync
- **Two connection modes**, switchable in the integration options:
  - **Persistent (default)** — keeps the BLE connection open continuously for lowest latency.
  - **App-compatible** — connects only while an action runs, then disconnects after ~90 s of inactivity so the official Dyson app can claim the connection when you need it.
- **BLE authentication** — full HKDF-SHA256 / AES-CBC / HMAC challenge-response handshake
- **Config flow UI** — enter your serial, BLE address, Dyson user id and LTK in the HA UI
- Local dawn/wake-up ramp and solar-location sync as services and buttons

> **Note:** BLE runs on the Home Assistant host itself. Your HA machine needs a working Bluetooth adapter that can reach the lamp. (Use the integration `esphome` / `bluetooth` alongside; the lamp just needs to be BLE-visible.)

## Installation via HACS

1. This repository must be a GitHub repo. Install **HACS**, then
   **HACS → Integrations → ⋮ → Custom repositories**, add `https://github.com/<your-github-user>/<this-repo>` with category **Integration**.
2. A new **Dyson Lightcycle Morph** entry appears under "Integrations". Download it.
3. Restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Dyson Lightcycle Morph**.
5. Enter:
   - **Serial** (e.g. `E5T-EU-...`)
   - **BLE address** (MAC on Linux/RPi, UUID on macOS) — or leave empty to auto-scan by serial
   - **User ID** and **LTK** (32 hex chars) from your Dyson cloud account
   - **Connection mode** (Persistent or App-compatible)
6. The integration connects/authenticates to verify the settings, then adds the light, select, switches and buttons.

### Switching the connection mode later

The connection mode can be changed anytime without reinstalling via
**Settings → Devices & Services → *entry* → Options** (select Persistent or App-compatible). The entry reloads automatically.


## Getting your Dyson User ID and LTK

These come from your own Dyson account (from the reverse-engineering work in the `dyson` project, e.g. via `dyson.tool` cloud utilities). They are private — store them in the config entry, which is encrypted by Home Assistant.

## Services

- `dyson_lamp.sync_location` — push GPS lat/lon, timezone and time to the lamp.
- `dyson_lamp.set_wakeup` — run the sunrise wake-up ramp (`duration`, `lumens`, `kelvin`).

## Development layout

```
custom_components/dyson_lamp/
├── __init__.py        # setup/unload, device registry, services
├── connection.py      # ConnectionManager (persistent / app-compatible modes)
├── config_flow.py     # BLE credential entry + options flow (mode switch)
├── const.py           # constants
├── lamp.py            # BLE authentication + GATT control (LampClient)
├── light.py           # main light entity + polling coordinator
├── select.py          # preset-mode select
├── switch.py          # auto-brightness & movement switches
├── button.py          # wake-up & solar-sync buttons
├── services.yaml      # service definitions
├── strings.json       # config flow strings
└── translations/en.json
hacs.json
```

## License

Reverse-engineering notes/code for personal use. Use at your own risk.
