# PushWard Studio

PushWard Studio is a HACS-compatible Home Assistant custom integration for
driving [PushWard](https://pushward.app) Live Activities and widgets from Home
Assistant entities. It is focused on an obvious, staged setup experience rather
than a single wall of fields or comma-delimited configuration strings.

This project is derived from the MIT-licensed
[`mac-lucky/pushward-hass`](https://github.com/mac-lucky/pushward-hass). See
[`NOTICE.md`](NOTICE.md) and [`LICENSE`](LICENSE) for attribution and terms.

## Why an integration instead of a blueprint

Unlike a blueprint, PushWard Studio can:

- Keep track of whether an activity is already running
- Throttle and deduplicate rapid entity updates
- Watch companion entities automatically
- Persist log and attribute history across restarts
- Backfill timeline data from Home Assistant Recorder
- Resolve icons and colors from entity/device metadata
- Validate API keys and configuration before saving
- Register native PushWard actions and quota sensors

## Guided configuration

Adding a Live Activity uses four short pages:

1. **Entity and layout** — choose the lifecycle entity and one of eight layouts.
2. **Lifecycle and updates** — start/end states, slug, name, priority, update
   interval, sound, and retention.
3. **Layout content** — only fields relevant to the selected template, with
   direct entity and attribute selectors.
4. **Appearance and actions** — subtitle, icon, colors, and tap behavior.

Widgets use the same pattern: entity/layout, content, appearance, then refresh
behavior.

Compound layouts use repeatable forms:

- Timeline series: add entity rows instead of typing
  `Label=sensor.example:attribute`.
- Timeline thresholds: add value/color/label rows.
- Board tiles: add label/entity/attribute/unit/icon rows.
- Log columns: add source entity/attribute/label/unit rows.
- Widget stat lists: add label/entity/attribute/unit rows.

## Supported features

- Eight Live Activity layouts: generic, countdown, steps, alert, gauge,
  timeline, board, and log
- Five widget layouts: value, progress, gauge, status, and stat list
- Idempotent activity/widget creation (the PushWard API upserts duplicate slugs)
- Automatic activity creation, start, update, two-phase completion, end, and
  deletion
- Priority, ended TTL, stale TTL, throttling, and content deduplication
- Companion value/progress/time/subtitle/current-step/fired-at entities
- Multi-entity timelines, board tiles, log columns, and widget stat rows
- Timeline recorder backfill and persistent attribute history
- AlarmKit countdown alarms and snooze controls
- Structured tap actions and silent webhooks
- Native actions for activity management, notifications, email, and widgets
- Account usage, limits, reset time, and subscription sensors
- Reauthentication, diagnostics, and quota repair notifications

## HACS installation

This directory is a standalone HACS repository layout. Publish the contents of
`home-assistant/pushward-studio/` as the root of its own public GitHub
repository, then:

1. Open **HACS > Integrations**.
2. Choose **Custom repositories**.
3. Add the repository URL as category **Integration**.
4. Search for **PushWard Studio**, install it, and restart Home Assistant.
5. Go to **Settings > Devices & services > Add integration** and search for
   **PushWard Studio**.
6. Paste an integration key from the PushWard iOS app.

The integration uses the `pushward` domain and therefore cannot be installed at
the same time as the official `pushward-hass` integration. Remove one before
installing the other.

## Manual installation

Copy `custom_components/pushward` into your Home Assistant configuration:

```text
/config/custom_components/pushward
```

Restart Home Assistant and add **PushWard Studio** from **Devices & services**.

## Development

The project targets Home Assistant 2025.7 or newer and Python 3.13.

```bash
python -m pip install -e . --group dev
pytest
ruff check .
```

The inherited upstream test suite covers API behavior, mappers, managers,
services, configuration flows, diagnostics, and quota handling. PushWard Studio
adds staged-flow and structured-selector coverage alongside those tests.
