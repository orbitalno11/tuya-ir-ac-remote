"""Climate platform for the Tuya IR AC Remote integration.

Each Home Assistant config entry represents one AC unit reachable through a
Tuya local IR hub. State is optimistic: IR blasters have no feedback
channel, so the entity tracks whatever was last commanded and restores it
across restarts via RestoreEntity.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_SWING_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .codes.loader import get_merged_table, load_builtin_codeset
from .codes.schema import CodeTable
from .codes.state_key import build_state_key
from .const import CONF_BRAND, CONF_VARIANT, DOMAIN, STATE_KEY_OFF
from .tuya_ir import TuyaIrError, TuyaIrHub

_LOGGER = logging.getLogger(__name__)

HVAC_MODE_BY_VALUE = {mode.value: mode for mode in HVACMode}
# Order in which to advertise modes when the code table supports them.
CONTROLLABLE_HVAC_MODES = [
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
    HVACMode.AUTO,
]


@dataclass
class TuyaIrLastActiveModeData(ExtraStoredData):
    """Extra restore data so 'turn on' can resume the last active hvac mode.

    The primary RestoreEntity state restore only ever recovers "off" itself
    when the entity was off at last shutdown, with no record of what mode
    preceded it -- this side-channel carries that one extra bit across
    restarts.
    """

    last_active_hvac_mode: HVACMode | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> "TuyaIrLastActiveModeData":
        return cls(last_active_hvac_mode=restored.get("last_active_hvac_mode"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate entity for one AC unit config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    hub: TuyaIrHub = entry_data["hub"]
    learned_codes: dict[str, str] = entry_data["learned_codes"]

    builtin_table = load_builtin_codeset(
        entry.data[CONF_BRAND], entry.data[CONF_VARIANT]
    )

    async_add_entities(
        [TuyaIrClimateEntity(entry, hub, builtin_table, learned_codes)]
    )


class TuyaIrClimateEntity(ClimateEntity, RestoreEntity):
    """A climate entity that controls an AC unit through a Tuya IR hub."""

    _attr_should_poll = False
    _attr_assumed_state = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        entry: ConfigEntry,
        hub: TuyaIrHub,
        builtin_table: CodeTable,
        learned_codes: dict[str, str],
    ) -> None:
        self._entry = entry
        self._hub = hub
        self._builtin_table = builtin_table
        self._learned_codes = learned_codes

        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, entry.title),
            manufacturer=builtin_table.brand.title(),
            model=builtin_table.variant,
        )

        self._attr_min_temp = builtin_table.min_temp
        self._attr_max_temp = builtin_table.max_temp
        self._attr_target_temperature_step = builtin_table.temp_step
        self._attr_fan_modes = list(builtin_table.fan_modes)
        self._attr_swing_modes = list(builtin_table.swing_modes)
        self._attr_hvac_modes = self._derive_supported_hvac_modes()

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

        # Optimistic state -- there is no feedback channel from an IR blaster.
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_target_temperature = builtin_table.min_temp
        self._attr_fan_mode = self._attr_fan_modes[0] if self._attr_fan_modes else None
        self._attr_swing_mode = self._attr_swing_modes[0] if self._attr_swing_modes else None

        # Most recent non-off hvac mode, so a "turn on" (e.g. from Google
        # Assistant) can resume it instead of a fixed fallback mode.
        self._attr_last_active_hvac_mode: HVACMode | None = None

    def _derive_supported_hvac_modes(self) -> list[HVACMode]:
        """Only advertise hvac modes that actually have a code in the table."""
        merged = get_merged_table(self._builtin_table, self._learned_codes)
        modes = set()
        for key in merged:
            if key == STATE_KEY_OFF:
                continue
            # Match the mode by prefix rather than splitting on the first "_",
            # so multi-word modes ("fan_only", "heat_cool") are recognised.
            for mode_value, mode in HVAC_MODE_BY_VALUE.items():
                if key == mode_value or key.startswith(f"{mode_value}_"):
                    modes.add(mode)
                    break
        ordered = [HVACMode.OFF]
        ordered += [mode for mode in CONTROLLABLE_HVAC_MODES if mode in modes]
        return ordered

    async def async_added_to_hass(self) -> None:
        """Restore optimistic state from the last known entity state."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            if last_state.state in HVAC_MODE_BY_VALUE and HVAC_MODE_BY_VALUE[
                last_state.state
            ] in (self._attr_hvac_modes or []):
                self._attr_hvac_mode = HVAC_MODE_BY_VALUE[last_state.state]

            attrs = last_state.attributes
            temperature = attrs.get(ATTR_TEMPERATURE)
            if temperature is not None and self._attr_min_temp <= temperature <= self._attr_max_temp:
                self._attr_target_temperature = temperature

            fan_mode = attrs.get(ATTR_FAN_MODE)
            if fan_mode is not None and fan_mode in (self._attr_fan_modes or []):
                self._attr_fan_mode = fan_mode

            swing_mode = attrs.get(ATTR_SWING_MODE)
            if swing_mode is not None and swing_mode in (self._attr_swing_modes or []):
                self._attr_swing_mode = swing_mode

        last_extra_data = await self.async_get_last_extra_data()
        if last_extra_data is not None:
            restored = TuyaIrLastActiveModeData.from_dict(last_extra_data.as_dict())
            restored_mode = restored.last_active_hvac_mode
            if restored_mode in HVAC_MODE_BY_VALUE and HVAC_MODE_BY_VALUE[
                restored_mode
            ] in (self._attr_hvac_modes or []):
                self._attr_last_active_hvac_mode = HVAC_MODE_BY_VALUE[restored_mode]

        if self._attr_last_active_hvac_mode is None:
            if self._attr_hvac_mode != HVACMode.OFF:
                # Upgrading from a version without extra-data tracking: the
                # plain state restore above still gives a good signal here.
                self._attr_last_active_hvac_mode = self._attr_hvac_mode
            else:
                controllable_modes = [
                    mode
                    for mode in (self._attr_hvac_modes or [])
                    if mode != HVACMode.OFF
                ]
                if controllable_modes:
                    self._attr_last_active_hvac_mode = controllable_modes[0]

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        """Return the last-active-mode data to persist for restore."""
        return TuyaIrLastActiveModeData(
            last_active_hvac_mode=self._attr_last_active_hvac_mode
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature and transmit the full updated state."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._attr_target_temperature = temperature
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode and transmit the full updated state."""
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._attr_last_active_hvac_mode = hvac_mode
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn the AC on, resuming the most recently active hvac mode."""
        target_mode = self._attr_last_active_hvac_mode
        if target_mode not in (self._attr_hvac_modes or []):
            controllable_modes = [
                mode for mode in (self._attr_hvac_modes or []) if mode != HVACMode.OFF
            ]
            if not controllable_modes:
                raise HomeAssistantError(
                    "No controllable HVAC mode is available to turn on -- "
                    "no IR codes are known for this AC yet. Use this "
                    "entity's 'Configure' (Learn Command) options to teach "
                    "it from your real remote."
                )
            target_mode = controllable_modes[0]
        await self.async_set_hvac_mode(target_mode)

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new fan mode and transmit the full updated state."""
        self._attr_fan_mode = fan_mode
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new swing mode and transmit the full updated state."""
        self._attr_swing_mode = swing_mode
        await self._async_send_current_state()
        self.async_write_ha_state()

    async def _async_send_current_state(self) -> None:
        """Look up and transmit the IR code for the entity's current state.

        AC remotes in this integration are assumed to be "state" protocol:
        every press encodes the complete state, so we always send one code
        for the full current combination rather than per-attribute deltas.
        """
        state_key = build_state_key(
            self._attr_hvac_mode,
            self._attr_target_temperature,
            self._attr_fan_mode,
            self._attr_swing_mode,
        )
        merged = get_merged_table(self._builtin_table, self._learned_codes)
        code = merged.get(state_key)
        if code is None:
            _LOGGER.warning(
                "No IR code known for state %r on %s -- use this entity's "
                "Learn Command options flow to teach it from your real remote",
                state_key,
                self.entity_id,
            )
            raise HomeAssistantError(
                f"No IR code is known for this combination ({state_key}). "
                "Use this entity's 'Configure' (Learn Command) options to "
                "teach it from your real remote."
            )

        try:
            await self._hub.async_send_code(code)
        except TuyaIrError as err:
            raise HomeAssistantError(f"Failed to send IR command: {err}") from err
