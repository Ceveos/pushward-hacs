"""Config flow and subentry flow for PushWard integration."""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    AttributeSelector,
    AttributeSelectorConfig,
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    IconSelector,
    IconSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    ObjectSelector,
    ObjectSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import PushWardApiClient, PushWardApiError, PushWardAuthError
from .const import (
    APP_STORE_URL,
    BOARD_MAX_TILES,
    BOARD_TILE_LABEL_MAX,
    BOARD_TILE_UNIT_MAX,
    CONF_ACCENT_COLOR,
    CONF_ACCENT_COLOR_ATTRIBUTE,
    CONF_ACTIVITY_NAME,
    CONF_ALARM,
    CONF_BACKGROUND_COLOR,
    CONF_BACKGROUND_COLOR_ATTRIBUTE,
    CONF_COMPLETION_MESSAGE,
    CONF_CURRENT_STEP_ATTR,
    CONF_CURRENT_STEP_ENTITY,
    CONF_DECIMALS,
    CONF_END_STATES,
    CONF_ENDED_TTL,
    CONF_ENTITY_ID,
    CONF_FIRED_AT_ATTRIBUTE,
    CONF_FIRED_AT_ENTITY,
    CONF_HISTORY_PERIOD,
    CONF_ICON,
    CONF_ICON_ATTRIBUTE,
    CONF_INTEGRATION_KEY,
    CONF_LABEL,
    CONF_LABEL_ATTRIBUTE,
    CONF_LIVE_PROGRESS,
    CONF_LOG_COLUMNS,
    CONF_LOG_LEVEL_ATTRIBUTE,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_PRIMARY_SERIES,
    CONF_PRIORITY,
    CONF_PROGRESS_ATTRIBUTE,
    CONF_PROGRESS_ENTITY,
    CONF_REMAINING_TIME_ATTR,
    CONF_REMAINING_TIME_ENTITY,
    CONF_SCALE,
    CONF_SECONDARY_URL,
    CONF_SECONDARY_URL_FOREGROUND,
    CONF_SECONDARY_URL_TITLE,
    CONF_SERIES,
    CONF_SERIES_ENTITIES,
    CONF_SERVER_URL,
    CONF_SEVERITY,
    CONF_SEVERITY_LABEL,
    CONF_SLUG,
    CONF_SMOOTHING,
    CONF_SNOOZE_SECONDS,
    CONF_SOUND,
    CONF_STALE_TTL,
    CONF_START_STATES,
    CONF_STAT_ROWS,
    CONF_STATE_LABELS,
    CONF_STEP_COLORS,
    CONF_STEP_CONFIGURATION,
    CONF_STEP_LABELS,
    CONF_STEP_ROWS,
    CONF_STEP_WEIGHTS,
    CONF_SUBTITLE_ATTRIBUTE,
    CONF_SUBTITLE_ENTITY,
    CONF_TAP_ACTION_FOREGROUND,
    CONF_TAP_ACTION_URL,
    CONF_TEMPLATE,
    CONF_TEXT_COLOR,
    CONF_TEXT_COLOR_ATTRIBUTE,
    CONF_THRESHOLDS,
    CONF_TILES,
    CONF_TOTAL_STEPS,
    CONF_UNIT,
    CONF_UNITS,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    CONF_URL_FOREGROUND,
    CONF_URL_TITLE,
    CONF_VALUE_ATTRIBUTE,
    CONF_VALUE_ENTITY,
    CONF_WARNING_THRESHOLD,
    CONF_WIDGET_NAME,
    CONF_WIDGET_POLL_INTERVAL,
    CONF_WIDGET_TEMPLATE,
    CONF_WIDGET_TRIGGER_MODE,
    DEFAULT_DECIMALS,
    DEFAULT_HISTORY_PERIOD,
    DEFAULT_MAX_VALUE,
    DEFAULT_MIN_VALUE,
    DEFAULT_PRIORITY,
    DEFAULT_SCALE,
    DEFAULT_SERVER_URL,
    DEFAULT_SEVERITY,
    DEFAULT_TOTAL_STEPS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_WIDGET_POLL_INTERVAL,
    DOMAIN,
    LOG_MAX_COLUMNS,
    MAX_LONG_TEXT_LEN,
    MAX_SLUG_LEN,
    MAX_TAP_ACTION_BODY_LEN,
    MAX_TAP_ACTION_ICON_LEN,
    MAX_TAP_ACTION_TITLE_LEN,
    MAX_TEXT_LEN,
    PRIORITY_MAX,
    PRIORITY_MIN,
    PUSHWARD_NAMED_COLORS,
    SNOOZE_SECONDS_MAX,
    SNOOZE_SECONDS_MIN,
    SOUNDS,
    SUBENTRY_TYPE_ENTITY,
    SUBENTRY_TYPE_WIDGET,
    TAP_ACTION_METHODS,
    TIMELINE_MAX_SERIES,
    TIMELINE_SERIES_LABEL_MAX,
    TOTAL_STEPS_MAX,
    UPDATE_INTERVAL_MIN,
    WARNING_THRESHOLD_MAX,
    WIDGET_LABEL_MAX,
    WIDGET_MAX_STAT_ROWS,
    WIDGET_NAME_MAX,
    WIDGET_POLL_INTERVAL_MAX,
    WIDGET_POLL_INTERVAL_MIN,
    WIDGET_TEMPLATE_GAUGE,
    WIDGET_TEMPLATE_PROGRESS,
    WIDGET_TEMPLATE_STAT_LIST,
    WIDGET_TEMPLATE_STATUS,
    WIDGET_TEMPLATE_VALUE,
    WIDGET_TRIGGER_EVENT,
    WIDGET_TRIGGER_MODES,
    WIDGET_TRIGGER_POLL,
    WIDGET_UNIT_MAX,
    normalize_slug,
    validate_action_headers,
    validate_color,
    validate_tap_action_url,
)
from .content_mapper import get_domain_defaults, sanitize_slug

_LOGGER = logging.getLogger(__name__)

_INTEGRATION_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_INTEGRATION_KEY): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    }
)

_TTL_MIN = 1
_TTL_MAX = 2592000  # 30 days


async def _validate_integration_key(
    hass: HomeAssistant,
    key: str,
    context: str,
    server_url: str = DEFAULT_SERVER_URL,
) -> dict[str, str]:
    """Validate an integration key against the PushWard API.

    Returns an error dict (empty on success).
    """
    session = async_get_clientsession(hass)
    client = PushWardApiClient(session, server_url, key)
    try:
        await client.validate_connection()
    except PushWardAuthError:
        return {"base": "invalid_auth"}
    except (PushWardApiError, aiohttp.ClientError, TimeoutError, OSError) as err:
        _LOGGER.warning("PushWard %s failed: %s", context, err)
        return {"base": "cannot_connect"}
    return {}


def _entity_domain(entity_id: str) -> str:
    """Extract the domain from an entity_id (e.g. 'sensor.temp' -> 'sensor')."""
    return entity_id.split(".")[0] if "." in entity_id else ""


