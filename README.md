# Dreame Wet & Dry Vacuum — Home Assistant integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration for **Dreame wet & dry stick vacuums**, tested with the **Dreame H14 Pro** (`dreame.hold.w2306e`) and **H15 Mix** (`dreame.hold.w2506`).

It connects to the Dreame cloud, authenticates with your Dreame account, and exposes the device's status, statistics, consumables, alerts and settings as Home Assistant entities. Live state updates are delivered through the cloud **MQTT push** feed, with a periodic web poll as a fallback.

> ⚠️ This is an **unofficial** integration. It is not affiliated with, endorsed by, or supported by Dreame. Use at your own risk. The cloud API is undocumented and may change at any time.

---

## Features

This is a *wet & dry stick* vacuum (not a robot), so there is **no `vacuum` entity**. Instead the integration exposes the device through standard entity platforms:

### Sensors
- **State** — current activity (mopping, drying, self-cleaning, charging, …)
- **Battery** level (%)
- **Washing / drying progress** levels (real-time, MQTT only)
- **Totals & history** — total run time, total clean count, last clean time and duration, self-clean / self-dry totals (diagnostic)
- **Consumables** — front/back roller brushes and filter: hours remaining, with % and minutes as attributes
- **Water level** and **suction mode**

### Binary sensors (alerts)
- Clean-water tank empty
- Detergent empty
- Dirty-water tank full / missing / needs cleaning
- Self-cleaning recommended (dirty brush/tube)
- Auto-detergent state

### Switches
- Light, auto detergent mixing, automatic rinse, automatic drying, timed dry after cleaning, custom mode

### Numbers
- Voice volume, timed-dry duration, and custom-mode settings (suction power, water flow, brush speed)

### Selects
- Traction force (light / balanced / strong)

### Buttons
- Start self-cleaning
- Start self-drying

> Some controls are *optimistic*: the device does not report their current value back, so the entity reflects the last command you sent.

Entity names are translated (English and French) and follow your Home Assistant UI language.

### H15 Mix support

The H15 Mix exposes a smaller, model-specific set of entities: charging/activity state, battery, washing and drying progress, cleaning count and last-clean information, and the consumable readings observed on this model. Its state codes use Dreame's H15 Mix key definitions. On-device testing confirmed the cloud-to-Home Assistant status feed and a complete self-cleaning-to-drying transition.

