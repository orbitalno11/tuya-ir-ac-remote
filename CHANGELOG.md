# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
correspond to `custom_components/tuya_ir_ac/manifest.json`'s `version` and
to the `vX.Y.Z` GitHub Release tag (see [RELEASING.md](RELEASING.md)).

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