def _entity_template_schema(defaults: dict | None = None) -> vol.Schema:
    """Build step-1 schema: entity picker + template."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ENTITY_ID,
                default=d.get(CONF_ENTITY_ID, ""),
            ): EntitySelector(EntitySelectorConfig()),
            vol.Optional(
                CONF_TEMPLATE,
                default=d.get(CONF_TEMPLATE, "generic"),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "generic", "label": "Generic progress"},
                        {"value": "countdown", "label": "Countdown / timer"},
                        {"value": "steps", "label": "Steps / workflow"},
                        {"value": "alert", "label": "Alert"},
                        {"value": "gauge", "label": "Gauge / numeric range"},
                        {"value": "timeline", "label": "Timeline / sparkline"},
                        {"value": "board", "label": "Board / tiles"},
                        {"value": "log", "label": "Event log"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _collect_entity_states(hass: HomeAssistant | None, entity_id: str, domain: str) -> list[str]:
    """Collect known state options for an entity from HA runtime data."""
    states: list[str] = []
    if hass is None:
        return states

    state_obj = hass.states.get(entity_id)
    if state_obj is None:
        return states

    # Current state
    if state_obj.state not in ("unavailable", "unknown"):
        states.append(state_obj.state)

    # select / input_select entities expose their options attribute
    if domain in ("select", "input_select"):
        options = state_obj.attributes.get("options", [])
        if isinstance(options, list):
            for opt in options:
                if isinstance(opt, str) and opt not in states:
                    states.append(opt)

    return states


# Device classes where gauge is the natural template.
_GAUGE_DEVICE_CLASSES = frozenset(
    {
        "temperature",
        "humidity",
        "battery",
        "power",
        "energy",
        "voltage",
        "current",
        "pressure",
        "illuminance",
        "speed",
        "wind_speed",
        "signal_strength",
        "moisture",
        "pm25",
        "pm10",
        "carbon_dioxide",
        "carbon_monoxide",
        "distance",
        "weight",
        "volume",
        "data_rate",
        "data_size",
        "frequency",
        "sound_pressure",
        "irradiance",
        "precipitation_intensity",
    }
)


def _suggest_template(hass: HomeAssistant | None, entity_id: str) -> str:
    """Suggest the best template for an entity based on domain/device_class/state_class."""
    if not entity_id or hass is None:
        return "generic"

    domain = _entity_domain(entity_id)

    if domain == "timer":
        return "countdown"
    if domain == "light":
        return "gauge"

    state_obj = hass.states.get(entity_id)
    if state_obj is None:
        return "generic"

    attrs = state_obj.attributes
    if domain in ("sensor", "number"):
        if attrs.get("state_class") in ("measurement", "total"):
            return "gauge"
        if attrs.get("device_class", "") in _GAUGE_DEVICE_CLASSES:
            return "gauge"

    return "generic"


def _details_schema(
    entity_id: str,
    template: str,
    defaults: dict | None = None,
    hass: HomeAssistant | None = None,
) -> vol.Schema:
    """Build step-2 schema with all config fields and dynamic selectors."""
    d = defaults or {}
    domain = _entity_domain(entity_id)
    domain_defs = get_domain_defaults(domain)

    # State options: domain defaults + entity runtime states + previously saved
    start_opts = list(domain_defs.get("start_states", []))
    end_opts = list(domain_defs.get("end_states", []))

    entity_states = _collect_entity_states(hass, entity_id, domain)
    for s in entity_states:
        if s not in start_opts:
            start_opts.append(s)
        if s not in end_opts:
            end_opts.append(s)

    saved_start = d.get(CONF_START_STATES, [])
    saved_end = d.get(CONF_END_STATES, [])
    if isinstance(saved_start, list):
        for s in saved_start:
            if s not in start_opts:
                start_opts.append(s)
    if isinstance(saved_end, list):
        for s in saved_end:
            if s not in end_opts:
                end_opts.append(s)

    start_default = d.get(CONF_START_STATES) if d.get(CONF_START_STATES) else domain_defs.get("start_states", [])
    end_default = d.get(CONF_END_STATES) if d.get(CONF_END_STATES) else domain_defs.get("end_states", [])

    tracked_attr_selector = AttributeSelector(AttributeSelectorConfig(entity_id=entity_id))
    # HA cannot dynamically rebind an AttributeSelector to a companion entity
    # selected elsewhere on this form. A text box never suggests attributes from
    # the wrong entity and preserves the existing stored string format.
    source_attr_selector = TextSelector()
    entity_selector = EntitySelector(EntitySelectorConfig())

    # Named-color dropdowns also accept custom RGB/RGBA hex values.
    accent_key = _color_vol_key(CONF_ACCENT_COLOR, d)
    bg_color_key = _color_vol_key(CONF_BACKGROUND_COLOR, d)
    text_color_key = _color_vol_key(CONF_TEXT_COLOR, d)

    # TTL defaults: only set default when valid value exists
    ended_ttl_val = d.get(CONF_ENDED_TTL)
    ended_ttl_key = (
        vol.Optional(CONF_ENDED_TTL, default=ended_ttl_val)
        if ended_ttl_val is not None
        else vol.Optional(CONF_ENDED_TTL)
    )
    stale_ttl_val = d.get(CONF_STALE_TTL)
    stale_ttl_key = (
        vol.Optional(CONF_STALE_TTL, default=stale_ttl_val)
        if stale_ttl_val is not None
        else vol.Optional(CONF_STALE_TTL)
    )

    fields: dict = {}

    # --- Start/end states (multi-select with custom values) ---
    fields[vol.Optional(CONF_START_STATES, default=start_default)] = SelectSelector(
        SelectSelectorConfig(
            options=start_opts,
            multiple=True,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    fields[vol.Optional(CONF_END_STATES, default=end_default)] = SelectSelector(
        SelectSelectorConfig(
            options=end_opts,
            multiple=True,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )

    # --- Template-specific fields ---
    if template in ("generic", "steps"):
        fields[_entity_source_key(CONF_PROGRESS_ENTITY, d)] = entity_selector
        fields[
            vol.Optional(
                CONF_PROGRESS_ATTRIBUTE,
                description={"suggested_value": d.get(CONF_PROGRESS_ATTRIBUTE, "")},
            )
        ] = source_attr_selector
    if template in ("generic", "countdown", "steps"):
        fields[_entity_source_key(CONF_REMAINING_TIME_ENTITY, d)] = entity_selector
        fields[
            vol.Optional(
                CONF_REMAINING_TIME_ATTR,
                description={"suggested_value": d.get(CONF_REMAINING_TIME_ATTR, "")},
            )
        ] = source_attr_selector
    if template in ("generic", "steps"):
        # Only meaningful with a remaining-time source above: interpolate the bar
        # to full and count down an ETA. Server accepts live_progress on generic only.
        fields[
            vol.Optional(
                CONF_LIVE_PROGRESS,
                default=d.get(CONF_LIVE_PROGRESS, False),
            )
        ] = BooleanSelector()
    if template == "steps":
        fields[_entity_source_key(CONF_CURRENT_STEP_ENTITY, d)] = entity_selector
        fields[
            vol.Optional(
                CONF_CURRENT_STEP_ATTR,
                description={"suggested_value": d.get(CONF_CURRENT_STEP_ATTR, "")},
            )
        ] = source_attr_selector
        step_default = d.get(CONF_STEP_CONFIGURATION)
        if not isinstance(step_default, list):
            total = int(d.get(CONF_TOTAL_STEPS, DEFAULT_TOTAL_STEPS))
            labels = d.get(CONF_STEP_LABELS) or {}
            rows = d.get(CONF_STEP_ROWS) or []
            weights = d.get(CONF_STEP_WEIGHTS) or []
            colors = d.get(CONF_STEP_COLORS) or []
            step_default = []
            for index in range(1, total + 1):
                item = {
                    "label": (
                        (labels.get(str(index)) or f"Step {index}")
                        if isinstance(labels, dict)
                        else f"Step {index}"
                    ),
                    "parallel_jobs": rows[index - 1] if index <= len(rows) else 1,
                    "weight": weights[index - 1] if index <= len(weights) else 1,
                }
                if index <= len(colors):
                    item["color"] = colors[index - 1]
                step_default.append(item)
        # With no label_field Home Assistant joins these compact peer values
        # with middle dots: "Wash · 2 jobs · 4 parts · Red".
        step_default = [
            {
                "label": item.get("label") or "",
                "parallel_jobs": (item.get("configuration") or item).get("parallel_jobs") or 1,
                "weight": (item.get("configuration") or item).get("weight") or 1,
                "color": _compact_step_color_value((item.get("configuration") or item).get("color") or ""),
            }
            for item in step_default
            if isinstance(item, dict)
        ]
        fields[vol.Required(CONF_STEP_CONFIGURATION, default=step_default)] = ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                fields={
                    "label": {
                        "label": "Step name (1-32 characters)",
                        "required": True,
                        "selector": TextSelector(),
                    },
                    "parallel_jobs": {
                        "label": "Parallel jobs (1-10)",
                        "required": True,
                        "selector": NumberSelector(
                            NumberSelectorConfig(
                                min=1,
                                max=10,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="jobs",
                            )
                        ),
                    },
                    "weight": {
                        "label": "Relative width (whole-number parts)",
                        "required": True,
                        "selector": NumberSelector(
                            NumberSelectorConfig(
                                min=1,
                                max=10000,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="parts",
                            )
                        ),
                    },
                    "color": {
                        "label": "Color",
                        "required": True,
                        "selector": _compact_step_color_selector(),
                    },
                },
            )
        )
    if template == "alert":
        fields[
            vol.Optional(
                CONF_SEVERITY,
                default=d.get(CONF_SEVERITY, DEFAULT_SEVERITY),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "info", "label": "Information"},
                    {"value": "warning", "label": "Warning"},
                    {"value": "critical", "label": "Critical"},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        fields[
            vol.Optional(
                CONF_SEVERITY_LABEL,
                default=d.get(CONF_SEVERITY_LABEL, ""),
            )
        ] = TextSelector()
        fields[_entity_source_key(CONF_FIRED_AT_ENTITY, d)] = entity_selector
        fields[
            vol.Optional(
                CONF_FIRED_AT_ATTRIBUTE,
                description={"suggested_value": d.get(CONF_FIRED_AT_ATTRIBUTE, "")},
            )
        ] = source_attr_selector
    if template == "gauge":
        fields[_entity_source_key(CONF_VALUE_ENTITY, d)] = entity_selector
        fields[
            vol.Optional(
                CONF_VALUE_ATTRIBUTE,
                description={"suggested_value": d.get(CONF_VALUE_ATTRIBUTE, "")},
            )
        ] = source_attr_selector
        fields[
            vol.Required(
                CONF_MIN_VALUE,
                default=d.get(CONF_MIN_VALUE, DEFAULT_MIN_VALUE),
            )
        ] = vol.Coerce(float)
        fields[
            vol.Required(
                CONF_MAX_VALUE,
                default=d.get(CONF_MAX_VALUE, DEFAULT_MAX_VALUE),
            )
        ] = vol.Coerce(float)
        fields[
            vol.Optional(
                CONF_UNIT,
                default=d.get(CONF_UNIT, ""),
            )
        ] = vol.All(str, vol.Length(max=32))
    if template == "timeline":
        series_default = d.get(CONF_SERIES, [])
        units_default = d.get(CONF_UNITS, {}) or {}
        if isinstance(series_default, dict):
            series_default = [
                {"attribute": attribute, "label": label, "unit": units_default.get(label, "")}
                for attribute, label in series_default.items()
            ]
        fields[
            vol.Optional(
                CONF_SERIES,
                default=series_default,
            )
        ] = ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                label_field=CONF_LABEL,
                description_field="attribute",
                fields={
                    CONF_LABEL: {"label": "Series label", "required": True, "selector": TextSelector()},
                    "attribute": {
                        "label": "Tracked-entity attribute",
                        "required": True,
                        "selector": tracked_attr_selector,
                    },
                    CONF_UNIT: {"label": "Display unit (optional)", "selector": TextSelector()},
                },
            )
        )
        fields[
            vol.Optional(
                CONF_SERIES_ENTITIES,
                default=d.get(CONF_SERIES_ENTITIES, []),
            )
        ] = ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                label_field=CONF_LABEL,
                description_field=CONF_ENTITY_ID,
                fields={
                    CONF_LABEL: {"label": "Series label", "selector": TextSelector()},
                    CONF_ENTITY_ID: {
                        "label": "Source entity",
                        "required": True,
                        "selector": EntitySelector(EntitySelectorConfig()),
                    },
                    "attribute": {"label": "Attribute (optional)", "selector": TextSelector()},
                    CONF_UNIT: {"label": "Display unit (optional)", "selector": TextSelector()},
                },
            )
        )
        fields[
            vol.Optional(
                CONF_PRIMARY_SERIES,
                default=d.get(CONF_PRIMARY_SERIES, ""),
            )
        ] = vol.All(str, vol.Length(max=32))
        fields[_entity_source_key(CONF_VALUE_ENTITY, d)] = entity_selector
        fields[
            vol.Optional(
                CONF_VALUE_ATTRIBUTE,
                description={"suggested_value": d.get(CONF_VALUE_ATTRIBUTE, "")},
            )
        ] = source_attr_selector
        fields[
            vol.Optional(
                CONF_UNIT,
                default=d.get(CONF_UNIT, ""),
            )
        ] = vol.All(str, vol.Length(max=32))
        fields[
            vol.Optional(
                CONF_SCALE,
                default=d.get(CONF_SCALE, DEFAULT_SCALE),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "linear", "label": "Linear"},
                    {"value": "logarithmic", "label": "Logarithmic"},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        fields[
            vol.Optional(
                CONF_DECIMALS,
                default=d.get(CONF_DECIMALS, DEFAULT_DECIMALS),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=10))
        fields[
            vol.Optional(
                CONF_SMOOTHING,
                default=d.get(CONF_SMOOTHING, False),
            )
        ] = BooleanSelector()
        fields[
            vol.Optional(
                CONF_THRESHOLDS,
                default=d.get(CONF_THRESHOLDS, []),
            )
        ] = ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                label_field="value",
                description_field="label",
                fields={
                    "value": {
                        "label": "Threshold value (in series units)",
                        "required": True,
                        "selector": NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX)),
                    },
                    "color": {"label": "Color (named or RGB/RGBA hex)", "selector": _color_selector()},
                    "label": {"label": "Label (optional)", "selector": TextSelector()},
                },
            )
        )
        fields[
            vol.Optional(
                CONF_HISTORY_PERIOD,
                default=d.get(CONF_HISTORY_PERIOD, DEFAULT_HISTORY_PERIOD),
            )
        ] = NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=1440,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="minutes",
            )
        )
    if template == "board":
        fields[
            vol.Required(
                CONF_TILES,
                default=d.get(CONF_TILES, []),
            )
        ] = ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                label_field=CONF_LABEL,
                description_field=CONF_ENTITY_ID,
                fields={
                    CONF_LABEL: {
                        "label": "Tile label (max 32 characters)",
                        "required": True,
                        "selector": TextSelector(),
                    },
                    CONF_ENTITY_ID: {
                        "label": "Value entity",
                        "required": True,
                        "selector": EntitySelector(EntitySelectorConfig()),
                    },
                    CONF_VALUE_ATTRIBUTE: {"label": "Attribute (optional)", "selector": TextSelector()},
                    CONF_UNIT: {"label": "Unit (optional, max 8 characters)", "selector": TextSelector()},
                    CONF_ICON: {"label": "Icon (optional)", "selector": IconSelector(IconSelectorConfig())},
                    CONF_ACCENT_COLOR: {
                        "label": "Color (named or RGB/RGBA hex)",
                        "selector": _color_selector(),
                    },
                    "trend": {
                        "label": "Trend (optional)",
                        "selector": SelectSelector(
                            SelectSelectorConfig(options=["", "up", "down", "flat"])
                        ),
                    },
                    "url_action": {"label": "Tile tap action (optional)", "selector": _action_selector(button=True)},
                },
            )
        )
    if template == "log":
        # Optional extra columns composed into each line's text. Freeform string
        # mirroring the board-tile format: '[Label=]source[|unit]' comma-separated,
        # where source is a tracked-entity attribute (brightness), another entity's
        # state (binary_sensor.door), or another entity's attribute (sensor.t:temp).
        fields[
            vol.Optional(
                CONF_LOG_COLUMNS,
                default=d.get(CONF_LOG_COLUMNS, []),
            )
        ] = ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                label_field=CONF_LABEL,
                description_field="attribute",
                fields={
                    CONF_LABEL: {"label": "Column label", "required": True, "selector": TextSelector()},
                    CONF_ENTITY_ID: {"label": "Source entity (optional)", "selector": entity_selector},
                    "attribute": {
                        "label": "Attribute (uses tracked entity when source is blank)",
                        "selector": TextSelector(),
                    },
                    CONF_UNIT: {"label": "Unit suffix (optional)", "selector": TextSelector()},
                },
            )
        )
        # Optional attribute on the tracked entity supplying each line's level
        # (info/warn/error); the line text is the formatted state.
        fields[
            vol.Optional(
                CONF_LOG_LEVEL_ATTRIBUTE,
                description={"suggested_value": d.get(CONF_LOG_LEVEL_ATTRIBUTE, "")},
            )
        ] = tracked_attr_selector

    # --- Identity fields ---
    fields[vol.Optional(CONF_SLUG, default=d.get(CONF_SLUG, ""))] = vol.All(str, vol.Length(max=MAX_SLUG_LEN))
    fields[
        vol.Optional(
            CONF_ACTIVITY_NAME,
            default=d.get(CONF_ACTIVITY_NAME, ""),
        )
    ] = vol.All(str, vol.Length(max=MAX_TEXT_LEN))
    fields[
        vol.Optional(
            CONF_ICON,
            description={"suggested_value": d.get(CONF_ICON, "")},
        )
    ] = IconSelector(IconSelectorConfig())
    fields[
        vol.Optional(
            CONF_ICON_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_ICON_ATTRIBUTE, "")},
        )
    ] = tracked_attr_selector
    fields[
        vol.Optional(
            CONF_PRIORITY,
            default=d.get(CONF_PRIORITY, DEFAULT_PRIORITY),
        )
    ] = NumberSelector(
        NumberSelectorConfig(
            min=PRIORITY_MIN,
            max=PRIORITY_MAX,
            step=1,
            mode=NumberSelectorMode.SLIDER,
        )
    )
    fields[
        vol.Optional(
            CONF_SOUND,
            default=d.get(CONF_SOUND, ""),
        )
    ] = SelectSelector(
        SelectSelectorConfig(
            options=[
                {"value": "", "label": "Silent (no sound)"},
                *[{"value": sound, "label": sound.replace("-", " ").title()} for sound in SOUNDS],
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    fields[
        vol.Optional(
            CONF_UPDATE_INTERVAL,
            default=d.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
    ] = NumberSelector(
        NumberSelectorConfig(
            min=UPDATE_INTERVAL_MIN,
            max=86400,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="seconds",
        )
    )

    # --- Optional fields ---
    fields[_entity_source_key(CONF_SUBTITLE_ENTITY, d)] = entity_selector
    fields[
        vol.Optional(
            CONF_SUBTITLE_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_SUBTITLE_ATTRIBUTE, "")},
        )
    ] = source_attr_selector
    state_labels_default = d.get(CONF_STATE_LABELS, [])
    if isinstance(state_labels_default, dict):
        state_labels_default = [
            {"state": state, "label": label} for state, label in state_labels_default.items()
        ]
    fields[vol.Optional(CONF_STATE_LABELS, default=state_labels_default)] = ObjectSelector(
        ObjectSelectorConfig(
            multiple=True,
            label_field="state",
            description_field="label",
            fields={
                "state": {"label": "Entity state", "required": True, "selector": TextSelector()},
                "label": {"label": "Text shown on iPhone", "required": True, "selector": TextSelector()},
            },
        )
    )
    if template == "countdown":
        fields[
            vol.Optional(
                CONF_COMPLETION_MESSAGE,
                default=d.get(CONF_COMPLETION_MESSAGE, ""),
            )
        ] = vol.All(str, vol.Length(max=MAX_LONG_TEXT_LEN))
        fields[
            vol.Optional(
                CONF_WARNING_THRESHOLD,
                description={"suggested_value": d.get(CONF_WARNING_THRESHOLD)},
            )
        ] = NumberSelector(
            NumberSelectorConfig(
                min=0,
                max=WARNING_THRESHOLD_MAX,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="seconds",
            )
        )
        fields[
            vol.Optional(
                CONF_ALARM,
                default=d.get(CONF_ALARM, False),
            )
        ] = BooleanSelector()
        fields[
            vol.Optional(
                CONF_SNOOZE_SECONDS,
                description={"suggested_value": d.get(CONF_SNOOZE_SECONDS)},
            )
        ] = NumberSelector(
            NumberSelectorConfig(
                min=SNOOZE_SECONDS_MIN,
                max=SNOOZE_SECONDS_MAX,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="seconds",
            )
        )
    fields[accent_key] = _color_selector()
    fields[
        vol.Optional(
            CONF_ACCENT_COLOR_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_ACCENT_COLOR_ATTRIBUTE, "")},
        )
    ] = tracked_attr_selector
    fields[bg_color_key] = _color_selector()
    fields[
        vol.Optional(
            CONF_BACKGROUND_COLOR_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_BACKGROUND_COLOR_ATTRIBUTE, "")},
        )
    ] = tracked_attr_selector
    fields[text_color_key] = _color_selector()
    fields[
        vol.Optional(
            CONF_TEXT_COLOR_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_TEXT_COLOR_ATTRIBUTE, "")},
        )
    ] = tracked_attr_selector
    fields[vol.Optional("tap_action", default=d.get("tap_action", {}))] = _action_selector(button=False)
    fields[vol.Optional("url_action", default=d.get("url_action", {}))] = _action_selector(button=True)
    fields[
        vol.Optional("secondary_url_action", default=d.get("secondary_url_action", {}))
    ] = _action_selector(button=True)
    fields[ended_ttl_key] = NumberSelector(
        NumberSelectorConfig(
            min=_TTL_MIN,
            max=_TTL_MAX,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="seconds",
        )
    )
    fields[stale_ttl_key] = NumberSelector(
        NumberSelectorConfig(
            min=_TTL_MIN,
            max=_TTL_MAX,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="seconds",
        )
    )

    return vol.Schema(fields)


_ENTITY_LIFECYCLE_FIELDS = {
    CONF_START_STATES,
    CONF_END_STATES,
    CONF_SLUG,
    CONF_ACTIVITY_NAME,
    CONF_PRIORITY,
    CONF_SOUND,
    CONF_UPDATE_INTERVAL,
    CONF_ENDED_TTL,
    CONF_STALE_TTL,
}

_ENTITY_APPEARANCE_FIELDS = {
    CONF_SUBTITLE_ENTITY,
    CONF_SUBTITLE_ATTRIBUTE,
    CONF_ICON,
    CONF_ICON_ATTRIBUTE,
    CONF_ACCENT_COLOR,
    CONF_ACCENT_COLOR_ATTRIBUTE,
    CONF_BACKGROUND_COLOR,
    CONF_BACKGROUND_COLOR_ATTRIBUTE,
    CONF_TEXT_COLOR,
    CONF_TEXT_COLOR_ATTRIBUTE,
    "tap_action",
    "url_action",
    "secondary_url_action",
}


def _schema_field_name(marker: object) -> str:
    """Return the plain field name from a voluptuous marker."""
    return str(marker.schema if isinstance(marker, vol.Marker) else marker)


def _subset_schema(schema: vol.Schema, field_names: set[str]) -> vol.Schema:
    """Select a stable subset of a schema while preserving field order and markers."""
    return vol.Schema(
        {
            marker: validator
            for marker, validator in schema.schema.items()
            if _schema_field_name(marker) in field_names
        }
    )


def _entity_staged_schemas(
    entity_id: str,
    template: str,
    defaults: dict | None = None,
    hass: HomeAssistant | None = None,
) -> tuple[vol.Schema, vol.Schema, vol.Schema]:
    """Split the large entity form into lifecycle, content, and appearance stages."""
    full = _details_schema(entity_id, template, defaults=defaults, hass=hass)
    lifecycle = _subset_schema(full, _ENTITY_LIFECYCLE_FIELDS)
    appearance = _subset_schema(full, _ENTITY_APPEARANCE_FIELDS)
    content = vol.Schema(
        {
            marker: validator
            for marker, validator in full.schema.items()
            if _schema_field_name(marker) not in _ENTITY_LIFECYCLE_FIELDS | _ENTITY_APPEARANCE_FIELDS
        }
    )
    return lifecycle, content, appearance


def _sectioned_schema(*sections: tuple[str, vol.Schema, bool]) -> vol.Schema:
    """Combine flat schemas into one form with collapsible sections."""
    return vol.Schema(
        {
            vol.Optional(name, default={}): section(schema, {"collapsed": collapsed})
            for name, schema, collapsed in sections
            if schema.schema
        },
        extra=vol.ALLOW_EXTRA,
    )


def _flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten one level of data-entry-flow sections for existing parsers."""
    flattened: dict[str, Any] = {}
    for key, value in user_input.items():
        if isinstance(value, dict) and key in {
            "lifecycle",
            "content",
            "appearance",
            "refresh",
        }:
            flattened.update(value)
        else:
            flattened[key] = value
    return flattened


