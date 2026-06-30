# Tuya IR AC Remote

A Home Assistant custom integration that turns a **Tuya local-network IR
hub** (a "universal smart IR remote") into a `climate` entity for
controlling a **Panasonic** or **Carrier** air conditioner -- entirely over
your **local network**. No Tuya cloud account or internet access is
required at runtime; only `device_id` / `local_key` extracted once during
setup.

This is a private/unlisted project: it is installed via HACS as a
**custom repository** and is not, and will not be, submitted to the
official HACS store.

## How IR codes work in this integration

AC remotes are "state" protocol devices: every button press transmits the
*entire* state of the unit (mode, temperature, fan speed, swing, power),
not just a delta. This integration mirrors that -- each combination of
mode/temperature/fan/swing is looked up as one IR code and sent as a whole.

Two sources of codes, merged together (learned always wins):

1. **Built-in codesets** (`custom_components/tuya_ir_ac/codes/<brand>/*.json`)
   -- bundled for convenience. **Important:** the codesets currently
   shipped (`panasonic/generic.json`, `carrier/generic.json`) are
   placeholders generated for development/testing. They are structurally
   valid Tuya IR codes but have **not** been verified against a real
   Panasonic or Carrier remote, and are unlikely to control your AC
   correctly out of the box. Treat them as a scaffold, not a working
   codeset. Verified, brand/model-specific codesets are a great target for
   future contributions.
2. **Learn Command** -- point your actual remote at the Tuya hub and
   capture its real codes through the integration's options flow. Learned
   codes always override the built-in table for that exact combination,
   and are the only way to guarantee correctness for your specific model.

**In practice: install, add your AC unit, then immediately use Learn
Command to teach the handful of combinations you actually use** (see
below). This is the reliable path.

## Prerequisites

1. Your Tuya IR hub must already be paired in the Tuya or Smart Life app
   and reachable on your local network.
2. You need its `device_id` and `local_key`. The standard way to get these
   locally is the [`tinytuya`](https://github.com/jasonacox/tinytuya)
   command-line wizard:

   ```bash
   pip install tinytuya
   python -m tinytuya wizard
   ```

   Follow the prompts (you'll need a free Tuya IoT Platform developer
   account, linked to the same Tuya/Smart Life app account). The wizard
   writes out `devices.json` containing the `id`, `key`, and `ip` for each
   of your devices -- find your IR hub in that list.

## Installation (HACS, custom repository)

1. In Home Assistant, open **HACS**.
2. Click the **⋮** menu (top right) → **Custom repositories**.
3. Add this repository's URL, category **Integration**.
4. Find **Tuya IR AC Remote** in HACS and install it.
5. Restart Home Assistant.

## Adding an AC unit

Each Home Assistant config entry represents **one AC unit**. If you have
two AC units on the same physical Tuya hub, add the integration twice,
pointing at the same `host` / `device_id` / `local_key` both times, with a
different name.

1. **Settings → Devices & Services → Add Integration → "Tuya IR AC Remote"**.
2. Enter the hub's `host` (IP address), `device_id`, `local_key`, protocol
   version (3.3 is correct for most modern hubs), and a name for this AC
   unit.
3. Choose the brand (Panasonic / Carrier / Generic).
4. Choose a starting codeset variant (currently only `generic` is
   available per brand -- see the codeset caveat above).
5. The climate entity is created. At this point treat it as a starting
   point and follow up with Learn Command below.

## Learn Command (teaching codes from your real remote)

1. Find the AC unit's entity in **Settings → Devices & Services → Tuya IR
   AC Remote**, and click **Configure**.
2. Select which command(s) you want to (re)learn -- a short curated list
   (off, a couple of cool/heat/dry temperatures, fan-only) covers most
   day-to-day use. You can re-run this flow any time to add more.
3. For each selected command, point your real remote at the Tuya hub and
   press the matching button within the timeout. If it times out, you'll
   be prompted to try again.
4. Once done, the entity reloads automatically with your learned codes
   merged in (and taking priority over the built-in table).

If you ever issue a command that has no known code (built-in or learned),
the climate entity raises an error telling you which combination is
missing -- use Learn Command to teach exactly that one.

## Known limitations

- **Toggle-protocol AC's are not supported.** Some older AC remotes
  (e.g. classic Panasonic CKP-style units) send incremental toggle pulses
  (temp+/temp-/power-toggle/mode-cycle) rather than full state per press.
  This integration only supports "state" protocol remotes, where every
  press encodes the complete state. There's no stateful sequencing logic
  to drive a toggle remote in this version.
- **Swing is on/off only** -- no multi-position swing angle control.
- **State is optimistic.** IR blasters have no feedback channel, so the
  entity shows whatever was last commanded (restored across restarts), not
  the AC's actual confirmed state.
- **Built-in codesets are unverified placeholders** in this version (see
  above) -- Learn Command is the reliable path for now.
- This integration has not been tested against real Tuya IR hub hardware
  during development (none was available in the build environment). The
  local protocol layer (`tinytuya`) is a separately maintained, widely
  used library, and the rest of the integration is covered by unit tests
  with `tinytuya` mocked out, but real-world hub communication, IR
  transmission, and Learn Command capture need to be validated against
  actual hardware by you, the user.

## Development / testing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest tests/ -v
```