Only **Start self-cleaning** is exposed as a control. It is available while the device is online and charging on its station, unless the verified **Dirty water tank full** alert is active. Before using it, fill the clean-water tank and ensure the dirty-water tank is installed and not full, as directed by the [H15 Mix manual](https://global.dreametech.com/pages/h15-mix-user-manual-1). The device can return command code `1` while still starting the cycle; the button verifies sustained activity or reports the specific full-tank error when the device pauses. The full-tank alert was observed on the H15 Mix as property `4.2` bit `4096`. After emptying and reseating the tank, the device took a few minutes to clear the cloud-reported error and re-enable the button. Other H14 Pro settings and warning-bit interpretations are deliberately not applied to the H15 Mix until verified on that model.

---

## Requirements

- Home Assistant **2025.1.0** or newer
- A **Dreame** account (the same one you use in the Dreamehome app) with your vacuum already added
- Network access from Home Assistant to the Dreame cloud (`eu`/`cn` regions supported)

Python dependencies (`pycryptodome`, `paho-mqtt`) are installed automatically by Home Assistant from the integration's `manifest.json`.

---

## Installation

### Option A — HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. In Home Assistant go to **HACS → Integrations → ⋮ (top-right) → Custom repositories**.
3. Add this repository:
   - **Repository:** `https://github.com/morcus/dreame-wet-dry-vacuum-home-assistant`
   - **Category:** `Integration`
4. Find **Dreame Wet & Dry Vacuum** in the HACS list and click **Download**.
5. **Restart Home Assistant.**

Once this repository is published to the [HACS default store](https://hacs.xyz/docs/publish/include), steps 2–3 will no longer be needed — it will be searchable directly in HACS.

### Option B — Manual

1. Copy the folder `custom_components/dreame_wet_dry_vacuum/` into your Home Assistant `config/custom_components/` directory.
2. **Restart Home Assistant.**

---

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Dreame Wet & Dry Vacuum**.
3. Enter your **Dreame account email**, **password**, and **region** (`Europe` or `China / Asia`).
4. If your account has more than one device, pick the vacuum you want to add.

The integration creates one device with all of its entities. State is updated in real time via MQTT, with a web poll every 5 minutes as a safety net.

---

## HACS compatibility — what's required & what's done

For reference, here is the checklist HACS uses to validate a custom **integration** repository, and how this project meets it.

| Requirement | Status | Notes |
|---|---|---|
| Integration lives in `custom_components/<domain>/` | ✅ | `custom_components/dreame_wet_dry_vacuum/` |
| `manifest.json` with `domain`, `name`, `version` | ✅ | required for custom integrations |
| `manifest.json` `documentation` URL | ✅ | points to this repository |
| `manifest.json` `issue_tracker` URL | ✅ | points to the GitHub issues page |
| `manifest.json` `codeowners` | ✅ | `["@morcus"]` |
| `hacs.json` in repository root | ✅ | `name`, `content_in_root: false`, `render_readme`, `homeassistant` |
| `README.md` in repository root | ✅ | this file (`render_readme: true`) |
| `LICENSE` in repository root | ✅ | The Unlicense (public domain) |
| CI validation (HACS Action + hassfest) | ✅ | `.github/workflows/validate.yml` |
| Brand assets (`brand/icon.png`) | ✅ | local **placeholder** icon — see note below |
| Repository is **public** on GitHub | ✅ | set to *Public* |
| GitHub repository **description** is set | ✅ | set in the repo's *About* section |
| GitHub repository **topics** | ✅ | `home-assistant`, `hacs`, `dreame`, `vacuum`, … |
| At least one **release / tag** | ✅ | [`v0.1.0`](https://github.com/morcus/dreame-wet-dry-vacuum-home-assistant/releases/tag/v0.1.0) |

> **Brand icon note:** `custom_components/dreame_wet_dry_vacuum/brand/icon.png` is a neutral, generated **placeholder** (a generic water-drop glyph) so the HACS *brands* check passes. It is **not** the Dreame logo. Replace it with a logo you have the rights to use, or — the recommended route — register the integration in the [home-assistant/brands](https://github.com/home-assistant/brands) repository, which both Home Assistant and HACS pick up automatically.

### Optional: getting into the default HACS store

To make the integration installable without adding it as a custom repository, submit it to the [HACS default repositories](https://hacs.xyz/docs/publish/include):

1. Ensure all ✅/⬜ items above are satisfied (public repo, description, topics, a release, and a passing structure).
2. Run the [HACS Action](https://github.com/hacs/action) and the [hassfest](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) checks in CI (recommended — see below).
3. Open a PR against [`hacs/default`](https://github.com/hacs/default) adding your repository.

### Recommended: validation workflows

Add GitHub Actions so HACS and Home Assistant structure are validated on every push. Create `.github/workflows/validate.yml`:

```yaml
name: Validate

on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"

jobs:
  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration

  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master
```

---

## Development

Unit tests (no Home Assistant install required) and linting:

```bash
pip install pytest ruff aiohttp pycryptodome "paho-mqtt>=2.0"
pytest
ruff check custom_components tests
```

Both run in CI on every push, alongside the HACS and hassfest validations.

---

## Versioning

The integration version lives in `custom_components/dreame_wet_dry_vacuum/manifest.json`. When you publish a new GitHub release, bump that version to match the release tag so HACS can track updates.

---

## Troubleshooting

- **`invalid_auth`** — wrong email/password, or wrong region. Make sure you can sign in to the Dreamehome app with the same credentials.
- **`cannot_connect`** — Home Assistant cannot reach the Dreame cloud; check connectivity and the selected region.
- **`no_devices`** — the account has no compatible device. Confirm the vacuum is added to that Dreame account.
- Enable debug logging to investigate:

  ```yaml
  logger:
    default: warning
    logs:
      custom_components.dreame_wet_dry_vacuum: debug
  ```

---

## Disclaimer

This project is provided "as is", without warranty of any kind. It uses an unofficial, reverse-engineered cloud API and may break at any time if Dreame changes their service. Credentials are stored by Home Assistant and used only to talk to the Dreame cloud.

---

## License

Released into the **public domain** under [The Unlicense](LICENSE). Do whatever you want with it — copy, modify, publish, sell, fork — no attribution required.