def _entity_sectioned_schema(
    entity_id: str,
    template: str,
    defaults: dict | None = None,
    hass: HomeAssistant | None = None,
) -> vol.Schema:
    """Build the single post-template entity form."""
    lifecycle, content, appearance = _entity_staged_schemas(entity_id, template, defaults, hass)
    return _sectioned_schema(
        ("lifecycle", lifecycle, False),
        ("content", content, False),
        ("appearance", appearance, True),
    )


def _normalize_action(raw: object, *, button: bool) -> dict:
    """Validate one structured action from a config-flow object selector."""
    if not isinstance(raw, dict) or not raw:
        return {}
    url = validate_tap_action_url(str(raw.get("url") or "").strip())
    action: dict = {"url": url}
    if "foreground" in raw:
        action["foreground"] = bool(raw["foreground"])
    if method := raw.get("method"):
        method = str(method).upper()
        if method not in TAP_ACTION_METHODS:
            raise vol.Invalid("Unsupported silent webhook method")
        action["method"] = method
    if headers := raw.get("headers"):
        if not isinstance(headers, dict):
            raise vol.Invalid("Silent webhook headers must be an object")
        action["headers"] = validate_action_headers({str(key): str(value) for key, value in headers.items()})
    if body := raw.get("body"):
        if len(str(body)) > MAX_TAP_ACTION_BODY_LEN:
            raise vol.Invalid(f"Silent webhook body must be at most {MAX_TAP_ACTION_BODY_LEN} characters")
        action["body"] = str(body)
    if any(action.get(key) for key in ("method", "headers", "body")) and urlparse(url).scheme.lower() not in (
        "http",
        "https",
    ):
        raise vol.Invalid("Silent webhook method, headers, and body require an http(s) URL")
    if action.get("foreground") is False and not any(action.get(key) for key in ("method", "headers", "body")):
        if urlparse(url).scheme.lower() not in ("http", "https"):
            raise vol.Invalid("Silent webhook behavior requires an http(s) URL")
        action["method"] = "GET"
    if button:
        if title := raw.get("title"):
            if len(str(title)) > MAX_TAP_ACTION_TITLE_LEN:
                raise vol.Invalid(f"Button title must be at most {MAX_TAP_ACTION_TITLE_LEN} characters")
            action["title"] = str(title)
        if icon := raw.get("icon"):
            if len(str(icon)) > MAX_TAP_ACTION_ICON_LEN:
                raise vol.Invalid(f"Button icon must be at most {MAX_TAP_ACTION_ICON_LEN} characters")
            action["icon"] = str(icon)
    return action


