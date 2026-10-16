# Dyson Lightcycle Morph — Weekly alarm package

This folder ships the **phone-friendly weekly wake-up alarm** for the Dyson
Lightcycle Morph. It is a Home Assistant *package* (plain YAML helpers +
automation), not part of the HACS integration, so you copy it onto your HA
host's `config/packages/` folder.

## Files

- `dyson_week_alarm.yaml` — the actual package (install this one).
- `dashboard_card.yaml` — a ready-made Lovelace card snippet (optional).

## Install

1. Enable packages in HA — in `configuration.yaml`:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
2. Copy `dyson_week_alarm.yaml` into your HA `config/packages/` folder.
3. Restart Home Assistant.

It creates, automatically:

- 7 **switches** `input_boolean.wake_mon` … `wake_sun` — armed on/off per weekday
- 7 **date/time helpers** `input_datetime.wake_time_mon` … `wake_time_sun` — wake time per day
- 1 **automation** that checks every minute and launches the lamp wake-up ramp, finishing **at** each configured time

## Control from your phone

Open the HA app → your dashboard → create an **Entities** card and add the
helpers you want, or paste the ready-made card from `dashboard_card.yaml`.

Tap a day tile to arm/disarm it and set the matching wake time. Ramp duration and target brightness are sliders in the same card. "Test sunrise" runs a 2-minute ramp, "Stop sunrise" cancels a running one.
