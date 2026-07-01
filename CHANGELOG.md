# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
correspond to `custom_components/tuya_ir_ac/manifest.json`'s `version` and
to the `vX.Y.Z` GitHub Release tag (see [RELEASING.md](RELEASING.md)).

## [0.1.1-alpha-02]
- Add a `panasonic/cs_yu18zkt` built-in codeset variant (placeholder, same
  caveats as `generic` -- use Learn Command for real codes).
- Expand the Learn Command punch list (`LEARN_PUNCH_LIST`) to cover every
  `auto`/`cool`/`dry` combination across 16-30°C and all four fan speeds at
  swing off (~180 entries), replacing the old short curated list. **Note:**
  `heat` mode and swing "on" are no longer offered in the Learn Command
  checklist (there's no free-text entry in this flow) -- extend
  `LEARN_PUNCH_LIST` manually if you need those.

## [0.1.1-alpha-01]
- Nothing

## [0.1.1]

- Add Tuya Cloud API-assisted device discovery to the config flow.
- Fix options flow `config_entry` access for cross-version Home Assistant
  compatibility.
- Fix CI: pytest import path, manifest key order, HACS store-only checks.

## [0.1.0]

- Initial release: Tuya local IR AC Remote HACS integration, exposing a
  `climate` entity for Panasonic/Carrier air conditioners driven by a local
  Tuya IR hub, with Learn Command support.