def _coerce_gauge_range(user_input: dict, *, is_gauge: bool) -> tuple[float, float]:
    """Coerce min/max value pair; raise invalid_gauge_range if min >= max for gauge templates."""
    min_v = float(user_input.get(CONF_MIN_VALUE, DEFAULT_MIN_VALUE))
    max_v = float(user_input.get(CONF_MAX_VALUE, DEFAULT_MAX_VALUE))
    if is_gauge and min_v >= max_v:
        raise vol.Invalid("invalid_gauge_range", path=[CONF_MIN_VALUE])
    return min_v, max_v


def _parse_board_tiles(raw: object) -> list[dict]:
    """Parse board tiles from a string ('label=entity_id[:attr[:unit[:icon]]], ...') or list.

    Mirrors ``_parse_widget_stat_rows``. Capped at BOARD_MAX_TILES. Each parsed tile
    is ``{label, entity_id, value_attribute?, unit?, icon?}``.
    """
    if isinstance(raw, list):
        tiles = [t for t in raw if isinstance(t, dict) and t.get(CONF_ENTITY_ID) and t.get(CONF_LABEL)]
        return tiles[:BOARD_MAX_TILES]
    if not isinstance(raw, str) or not raw.strip():
        return []
    tiles = []
    for entry in raw.split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        label, rest = entry.split("=", 1)
        label = label.strip()
        # maxsplit=3 keeps the icon (4th field) intact even when it contains a
        # colon, e.g. an "mdi:cpu" MDI icon — otherwise the prefix would be lost.
        parts = [p.strip() for p in rest.split(":", 3)]
        if not label or not parts or not parts[0]:
            continue
        tile: dict = {CONF_LABEL: label, CONF_ENTITY_ID: parts[0]}
        if len(parts) > 1 and parts[1]:
            tile[CONF_VALUE_ATTRIBUTE] = parts[1]
        if len(parts) > 2 and parts[2]:
            tile[CONF_UNIT] = parts[2]
        if len(parts) > 3 and parts[3]:
            tile[CONF_ICON] = parts[3]
        tiles.append(tile)
        if len(tiles) >= BOARD_MAX_TILES:
            break
    return tiles


def _serialize_board_tiles(tiles: list[dict]) -> str:
    """Serialize board tiles back to 'label=entity_id[:attr[:unit[:icon]]], ...' for editing."""
    parts: list[str] = []
    for tile in tiles or []:
        label = tile.get(CONF_LABEL, "")
        entity_id = tile.get(CONF_ENTITY_ID, "")
        if not label or not entity_id:
            continue
        s = f"{label}={entity_id}"
        attr = tile.get(CONF_VALUE_ATTRIBUTE) or ""
        unit = tile.get(CONF_UNIT) or ""
        icon = tile.get(CONF_ICON) or ""
        if attr or unit or icon:
            s += f":{attr}"
        if unit or icon:
            s += f":{unit}"
        if icon:
            s += f":{icon}"
        parts.append(s)
    return ", ".join(parts)


def _parse_log_columns(raw: object) -> list[dict]:
    """Parse log columns from a string ('[Label=]source[|unit], ...') or list.

    Mirrors ``_parse_board_tiles``. Capped at LOG_MAX_COLUMNS. ``source`` disambiguates:
      - ``brightness`` (no dot)           → an attribute of the tracked entity
      - ``binary_sensor.door`` (has a dot) → another entity's state
      - ``sensor.temp:temperature``        → another entity's attribute
    ``|`` splits off an optional unit suffix; ``=`` splits off an optional label.
    Each parsed column is ``{label?, entity_id?, attribute?, unit?}``.
    """
    if isinstance(raw, list):
        cols = [c for c in raw if isinstance(c, dict) and (c.get(CONF_ENTITY_ID) or c.get("attribute"))]
        return cols[:LOG_MAX_COLUMNS]
    if not isinstance(raw, str) or not raw.strip():
        return []
    columns: list[dict] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        label = ""
        if "=" in entry:
            label, entry = (part.strip() for part in entry.split("=", 1))
        unit = ""
        if "|" in entry:
            entry, unit = (part.strip() for part in entry.split("|", 1))
        source = entry
        if not source:
            continue
        column: dict = {}
        if label:
            column[CONF_LABEL] = label
        if ":" in source:
            entity_id, attr = (part.strip() for part in source.split(":", 1))
            if not entity_id:
                continue
            column[CONF_ENTITY_ID] = entity_id
            if attr:
                column["attribute"] = attr
        elif "." in source:
            column[CONF_ENTITY_ID] = source
        else:
            column["attribute"] = source
        if unit:
            column[CONF_UNIT] = unit
        columns.append(column)
        if len(columns) >= LOG_MAX_COLUMNS:
            break
    return columns


def _serialize_log_columns(columns: list[dict]) -> str:
    """Serialize log columns back to '[Label=]source[|unit], ...' for editing."""
    parts: list[str] = []
    for column in columns or []:
        if not isinstance(column, dict):
            continue
        entity_id = column.get(CONF_ENTITY_ID) or ""
        attr = column.get("attribute") or ""
        if entity_id and attr:
            source = f"{entity_id}:{attr}"
        elif entity_id:
            source = entity_id
        elif attr:
            source = attr
        else:
            continue
        s = source
        label = column.get(CONF_LABEL) or ""
        if label:
            s = f"{label}={s}"
        unit = column.get(CONF_UNIT) or ""
        if unit:
            s = f"{s}|{unit}"
        parts.append(s)
    return ", ".join(parts)


def _parse_series_entities(raw: object) -> list[dict]:
    """Parse timeline series entities from a string ('[Label=]entity_id[:attribute], ...') or list.

    Mirrors ``_parse_board_tiles``. Each series binds a separate entity as a line:
    the entity's state, or one of its attributes ('entity_id:attribute'). ``source``
    must be an entity_id (contains a dot); a bare word is not a series and is
    skipped. The optional label is left raw here and frozen later by
    ``_resolve_series_entity_labels``. Capped at TIMELINE_MAX_SERIES. Each parsed
    series is ``{label?, entity_id, attribute?}``.
    """
    if isinstance(raw, list):
        series = [s for s in raw if isinstance(s, dict) and s.get(CONF_ENTITY_ID)]
        return series[:TIMELINE_MAX_SERIES]
    if not isinstance(raw, str) or not raw.strip():
        return []
    result: list[dict] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        label = ""
        if "=" in entry:
            label, entry = (part.strip() for part in entry.split("=", 1))
        source = entry
        if not source:
            continue
        series: dict = {}
        if ":" in source:
            entity_id, attr = (part.strip() for part in source.split(":", 1))
            if not entity_id or "." not in entity_id:
                continue
            series[CONF_ENTITY_ID] = entity_id
            if attr:
                series["attribute"] = attr
        elif "." in source:
            series[CONF_ENTITY_ID] = source
        else:
            continue
        if label:
            series[CONF_LABEL] = label
        result.append(series)
        if len(result) >= TIMELINE_MAX_SERIES:
            break
    return result


def _serialize_series_entities(series_entities: list[dict]) -> str:
    """Serialize timeline series entities back to '[Label=]entity_id[:attribute], ...' for editing."""
    parts: list[str] = []
    for series in series_entities or []:
        if not isinstance(series, dict):
            continue
        entity_id = series.get(CONF_ENTITY_ID) or ""
        if not entity_id:
            continue
        source = entity_id
        attr = series.get("attribute") or ""
        if attr:
            source = f"{entity_id}:{attr}"
        label = series.get(CONF_LABEL) or ""
        parts.append(f"{label}={source}" if label else source)
    return ", ".join(parts)


def _entity_friendly_name(hass: HomeAssistant | None, entity_id: str) -> str:
    """Return an entity's friendly name, falling back to the entity_id."""
    if hass is not None:
        state = hass.states.get(entity_id)
        if state is not None:
            name = state.attributes.get("friendly_name")
            if name:
                return str(name)
    return entity_id


def _dedupe_label(label: str, used: set[str]) -> str:
    """Return ``label`` (or ``label 2``/``label 3``/...) not already in ``used``.

    The base is re-truncated to make room for the suffix so the result never
    exceeds TIMELINE_SERIES_LABEL_MAX.
    """
    candidate = label
    n = 1
    while candidate in used:
        n += 1
        suffix = f" {n}"
        candidate = f"{label[: TIMELINE_SERIES_LABEL_MAX - len(suffix)]}{suffix}"
    return candidate


def _resolve_series_entity_labels(series_entities: list[dict], hass: HomeAssistant | None) -> list[dict]:
    """Freeze each timeline series-entity's label at config time.

    A label given in the config is used as-is; an unlabeled series defaults to the
    source entity's friendly name, with the attribute name appended when it reads
    an attribute (so two attributes of one entity don't collide). Labels are
    truncated to TIMELINE_SERIES_LABEL_MAX and de-duplicated with a numeric suffix.
    Freezing matters because the server merges timeline series by label (RFC 7396):
    a render-time friendly-name change would strand the old series as a flat line.
    """
    resolved: list[dict] = []
    used: set[str] = set()
    for series in series_entities:
        entity_id = series.get(CONF_ENTITY_ID)
        if not entity_id:
            continue
        attr = series.get("attribute")
        label = (series.get(CONF_LABEL) or "").strip()
        if not label:
            label = _entity_friendly_name(hass, entity_id)
            if attr:
                label = f"{label} {attr}"
        label = _dedupe_label(label[:TIMELINE_SERIES_LABEL_MAX], used)
        used.add(label)
        out: dict = {CONF_LABEL: label, CONF_ENTITY_ID: entity_id}
        if attr:
            out["attribute"] = attr
        if unit := series.get(CONF_UNIT):
            out[CONF_UNIT] = str(unit)
        resolved.append(out)
    return resolved


