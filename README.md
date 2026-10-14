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
- `dyson_lamp.set_wakeup` — run the sunrise wake-up ramp (`duration` in minutes, `lumens`, `kelvin`).

## Wake-up / alarm ("Wecker")

There is **no native Home Assistant "alarm that triggers a device"** component — the built-in Alarm/Alarm Control Panel is for alarm systems, not wake-up timers. The idiomatic way in HA is a simple **automation**: a `time` trigger that calls `dyson_lamp.set_wakeup`. This repo ships a ready-made blueprint for exactly that.

1. Install the blueprint from within this integration (HACS): **Automations → Blueprints**, search **"Dyson Lightcycle Morph - Wake up with light"**.
2. Create an automation from it:
   - **Ramp start time** — when the light starts ramping up (set to your wake time minus the ramp duration, e.g. `06:30` for a `07:00` wake with a 30 min ramp).
   - **Days of week**, **Ramp duration (min)**, **Target brightness**, **Target color temperature**.
3. Save — the automation ramps the lamp from warm/dim to bright/cool each morning, just like the app's lightcycle.

The ramp (`run_wakeup`) runs approximately one update per second over the chosen duration with a gentle quadratic brightness curve and a linear color-temperature rise, then leaves the lamp on at the target settings.

### Weekly alarm with per-day times (phone friendly)

If you want **different wake times per weekday**, controllable from your phone/HA app, this repo ships a **package** file: `packages/dyson_week_alarm.yaml`.

It creates 14 helpers plus one central automation:

- 7 **switches** (`input_boolean.wake_mon` … `wake_sun`) — arm/disarm each weekday from your phone.
- 7 **date/time helpers** (`input_datetime.wake_time_mon` … `wake_time_sun`) — set a separate wake time per day.
- 1 **automation** that checks every minute and launches the ramp at the right time (the ramp finishes **at** each configured wake time).

**Install:**

1. Enable packages in HA: add `homeassistant: packages: !include_dir_named packages` (or the equivalent) to `configuration.yaml`.
2. Copy `packages/dyson_week_alarm.yaml` from this repo into your HA `packages/` folder.
3. Reload Home Assistant (Settings → System → Restart, or reload YAML). The helpers and automation appear automatically.

Then, on your phone/dashboard, toggle `wake_mon` etc. **on** to arm a day and set each `wake_time_*` helper to that day's wake-up time. The ramp `duration`/`lumens`/`kelvin` are fixed inside the file (30 min / 800 lm / 4800 K by default) — edit the YAML if you want to change them.

## Entities

Besides the light, the integration provides status sensors (updated by the poller):
- **Binary sensors**: Power (on/off), Movement Sensor (PIR)
- **Sensors**: Brightness (lm), Color Temperature (K)
- **Switch**: Auto-Brightness (Ambient Light Sensor), Movement Sensor
- **Select**: preset mode
- **Buttons**: Wake Up, Sync Solar Location

## Status polling

In **persistent** mode the lamp state (on/off, brightness, color temp) is polled every **5 seconds**, so the light entity and the status sensors stay current — e.g. if the lamp is turned via touch on the head or the Dyson app. In **app-compatible** mode polling is disabled by design so the BLE connection is not kept open; state is refreshed after each manual action.

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
├── sensor.py          # brightness & color-temp status sensors
├── binary_sensor.py   # power & movement on/off status
├── button.py          # wake-up & solar-sync buttons
├── services.yaml      # service definitions
├── strings.json       # config flow strings
└── translations/en.json
blueprints/automation/dyson_lamp/wake_up.yml   # wake-up alarm blueprint
hacs.json
```

## License

Reverse-engineering notes/code for personal use. Use at your own risk.
