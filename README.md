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

### Getting notified about updates

New versions are published as GitHub Releases (see
[RELEASING.md](RELEASING.md)). HACS checks this repo periodically and will
show an update badge -- and, if you've enabled HACS's own update
notifications, a Home Assistant notification -- as soon as a new release
is out. There's nothing extra to configure: just keep this repo added as a
custom repository in HACS.

## Adding an AC unit

Each Home Assistant config entry represents **one AC unit**. If you have
two AC units on the same physical Tuya hub, add the integration twice,
pointing at the same `host` / `device_id` / `local_key` both times, with a
different name.

1. **Settings → Devices & Services → Add Integration → "Tuya IR AC Remote"**.
2. Pick **Enter hub details manually** or **Discover via Tuya Cloud API**
   (see below for the cloud option).
3. **Manual path**: enter the hub's `host` (IP address), `device_id`,
   `local_key`, protocol version (3.3 is correct for most modern hubs), and
   a name for this AC unit.
4. Choose the brand (Panasonic / Carrier / Generic).
5. Choose a starting codeset variant (currently only `generic` is
   available per brand -- see the codeset caveat above).
6. The climate entity is created. At this point treat it as a starting
   point and follow up with Learn Command below.

### Cloud-assisted setup (optional)

Instead of manually running `tinytuya wizard` and copy-pasting
`device_id`/`local_key`, you can authenticate once with your Tuya Cloud API
credentials and pick your hub from a fetched device list:

1. Create a **Cloud Development** project on the
   [Tuya IoT Platform](https://iot.tuya.com), link it to the same Tuya/Smart
   Life app account your hub is paired to, and note its **Access ID** and
   **Access Secret**. Tuya's free trial projects expire after about a year --
   if cloud lookup suddenly stops authenticating, check
   iot.tuya.com and renew/re-link the project's Cloud Development service.
2. In the config flow, pick **Discover via Tuya Cloud API**, enter the
   Access ID/Secret and your account's region (`cn`, `us`, `us-e`, `eu`,
   `eu-w`, `in`, or `sg`).
3. Pick which device is your physical IR hub from the list. If that hub has
   other devices registered under it in the Tuya cloud, you'll be offered a
   list of those too -- picking one only prefills a friendly name and, if
   the product name mentions it, a brand guess. **It never changes which
   physical device gets contacted** -- IR is always sent to the hub you
   picked in the previous step, using its own `device_id`/`local_key`.
4. The Cloud API has no visibility into your local network, so you'll still
   enter the hub's LAN IP address manually at this point.
5. Continue with brand/variant selection as normal.

Your Access ID/Secret are saved in this config entry (same plain storage
Home Assistant already uses for `local_key`, i.e. `.storage/core.config_entries`
protected only by OS file permissions -- not some special encrypted vault)
so that adding another AC unit later can reuse them without re-entering.
**This is setup-time only** -- once the entry is created, the integration
never talks to the Tuya Cloud again; all runtime IR send/learn stays local.

Not implemented (possible future additions, not attempted here): automatic
LAN IP discovery for the selected hub, and an options-flow UI to edit/rotate
saved cloud credentials after the entry is created.

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
- **Cloud-assisted discovery is also unverified against a real Tuya Cloud
  account** in this build environment (no credentials were available) --
  automated tests fully mock the Tuya Cloud API. Whether `getdevices()`
  actually returns a working `local_key` for your specific hub/account/
  project type needs to be confirmed by you; if the returned key doesn't
  work, use the manual path or Learn Command instead.
- No automatic LAN IP discovery for a cloud-selected hub, and no options-flow
  UI (yet) to edit/rotate saved Tuya Cloud credentials after setup.

## Development / testing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest tests/ -v
```