def _parse_entity_input(user_input: dict, hass: HomeAssistant | None = None) -> dict:
    """Normalize user input into an entity config dict."""
    entity_id = user_input[CONF_ENTITY_ID]
    raw_slug = user_input.get(CONF_SLUG, "").strip()
    slug = (normalize_slug(raw_slug) if raw_slug else "") or sanitize_slug(entity_id)

    domain = _entity_domain(entity_id)
    defaults = get_domain_defaults(domain)

    start_raw = user_input.get(CONF_START_STATES, [])
    end_raw = user_input.get(CONF_END_STATES, [])

    # Handle both list (from SelectSelector) and string (legacy fallback)
    if isinstance(start_raw, str):
        start_states = _parse_csv(start_raw)
    elif isinstance(start_raw, list):
        start_states = [s.strip() for s in start_raw if isinstance(s, str) and s.strip()]
    else:
        start_states = []

    if isinstance(end_raw, str):
        end_states = _parse_csv(end_raw)
    elif isinstance(end_raw, list):
        end_states = [s.strip() for s in end_raw if isinstance(s, str) and s.strip()]
    else:
        end_states = []

    # Parse TTLs: NumberSelector returns float, convert to int or None
    ended_ttl = user_input.get(CONF_ENDED_TTL)
    stale_ttl = user_input.get(CONF_STALE_TTL)

    tap_action = _normalize_action(user_input.get("tap_action"), button=False)
    url_action = _normalize_action(user_input.get("url_action"), button=True)
    secondary_url_action = _normalize_action(user_input.get("secondary_url_action"), button=True)
    # These keys are no longer shown, but accepting them costs nothing and keeps
    # direct parser callers/tests straightforward during the pre-release transition.
    legacy_tap_url = str(user_input.get(CONF_TAP_ACTION_URL) or "").strip()
    legacy_tap_foreground = bool(user_input.get(CONF_TAP_ACTION_FOREGROUND, True))
    legacy_url = str(user_input.get(CONF_URL) or "").strip()
    legacy_url_foreground = bool(user_input.get(CONF_URL_FOREGROUND, True))
    legacy_url_title = str(user_input.get(CONF_URL_TITLE) or "").strip()
    legacy_secondary_url = str(user_input.get(CONF_SECONDARY_URL) or "").strip()
    legacy_secondary_foreground = bool(user_input.get(CONF_SECONDARY_URL_FOREGROUND, True))
    legacy_secondary_title = str(user_input.get(CONF_SECONDARY_URL_TITLE) or "").strip()
    if legacy_tap_url:
        _normalize_action({"url": legacy_tap_url, "foreground": legacy_tap_foreground}, button=False)
    if legacy_url:
        _normalize_action({"url": legacy_url, "foreground": legacy_url_foreground}, button=True)
    if legacy_secondary_url:
        _normalize_action({"url": legacy_secondary_url, "foreground": legacy_secondary_foreground}, button=True)

    min_v, max_v = _coerce_gauge_range(user_input, is_gauge=user_input.get(CONF_TEMPLATE) == "gauge")

    # Parse timeline fields
    series_raw = user_input.get(CONF_SERIES, [])
    if isinstance(series_raw, list):
        series_rows = [row for row in series_raw if isinstance(row, dict)]
        series = {
            str(row.get("attribute") or "").strip(): str(row.get(CONF_LABEL) or "").strip()
            for row in series_rows
            if row.get("attribute") and row.get(CONF_LABEL)
        }
    else:
        series_rows = []
        series = _parse_state_labels(series_raw) if isinstance(series_raw, str) else series_raw or {}
    series_entities = _resolve_series_entity_labels(
        _parse_series_entities(user_input.get(CONF_SERIES_ENTITIES, "")), hass
    )
    if len(series) + len(series_entities) > TIMELINE_MAX_SERIES:
        raise vol.Invalid("too_many_series", path=[CONF_SERIES_ENTITIES])
    for row in [*series_rows, *series_entities]:
        label = str(row.get(CONF_LABEL) or "")
        if label and len(label) > TIMELINE_SERIES_LABEL_MAX:
            raise vol.Invalid(
                f"Timeline series labels must be at most {TIMELINE_SERIES_LABEL_MAX} characters",
                path=[CONF_SERIES],
            )
    units = {
        str(row.get(CONF_LABEL)).strip(): str(row.get(CONF_UNIT)).strip()
        for row in [*series_rows, *series_entities]
        if row.get(CONF_LABEL) and row.get(CONF_UNIT)
    }
    thresholds_raw = user_input.get(CONF_THRESHOLDS, "")
    if isinstance(thresholds_raw, list) and len(thresholds_raw) > 5:
        raise vol.Invalid("A Timeline supports at most 5 thresholds", path=[CONF_THRESHOLDS])
    thresholds = (
        _parse_thresholds(thresholds_raw)
        if isinstance(thresholds_raw, str)
        else [item for item in thresholds_raw or [] if isinstance(item, dict)][:5]
    )
    for threshold in thresholds:
        if isinstance(threshold, dict) and threshold.get("color"):
            threshold["color"] = _validate_color_input(threshold["color"])
    history_period_raw = user_input.get(CONF_HISTORY_PERIOD, DEFAULT_HISTORY_PERIOD)

    step_configuration = user_input.get(CONF_STEP_CONFIGURATION, [])
    if not isinstance(step_configuration, list):
        step_configuration = []
    if len(step_configuration) > TOTAL_STEPS_MAX:
        raise vol.Invalid(f"A Steps activity supports at most {TOTAL_STEPS_MAX} steps", path=[CONF_STEP_CONFIGURATION])
    step_configuration = [item for item in step_configuration if isinstance(item, dict)][:TOTAL_STEPS_MAX]
    if user_input.get(CONF_TEMPLATE) == "steps" and not step_configuration:
        legacy_total = int(user_input.get(CONF_TOTAL_STEPS, DEFAULT_TOTAL_STEPS))
        legacy_labels = _parse_state_labels(user_input.get(CONF_STEP_LABELS, ""))
        legacy_rows = _parse_int_list(user_input.get(CONF_STEP_ROWS, ""))
        step_configuration = []
        for index in range(1, max(1, min(TOTAL_STEPS_MAX, legacy_total)) + 1):
            item = {"label": legacy_labels.get(str(index), "")}
            if index <= len(legacy_rows):
                item["parallel_jobs"] = legacy_rows[index - 1]
            step_configuration.append(item)
    if user_input.get(CONF_TEMPLATE) == "steps":
        for index, item in enumerate(step_configuration, 1):
            label = str(item.get("label") or "").strip()
            if not label or len(label) > 32:
                raise vol.Invalid(
                    f"Step {index} needs a name between 1 and 32 characters",
                    path=[CONF_STEP_CONFIGURATION],
                )
            item["label"] = label
            configuration = item.get("configuration")
            if not isinstance(configuration, dict):
                configuration = item
            try:
                parallel_jobs_number = float(configuration.get("parallel_jobs") or 1)
                weight_number = float(configuration.get("weight") or 1)
            except (TypeError, ValueError) as err:
                raise vol.Invalid(f"Step {index} has an invalid numeric value", path=[CONF_STEP_CONFIGURATION]) from err
            if not parallel_jobs_number.is_integer() or not weight_number.is_integer():
                raise vol.Invalid(
                    f"Step {index} parallel jobs and relative width must be whole numbers",
                    path=[CONF_STEP_CONFIGURATION],
                )
            parallel_jobs = int(parallel_jobs_number)
            weight = int(weight_number)
            if not 1 <= parallel_jobs <= 10:
                raise vol.Invalid(f"Step {index} parallel jobs must be from 1 to 10", path=[CONF_STEP_CONFIGURATION])
            if not 1 <= weight <= 10000:
                raise vol.Invalid(
                    f"Step {index} relative width must be a whole number from 1 to 10,000",
                    path=[CONF_STEP_CONFIGURATION],
                )
            color = _parse_step_color(configuration.get("color"))
            item.clear()
            item.update(label=label, parallel_jobs=parallel_jobs, weight=weight, color=color)
    step_labels = {
        str(index): str(item.get("label") or "")
        for index, item in enumerate(step_configuration, 1)
        if item.get("label")
    }
    has_step_rows = any(item.get("parallel_jobs") is not None for item in step_configuration)
    step_rows = (
        [max(1, min(10, int(item.get("parallel_jobs") or 1))) for item in step_configuration]
        if has_step_rows
        else []
    )
    has_step_weights = any(item.get("weight") is not None for item in step_configuration)
    step_weights = (
        [max(0.1, float(item.get("weight") or 1)) for item in step_configuration]
        if has_step_weights
        else []
    )
    step_colors = [str(item.get("color") or "") for item in step_configuration]

    # Board tiles: a board needs at least one tile to render.
    raw_tiles = user_input.get(CONF_TILES, "")
    if isinstance(raw_tiles, list) and len(raw_tiles) > BOARD_MAX_TILES:
        raise vol.Invalid(f"A Board supports at most {BOARD_MAX_TILES} tiles", path=[CONF_TILES])
    tiles = _parse_board_tiles(raw_tiles)
    if user_input.get(CONF_TEMPLATE) == "board" and not tiles:
        raise vol.Invalid("tiles_required", path=[CONF_TILES])
    for index, tile in enumerate(tiles, 1):
        if len(str(tile.get(CONF_LABEL, ""))) > BOARD_TILE_LABEL_MAX:
            raise vol.Invalid(
                f"Tile {index} label must be at most {BOARD_TILE_LABEL_MAX} characters", path=[CONF_TILES]
            )
        if len(str(tile.get(CONF_UNIT, ""))) > BOARD_TILE_UNIT_MAX:
            raise vol.Invalid(
                f"Tile {index} unit must be at most {BOARD_TILE_UNIT_MAX} characters", path=[CONF_TILES]
            )
        if CONF_ACCENT_COLOR in tile:
            tile[CONF_ACCENT_COLOR] = _validate_color_input(tile[CONF_ACCENT_COLOR], allow_empty=True)
        if tile.get("url_action"):
            tile["url_action"] = _normalize_action(tile["url_action"], button=True)

    raw_log_columns = user_input.get(CONF_LOG_COLUMNS, "")
    if isinstance(raw_log_columns, list) and len(raw_log_columns) > LOG_MAX_COLUMNS:
        raise vol.Invalid(f"A Log supports at most {LOG_MAX_COLUMNS} extra columns", path=[CONF_LOG_COLUMNS])

    return {
        CONF_ENTITY_ID: entity_id,
        CONF_SLUG: slug,
        CONF_ACTIVITY_NAME: user_input.get(CONF_ACTIVITY_NAME, "") or entity_id,
        CONF_ICON: user_input.get(CONF_ICON, ""),
        CONF_ICON_ATTRIBUTE: user_input.get(CONF_ICON_ATTRIBUTE, ""),
        CONF_PRIORITY: int(user_input.get(CONF_PRIORITY, DEFAULT_PRIORITY)),
        CONF_TEMPLATE: user_input.get(CONF_TEMPLATE, "generic"),
        CONF_START_STATES: start_states or defaults.get("start_states", []),
        CONF_END_STATES: end_states or defaults.get("end_states", []),
        CONF_UPDATE_INTERVAL: int(user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)),
        CONF_PROGRESS_ATTRIBUTE: user_input.get(CONF_PROGRESS_ATTRIBUTE, ""),
        CONF_PROGRESS_ENTITY: user_input.get(CONF_PROGRESS_ENTITY, ""),
        CONF_REMAINING_TIME_ATTR: user_input.get(CONF_REMAINING_TIME_ATTR, ""),
        CONF_REMAINING_TIME_ENTITY: user_input.get(CONF_REMAINING_TIME_ENTITY, ""),
        CONF_LIVE_PROGRESS: bool(user_input.get(CONF_LIVE_PROGRESS, False)),
        CONF_SUBTITLE_ATTRIBUTE: user_input.get(CONF_SUBTITLE_ATTRIBUTE, ""),
        CONF_SUBTITLE_ENTITY: user_input.get(CONF_SUBTITLE_ENTITY, ""),
        CONF_STATE_LABELS: (
            _parse_state_labels(user_input.get(CONF_STATE_LABELS, ""))
            if isinstance(user_input.get(CONF_STATE_LABELS), str)
            else {
                str(row.get("state")).strip(): str(row.get("label")).strip()
                for row in user_input.get(CONF_STATE_LABELS, [])
                if isinstance(row, dict) and row.get("state") and row.get("label")
            }
        ),
        CONF_COMPLETION_MESSAGE: user_input.get(CONF_COMPLETION_MESSAGE, ""),
        CONF_TOTAL_STEPS: len(step_configuration) or user_input.get(CONF_TOTAL_STEPS, DEFAULT_TOTAL_STEPS),
        CONF_CURRENT_STEP_ATTR: user_input.get(CONF_CURRENT_STEP_ATTR, ""),
        CONF_CURRENT_STEP_ENTITY: user_input.get(CONF_CURRENT_STEP_ENTITY, ""),
        CONF_SEVERITY: user_input.get(CONF_SEVERITY, DEFAULT_SEVERITY),
        CONF_SEVERITY_LABEL: user_input.get(CONF_SEVERITY_LABEL, ""),
        CONF_VALUE_ATTRIBUTE: user_input.get(CONF_VALUE_ATTRIBUTE, ""),
        CONF_VALUE_ENTITY: user_input.get(CONF_VALUE_ENTITY, ""),
        CONF_MIN_VALUE: min_v,
        CONF_MAX_VALUE: max_v,
        CONF_UNIT: user_input.get(CONF_UNIT, ""),
        CONF_ACCENT_COLOR: _validate_color_input(user_input.get(CONF_ACCENT_COLOR), allow_empty=True),
        CONF_ACCENT_COLOR_ATTRIBUTE: user_input.get(CONF_ACCENT_COLOR_ATTRIBUTE, ""),
        "tap_action": tap_action,
        "url_action": url_action,
        "secondary_url_action": secondary_url_action,
        CONF_TAP_ACTION_URL: legacy_tap_url,
        CONF_TAP_ACTION_FOREGROUND: legacy_tap_foreground,
        CONF_URL: legacy_url,
        CONF_URL_FOREGROUND: legacy_url_foreground,
        CONF_URL_TITLE: legacy_url_title,
        CONF_SECONDARY_URL: legacy_secondary_url,
        CONF_SECONDARY_URL_FOREGROUND: legacy_secondary_foreground,
        CONF_SECONDARY_URL_TITLE: legacy_secondary_title,
        CONF_ENDED_TTL: int(ended_ttl) if ended_ttl is not None else None,
        CONF_STALE_TTL: int(stale_ttl) if stale_ttl is not None else None,
        CONF_SERIES: series,
        CONF_SERIES_ENTITIES: series_entities,
        CONF_PRIMARY_SERIES: (user_input.get(CONF_PRIMARY_SERIES) or "").strip(),
        CONF_SCALE: user_input.get(CONF_SCALE, DEFAULT_SCALE),
        CONF_DECIMALS: user_input.get(CONF_DECIMALS, DEFAULT_DECIMALS),
        CONF_SMOOTHING: user_input.get(CONF_SMOOTHING, False),
        CONF_THRESHOLDS: thresholds,
        CONF_HISTORY_PERIOD: int(history_period_raw) if history_period_raw is not None else DEFAULT_HISTORY_PERIOD,
        CONF_SOUND: user_input.get(CONF_SOUND, ""),
        CONF_WARNING_THRESHOLD: int(user_input[CONF_WARNING_THRESHOLD])
        if user_input.get(CONF_WARNING_THRESHOLD) is not None
        else None,
        CONF_ALARM: bool(user_input.get(CONF_ALARM, False)),
        CONF_SNOOZE_SECONDS: int(user_input[CONF_SNOOZE_SECONDS])
        if user_input.get(CONF_SNOOZE_SECONDS) is not None
        else None,
        CONF_STEP_CONFIGURATION: step_configuration,
        CONF_STEP_LABELS: step_labels or _parse_state_labels(user_input.get(CONF_STEP_LABELS, "")),
        CONF_STEP_ROWS: step_rows or _parse_int_list(user_input.get(CONF_STEP_ROWS, "")),
        CONF_STEP_WEIGHTS: step_weights,
        CONF_STEP_COLORS: step_colors,
        CONF_FIRED_AT_ATTRIBUTE: user_input.get(CONF_FIRED_AT_ATTRIBUTE, ""),
        CONF_FIRED_AT_ENTITY: user_input.get(CONF_FIRED_AT_ENTITY, ""),
        CONF_UNITS: units or _parse_state_labels(user_input.get(CONF_UNITS, "")),
        CONF_BACKGROUND_COLOR: _validate_color_input(user_input.get(CONF_BACKGROUND_COLOR), allow_empty=True),
        CONF_BACKGROUND_COLOR_ATTRIBUTE: user_input.get(CONF_BACKGROUND_COLOR_ATTRIBUTE, ""),
        CONF_TEXT_COLOR: _validate_color_input(user_input.get(CONF_TEXT_COLOR), allow_empty=True),
        CONF_TEXT_COLOR_ATTRIBUTE: user_input.get(CONF_TEXT_COLOR_ATTRIBUTE, ""),
        CONF_TILES: tiles,
        CONF_LOG_LEVEL_ATTRIBUTE: user_input.get(CONF_LOG_LEVEL_ATTRIBUTE, ""),
        CONF_LOG_COLUMNS: _parse_log_columns(raw_log_columns),
    }


class PushWardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial PushWard configuration."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await _validate_integration_key(self.hass, user_input[CONF_INTEGRATION_KEY], "setup")
            if not errors:
                return self.async_create_entry(
                    title="PushWard HACS",
                    data={
                        CONF_SERVER_URL: DEFAULT_SERVER_URL,
                        CONF_INTEGRATION_KEY: user_input[CONF_INTEGRATION_KEY],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_INTEGRATION_KEY_SCHEMA,
            errors=errors,
            description_placeholders={"app_store_url": APP_STORE_URL},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Handle reconfiguration of the integration key."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await _validate_integration_key(self.hass, user_input[CONF_INTEGRATION_KEY], "reconfigure")
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        CONF_SERVER_URL: DEFAULT_SERVER_URL,
                        CONF_INTEGRATION_KEY: user_input[CONF_INTEGRATION_KEY],
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_INTEGRATION_KEY_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> config_entries.ConfigFlowResult:
        """Handle reauth when the integration key becomes invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask user for a new integration key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entry = self._get_reauth_entry()
            server_url = entry.data[CONF_SERVER_URL]
            errors = await _validate_integration_key(
                self.hass, user_input[CONF_INTEGRATION_KEY], "reauth", server_url=server_url
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_INTEGRATION_KEY: user_input[CONF_INTEGRATION_KEY],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_INTEGRATION_KEY_SCHEMA,
            errors=errors,
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return supported subentry types."""
        return {
            SUBENTRY_TYPE_ENTITY: PushWardEntitySubentryFlow,
            SUBENTRY_TYPE_WIDGET: PushWardWidgetSubentryFlow,
        }


class PushWardEntitySubentryFlow(config_entries.ConfigSubentryFlow):
    """Handle tracked entities with a template picker and one sectioned form."""

    def __init__(self) -> None:
        """Initialize the subentry flow."""
        super().__init__()
        self._step1_input: dict[str, Any] = {}
        self._is_reconfigure: bool = False
        self._details_defaults: dict[str, Any] = {}
        self._suggestion_offered: bool = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.SubentryFlowResult:
        """Step 1: Entity + template."""
        if user_input is not None:
            entity_id = user_input[CONF_ENTITY_ID]
            template = user_input.get(CONF_TEMPLATE, "generic")

            # Suggest a better template if the user left the default
            if template == "generic" and not self._suggestion_offered:
                suggested = _suggest_template(self.hass, entity_id)
                if suggested != "generic":
                    self._suggestion_offered = True
                    return self.async_show_form(
                        step_id="user",
                        data_schema=_entity_template_schema(
                            defaults={CONF_ENTITY_ID: entity_id, CONF_TEMPLATE: suggested}
                        ),
                    )

            self._step1_input = user_input
            self._is_reconfigure = False
            return await self.async_step_details()

        return self.async_show_form(
            step_id="user",
            data_schema=_entity_template_schema(),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Step 1 (reconfigure): Entity + template with pre-filled values."""
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            self._step1_input = user_input
            self._is_reconfigure = True
            # Prepare defaults for step 2 from existing config
            self._details_defaults = dict(subentry.data)
            return await self.async_step_details()

        current = dict(subentry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_entity_template_schema(defaults=current),
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> config_entries.SubentryFlowResult:
        """Step 2: Configure all template options in collapsible sections."""
        entity_id = self._step1_input.get(CONF_ENTITY_ID, "")
        template = self._step1_input.get(CONF_TEMPLATE, "generic")
        if user_input is not None:
            merged = {**self._step1_input, **_flatten_sections(user_input)}
            try:
                entity_cfg = _parse_entity_input(merged, hass=self.hass)
            except vol.Invalid as exc:
                defaults = self._details_defaults if self._is_reconfigure else None
                return self.async_show_form(
                    step_id="details",
                    data_schema=_entity_sectioned_schema(entity_id, template, defaults, self.hass),
                    errors={"base": str(exc.msg)},
                )
            if self._is_reconfigure:
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=entity_cfg,
                    title=entity_cfg[CONF_ACTIVITY_NAME],
                )
            return self.async_create_entry(
                title=entity_cfg[CONF_ACTIVITY_NAME],
                data=entity_cfg,
                unique_id=entity_cfg[CONF_ENTITY_ID],
            )

        defaults = self._details_defaults if self._is_reconfigure else None
        return self.async_show_form(
            step_id="details",
            data_schema=_entity_sectioned_schema(entity_id, template, defaults, self.hass),
            description_placeholders={"entity": entity_id, "template": template},
        )

# --- Widget subentry flow ---


def _widget_step1_schema(defaults: dict | None = None) -> vol.Schema:
    """Step-1 schema: entity picker + template + (optional) slug override."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_ENTITY_ID,
                default=d.get(CONF_ENTITY_ID, ""),
            ): EntitySelector(EntitySelectorConfig()),
            vol.Required(
                CONF_WIDGET_TEMPLATE,
                default=d.get(CONF_WIDGET_TEMPLATE, WIDGET_TEMPLATE_VALUE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        {"value": "value", "label": "Single value"},
                        {"value": "progress", "label": "Progress"},
                        {"value": "gauge", "label": "Gauge"},
                        {"value": "status", "label": "Status"},
                        {"value": "stat_list", "label": "Statistics list"},
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_SLUG,
                default=d.get(CONF_SLUG, ""),
            ): vol.All(str, vol.Length(max=MAX_SLUG_LEN)),
        }
    )


def _widget_details_schema(
    entity_id: str,
    template: str,
    defaults: dict | None = None,
) -> vol.Schema:
    """Step-2 schema: template-specific fields + cosmetics + trigger mode."""
    d = defaults or {}

    attr_selector = AttributeSelector(AttributeSelectorConfig(entity_id=entity_id))

    accent_key = _color_vol_key(CONF_ACCENT_COLOR, d)
    bg_color_key = _color_vol_key(CONF_BACKGROUND_COLOR, d)
    text_color_key = _color_vol_key(CONF_TEXT_COLOR, d)

    fields: dict = {}

    fields[
        vol.Optional(
            CONF_WIDGET_NAME,
            default=d.get(CONF_WIDGET_NAME, ""),
        )
    ] = vol.All(str, vol.Length(max=WIDGET_NAME_MAX))

    # Template-specific
    if template in (WIDGET_TEMPLATE_VALUE, WIDGET_TEMPLATE_PROGRESS, WIDGET_TEMPLATE_GAUGE):
        fields[
            vol.Optional(
                CONF_VALUE_ATTRIBUTE,
                description={"suggested_value": d.get(CONF_VALUE_ATTRIBUTE, "")},
            )
        ] = attr_selector
        fields[
            vol.Optional(
                CONF_UNIT,
                default=d.get(CONF_UNIT, ""),
            )
        ] = vol.All(str, vol.Length(max=WIDGET_UNIT_MAX))

    if template == WIDGET_TEMPLATE_GAUGE:
        fields[
            vol.Required(
                CONF_MIN_VALUE,
                default=d.get(CONF_MIN_VALUE, DEFAULT_MIN_VALUE),
            )
        ] = vol.Coerce(float)
        fields[
            vol.Required(
                CONF_MAX_VALUE,
                default=d.get(CONF_MAX_VALUE, DEFAULT_MAX_VALUE),
            )
        ] = vol.Coerce(float)

    if template == WIDGET_TEMPLATE_STATUS:
        fields[
            vol.Optional(
                CONF_SEVERITY,
                default=d.get(CONF_SEVERITY, ""),
            )
        ] = SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "", "label": "None"},
                    {"value": "info", "label": "Information"},
                    {"value": "warning", "label": "Warning"},
                    {"value": "critical", "label": "Critical"},
                    {"value": "success", "label": "Success"},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

    if template == WIDGET_TEMPLATE_STAT_LIST:
        fields[
            vol.Required(
                CONF_STAT_ROWS,
                default=d.get(CONF_STAT_ROWS, []),
            )
        ] = ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                label_field=CONF_LABEL,
                description_field=CONF_ENTITY_ID,
                fields={
                    CONF_LABEL: {"label": "Row label", "required": True, "selector": TextSelector()},
                    CONF_ENTITY_ID: {
                        "label": "Value entity",
                        "required": True,
                        "selector": EntitySelector(EntitySelectorConfig()),
                    },
                    CONF_VALUE_ATTRIBUTE: {"label": "Attribute (optional)", "selector": TextSelector()},
                    CONF_UNIT: {"label": "Unit (optional)", "selector": TextSelector()},
                },
            )
        )

    # Cosmetic fields (all templates)
    fields[
        vol.Optional(
            CONF_LABEL,
            default=d.get(CONF_LABEL, ""),
        )
    ] = vol.All(str, vol.Length(max=WIDGET_LABEL_MAX))
    fields[
        vol.Optional(
            CONF_LABEL_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_LABEL_ATTRIBUTE, "")},
        )
    ] = attr_selector
    fields[
        vol.Optional(
            CONF_SUBTITLE_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_SUBTITLE_ATTRIBUTE, "")},
        )
    ] = attr_selector
    fields[
        vol.Optional(
            CONF_ICON,
            description={"suggested_value": d.get(CONF_ICON, "")},
        )
    ] = IconSelector(IconSelectorConfig())
    fields[
        vol.Optional(
            CONF_ICON_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_ICON_ATTRIBUTE, "")},
        )
    ] = attr_selector
    fields[accent_key] = _color_selector()
    fields[
        vol.Optional(
            CONF_ACCENT_COLOR_ATTRIBUTE,
            description={"suggested_value": d.get(CONF_ACCENT_COLOR_ATTRIBUTE, "")},
        )
    ] = attr_selector
    fields[bg_color_key] = _color_selector()
    fields[text_color_key] = _color_selector()

    fields[vol.Optional("tap_action", default=d.get("tap_action", {}))] = _action_selector(button=False)
    fields[vol.Optional("url_action", default=d.get("url_action", {}))] = _action_selector(button=True)
    fields[
        vol.Optional("secondary_url_action", default=d.get("secondary_url_action", {}))
    ] = _action_selector(button=True)

    # Trigger mode + interval
    fields[
        vol.Required(
            CONF_WIDGET_TRIGGER_MODE,
            default=d.get(CONF_WIDGET_TRIGGER_MODE, WIDGET_TRIGGER_EVENT),
        )
    ] = SelectSelector(
        SelectSelectorConfig(
            options=[
                {"value": WIDGET_TRIGGER_EVENT, "label": "On entity changes (recommended)"},
                {"value": WIDGET_TRIGGER_POLL, "label": "Poll on a schedule"},
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    fields[
        vol.Optional(
            CONF_WIDGET_POLL_INTERVAL,
            default=d.get(CONF_WIDGET_POLL_INTERVAL, DEFAULT_WIDGET_POLL_INTERVAL),
        )
    ] = NumberSelector(
        NumberSelectorConfig(
            min=WIDGET_POLL_INTERVAL_MIN,
            max=WIDGET_POLL_INTERVAL_MAX,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="seconds",
        )
    )

    return vol.Schema(fields)


_WIDGET_APPEARANCE_FIELDS = {
    CONF_WIDGET_NAME,
    CONF_LABEL,
    CONF_LABEL_ATTRIBUTE,
    CONF_SUBTITLE_ATTRIBUTE,
    CONF_ICON,
    CONF_ICON_ATTRIBUTE,
    CONF_ACCENT_COLOR,
    CONF_ACCENT_COLOR_ATTRIBUTE,
    CONF_BACKGROUND_COLOR,
    CONF_TEXT_COLOR,
    "tap_action",
    "url_action",
    "secondary_url_action",
}
_WIDGET_REFRESH_FIELDS = {CONF_WIDGET_TRIGGER_MODE, CONF_WIDGET_POLL_INTERVAL}


def _widget_staged_schemas(
    entity_id: str,
    template: str,
    defaults: dict | None = None,
) -> tuple[vol.Schema, vol.Schema, vol.Schema]:
    """Split widget configuration into content, appearance, and refresh stages."""
    full = _widget_details_schema(entity_id, template, defaults=defaults)
    appearance = _subset_schema(full, _WIDGET_APPEARANCE_FIELDS)
    refresh = _subset_schema(full, _WIDGET_REFRESH_FIELDS)
    content = vol.Schema(
        {
            marker: validator
            for marker, validator in full.schema.items()
            if _schema_field_name(marker) not in _WIDGET_APPEARANCE_FIELDS | _WIDGET_REFRESH_FIELDS
        }
    )
    return content, appearance, refresh


def _widget_sectioned_schema(entity_id: str, template: str, defaults: dict | None = None) -> vol.Schema:
    """Build the single post-template widget form."""
    content, appearance, refresh = _widget_staged_schemas(entity_id, template, defaults)
    return _sectioned_schema(
        ("content", content, False),
        ("appearance", appearance, True),
        ("refresh", refresh, True),
    )


def _parse_widget_stat_rows(raw: object) -> list[dict]:
    """Parse stat_rows from string ('label=entity_id[:attr[:unit]], ...') or list."""
    if isinstance(raw, list):
        rows = [row for row in raw if isinstance(row, dict) and row.get(CONF_ENTITY_ID) and row.get(CONF_LABEL)]
        return rows[:WIDGET_MAX_STAT_ROWS]
    if not isinstance(raw, str) or not raw.strip():
        return []
    rows: list[dict] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if "=" not in entry:
            continue
        label, rest = entry.split("=", 1)
        label = label.strip()
        parts = [p.strip() for p in rest.split(":")]
        if not label or not parts or not parts[0]:
            continue
        row: dict = {CONF_LABEL: label, CONF_ENTITY_ID: parts[0]}
        if len(parts) > 1 and parts[1]:
            row[CONF_VALUE_ATTRIBUTE] = parts[1]
        if len(parts) > 2 and parts[2]:
            row[CONF_UNIT] = parts[2]
        rows.append(row)
        if len(rows) >= WIDGET_MAX_STAT_ROWS:
            break
    return rows


def _serialize_widget_stat_rows(rows: list[dict]) -> str:
    parts: list[str] = []
    for row in rows or []:
        label = row.get(CONF_LABEL, "")
        entity_id = row.get(CONF_ENTITY_ID, "")
        if not label or not entity_id:
            continue
        s = f"{label}={entity_id}"
        attr = row.get(CONF_VALUE_ATTRIBUTE) or ""
        unit = row.get(CONF_UNIT) or ""
        if attr or unit:
            s += f":{attr}"
        if unit:
            s += f":{unit}"
        parts.append(s)
    return ", ".join(parts)


def _parse_widget_input(user_input: dict, step1: dict) -> dict:
    """Build the persisted subentry data from step-1 + step-2 inputs."""
    entity_id = step1[CONF_ENTITY_ID]
    template = step1[CONF_WIDGET_TEMPLATE]
    raw_slug = (step1.get(CONF_SLUG) or "").strip()
    slug = (normalize_slug(raw_slug) if raw_slug else "") or sanitize_slug(entity_id)

    min_v, max_v = _coerce_gauge_range(user_input, is_gauge=template == WIDGET_TEMPLATE_GAUGE)

    raw_stat_rows = user_input.get(CONF_STAT_ROWS, [])
    if isinstance(raw_stat_rows, list) and len(raw_stat_rows) > WIDGET_MAX_STAT_ROWS:
        raise vol.Invalid(f"A statistics widget supports at most {WIDGET_MAX_STAT_ROWS} rows", path=[CONF_STAT_ROWS])
    stat_rows = _parse_widget_stat_rows(raw_stat_rows)
    if template == WIDGET_TEMPLATE_STAT_LIST and not stat_rows:
        raise vol.Invalid("stat_rows_required", path=[CONF_STAT_ROWS])
    for index, row in enumerate(stat_rows, 1):
        label = str(row.get(CONF_LABEL) or "").strip()
        unit = str(row.get(CONF_UNIT) or "")
        if not label or len(label) > WIDGET_LABEL_MAX:
            raise vol.Invalid(
                f"Statistic row {index} needs a label from 1 to {WIDGET_LABEL_MAX} characters",
                path=[CONF_STAT_ROWS],
            )
        if len(unit) > WIDGET_UNIT_MAX:
            raise vol.Invalid(
                f"Statistic row {index} unit must be at most {WIDGET_UNIT_MAX} characters",
                path=[CONF_STAT_ROWS],
            )

    poll_interval = int(user_input.get(CONF_WIDGET_POLL_INTERVAL, DEFAULT_WIDGET_POLL_INTERVAL))
    poll_interval = max(WIDGET_POLL_INTERVAL_MIN, min(WIDGET_POLL_INTERVAL_MAX, poll_interval))

    trigger = user_input.get(CONF_WIDGET_TRIGGER_MODE) or WIDGET_TRIGGER_EVENT
    if trigger not in WIDGET_TRIGGER_MODES:
        trigger = WIDGET_TRIGGER_EVENT

    tap_action = _normalize_action(user_input.get("tap_action"), button=False)
    url_action = _normalize_action(user_input.get("url_action"), button=True)
    secondary_url_action = _normalize_action(user_input.get("secondary_url_action"), button=True)
    legacy_tap_url = str(user_input.get(CONF_TAP_ACTION_URL) or "").strip()
    legacy_tap_foreground = bool(user_input.get(CONF_TAP_ACTION_FOREGROUND, True))
    if legacy_tap_url:
        _normalize_action({"url": legacy_tap_url, "foreground": legacy_tap_foreground}, button=False)

    return {
        CONF_ENTITY_ID: entity_id,
        CONF_SLUG: slug,
        CONF_WIDGET_NAME: user_input.get(CONF_WIDGET_NAME, "") or "",
        CONF_WIDGET_TEMPLATE: template,
        CONF_WIDGET_TRIGGER_MODE: trigger,
        CONF_WIDGET_POLL_INTERVAL: poll_interval,
        CONF_VALUE_ATTRIBUTE: user_input.get(CONF_VALUE_ATTRIBUTE, "") or "",
        CONF_UNIT: user_input.get(CONF_UNIT, "") or "",
        CONF_MIN_VALUE: min_v,
        CONF_MAX_VALUE: max_v,
        CONF_SEVERITY: user_input.get(CONF_SEVERITY, "") or "",
        CONF_STAT_ROWS: stat_rows,
        CONF_LABEL: user_input.get(CONF_LABEL, "") or "",
        CONF_LABEL_ATTRIBUTE: user_input.get(CONF_LABEL_ATTRIBUTE, "") or "",
        CONF_SUBTITLE_ATTRIBUTE: user_input.get(CONF_SUBTITLE_ATTRIBUTE, "") or "",
        CONF_ICON: user_input.get(CONF_ICON, "") or "",
        CONF_ICON_ATTRIBUTE: user_input.get(CONF_ICON_ATTRIBUTE, "") or "",
        CONF_ACCENT_COLOR: _validate_color_input(user_input.get(CONF_ACCENT_COLOR), allow_empty=True),
        CONF_ACCENT_COLOR_ATTRIBUTE: user_input.get(CONF_ACCENT_COLOR_ATTRIBUTE, "") or "",
        CONF_BACKGROUND_COLOR: _validate_color_input(user_input.get(CONF_BACKGROUND_COLOR), allow_empty=True),
        CONF_TEXT_COLOR: _validate_color_input(user_input.get(CONF_TEXT_COLOR), allow_empty=True),
        "tap_action": tap_action,
        "url_action": url_action,
        "secondary_url_action": secondary_url_action,
        CONF_TAP_ACTION_URL: legacy_tap_url,
        CONF_TAP_ACTION_FOREGROUND: legacy_tap_foreground,
    }


class PushWardWidgetSubentryFlow(config_entries.ConfigSubentryFlow):
    """Configure a tracked widget with one sectioned post-template form."""

    def __init__(self) -> None:
        super().__init__()
        self._step1_input: dict[str, Any] = {}
        self._is_reconfigure: bool = False
        self._details_defaults: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.SubentryFlowResult:
        """Step 1: entity + template + slug."""
        if user_input is not None:
            self._step1_input = user_input
            self._is_reconfigure = False
            return await self.async_step_details()
        return self.async_show_form(
            step_id="user",
            data_schema=_widget_step1_schema(),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            self._step1_input = user_input
            self._is_reconfigure = True
            current = dict(subentry.data)
            self._details_defaults = current
            return await self.async_step_details()
        current = dict(subentry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_widget_step1_schema(defaults=current),
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None) -> config_entries.SubentryFlowResult:
        """Step 2: Configure all widget options in collapsible sections."""
        entity_id = self._step1_input.get(CONF_ENTITY_ID, "")
        template = self._step1_input.get(CONF_WIDGET_TEMPLATE, WIDGET_TEMPLATE_VALUE)
        if user_input is not None:
            flattened = _flatten_sections(user_input)
            try:
                widget_cfg = _parse_widget_input(flattened, self._step1_input)
            except vol.Invalid as exc:
                defaults = self._details_defaults if self._is_reconfigure else None
                return self.async_show_form(
                    step_id="details",
                    data_schema=_widget_sectioned_schema(entity_id, template, defaults),
                    errors={"base": str(exc.msg)},
                )
            title = widget_cfg.get(CONF_WIDGET_NAME) or widget_cfg[CONF_SLUG]
            if self._is_reconfigure:
                return self.async_update_and_abort(
                    self._get_entry(), self._get_reconfigure_subentry(), data=widget_cfg, title=title
                )
            return self.async_create_entry(title=title, data=widget_cfg, unique_id=widget_cfg[CONF_SLUG])

        defaults = self._details_defaults if self._is_reconfigure else None
        return self.async_show_form(
            step_id="details",
            data_schema=_widget_sectioned_schema(entity_id, template, defaults),
            description_placeholders={"entity": entity_id, "template": template},
        )

def _rgb_to_hex(rgb: list[int] | None) -> str:
    """Convert an [R, G, B] list to a '#rrggbb' hex string."""
    if not rgb or not isinstance(rgb, list) or len(rgb) != 3:
        return ""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


_COLOR_HEX_LABELS = {
    "red": "#FF3B30",
    "orange": "#FF9500",
    "yellow": "#FFCC00",
    "green": "#34C759",
    "blue": "#007AFF",
    "purple": "#AF52DE",
    "pink": "#FF2D55",
    "indigo": "#5856D6",
    "teal": "#5AC8FA",
    "cyan": "#32ADE6",
    "mint": "#00C7BE",
    "brown": "#A2845E",
}


def _color_selector() -> SelectSelector:
    """Return PushWard's named palette while allowing custom hex colors."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                {"value": "", "label": "Automatic / PushWard default"},
                *[
                    {"value": color, "label": f"{color.title()} ({_COLOR_HEX_LABELS[color]})"}
                    for color in PUSHWARD_NAMED_COLORS
                ],
            ],
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _compact_step_color_selector() -> SelectSelector:
    """Return short color values suitable for a supporting-text summary."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                {"value": "Auto", "label": "Automatic / PushWard default"},
                *[
                    {
                        "value": color.title(),
                        "label": f"{color.title()} ({_COLOR_HEX_LABELS[color]})",
                    }
                    for color in PUSHWARD_NAMED_COLORS
                ],
            ],
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _compact_step_color_value(value: object) -> str:
    """Format a saved API color for the compact selector."""
    color = str(value).strip().lower()
    if not color:
        return "Auto"
    if color in PUSHWARD_NAMED_COLORS:
        return color.title()
    return str(value).strip()


def _parse_step_color(value: object) -> str:
    """Convert a self-describing step color back to the PushWard API value."""
    raw = str(value or "").strip()
    if not raw or raw.lower() in ("auto", "automatic") or raw.lower().startswith("automatic color"):
        return ""
    if " color" in raw.lower():
        raw = raw[: raw.lower().index(" color")].lower()
    return _validate_color_input(raw, allow_empty=True)


def _action_selector(*, button: bool) -> ObjectSelector:
    """Return a structured foreground-link / silent-webhook editor."""
    fields: dict[str, dict] = {}
    if button:
        fields.update(
            {
                "title": {"label": "Button title (max 64 characters)", "selector": TextSelector()},
                "icon": {"label": "SF Symbol (optional)", "selector": TextSelector()},
            }
        )
    fields.update(
        {
            "url": {"label": "URL or app deep link", "selector": TextSelector()},
            "foreground": {"label": "Open visibly instead of running silently", "selector": BooleanSelector()},
            "method": {
                "label": "Silent webhook method",
                "selector": SelectSelector(SelectSelectorConfig(options=list(TAP_ACTION_METHODS))),
            },
            "headers": {"label": "Silent webhook headers (advanced object)", "selector": ObjectSelector()},
            "body": {
                "label": "Silent webhook body",
                "selector": TextSelector(TextSelectorConfig(multiline=True)),
            },
        }
    )
    return ObjectSelector(ObjectSelectorConfig(fields=fields))


def _color_input_to_str(value: object) -> str:
    """Normalize a named color, custom hex string, or legacy RGB picker value."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return _rgb_to_hex(value)
    return ""


def _validate_color_input(value: object, *, allow_empty: bool = False) -> str:
    """Return a normalized PushWard color or raise a clear form error."""
    color = _color_input_to_str(value)
    if not color and allow_empty:
        return ""
    return validate_color(color)


def _hex_to_rgb(hex_color: str) -> list[int] | None:
    """Convert a '#rrggbb' hex string back to [R, G, B] for the color picker."""
    if not hex_color or not hex_color.startswith("#") or len(hex_color) != 7:
        return None
    try:
        return [int(hex_color[i : i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        return None


def _color_vol_key(conf_key: str, current: dict) -> vol.Optional:
    """Build a color key prefilled with a saved named or custom hex color."""
    value = current.get(conf_key, "")
    return vol.Optional(conf_key, default=value) if value else vol.Optional(conf_key)


def _entity_source_key(conf_key: str, current: dict) -> vol.Optional:
    """Build a vol.Optional key for a companion-entity EntitySelector.

    Pre-fills the saved entity_id when present; otherwise leaves the field empty
    so an unset companion submits as absent rather than an invalid empty entity.
    """
    saved = current.get(conf_key)
    if saved:
        return vol.Optional(conf_key, description={"suggested_value": saved})
    return vol.Optional(conf_key)


def _parse_csv(value: str) -> list[str]:
    """Parse a comma-separated string into a list of stripped, non-empty items."""
    if not value:
        return []
    return [s.strip() for s in value.split(",") if s.strip()]


def _parse_int_list(value: str) -> list[int]:
    """Parse '1,2,3' into [1, 2, 3], silently skipping non-integer tokens."""
    result: list[int] = []
    for token in _parse_csv(value):
        with contextlib.suppress(ValueError):
            result.append(int(token))
    return result


def _serialize_int_list(values: list[int]) -> str:
    """Serialize a list of ints to '1, 2, 3' text for UI editing."""
    return ", ".join(str(v) for v in values) if values else ""


def _parse_state_labels(value: str) -> dict[str, str]:
    """Parse 'key=value, key2=value2' into a dict."""
    if not value:
        return {}
    result: dict[str, str] = {}
    for pair in value.split(","):
        pair = pair.strip()
        if "=" in pair:
            key, val = pair.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key and val:
                result[key] = val
    return result


def _serialize_key_value_pairs(pairs: dict[str, str]) -> str:
    """Serialize a dict to 'key=value, key2=value2' text for UI editing."""
    if not pairs:
        return ""
    return ", ".join(f"{k}={v}" for k, v in pairs.items())


def _parse_thresholds(value: str) -> list[dict]:
    """Parse 'value:color:label, ...' into threshold dicts.

    Format: value[:color[:label]], ...
    Example: '25:red:Hot, 18:blue:Cold, 20'
    """
    if not value:
        return []
    result: list[dict] = []
    for entry in value.split(","):
        parts = [p.strip() for p in entry.strip().split(":")]
        if not parts or not parts[0]:
            continue
        try:
            threshold: dict = {"value": float(parts[0])}
        except ValueError:
            continue
        if len(parts) > 1 and parts[1]:
            threshold["color"] = parts[1]
        if len(parts) > 2 and parts[2]:
            threshold["label"] = parts[2]
        result.append(threshold)
    return result[:5]


def _serialize_thresholds(thresholds: list[dict]) -> str:
    """Serialize threshold dicts back to 'value:color:label, ...' text for editing."""
    if not thresholds:
        return ""
    parts: list[str] = []
    for t in thresholds:
        s = str(t.get("value", ""))
        color = t.get("color", "")
        label = t.get("label", "")
        if color or label:
            s += f":{color}"
        if label:
            s += f":{label}"
        parts.append(s)
    return ", ".join(parts)
