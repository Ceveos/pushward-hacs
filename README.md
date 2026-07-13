# PushWard HACS

PushWard HACS is a HACS-compatible Home Assistant custom integration for
driving [PushWard](https://pushward.app) Live Activities and widgets from Home
Assistant entities. It is focused on an obvious, staged setup experience rather
than a single wall of fields or comma-delimited configuration strings.

This project is derived from the MIT-licensed
[`mac-lucky/pushward-hass`](https://github.com/mac-lucky/pushward-hass). See
[`NOTICE.md`](NOTICE.md) and [`LICENSE`](LICENSE) for attribution and terms.

## Why an integration instead of a blueprint

Unlike a blueprint, PushWard HACS can:

- Keep track of whether an activity is already running
- Throttle and deduplicate rapid entity updates
- Watch companion entities automatically
- Persist log and attribute history across restarts
- Backfill timeline data from Home Assistant Recorder
- Resolve icons and colors from entity/device metadata
- Validate API keys and configuration before saving
- Register native PushWard actions and quota sensors

## Guided configuration

Adding a Live Activity uses two pages:

1. **Entity and layout** — choose the lifecycle entity and one of eight layouts.
2. **Configuration** — one form with lifecycle, layout content, appearance, tap
   actions, and advanced behavior grouped into collapsible sections.

Widgets use the same pattern: choose the entity/layout, then configure content,
appearance, and refresh behavior in one sectioned form.

Compound layouts use repeatable forms:

- Timeline series: add entity rows instead of typing
  `Label=sensor.example:attribute`.
- Timeline thresholds: add value/color/label rows.
- Board tiles: add label/entity/attribute/unit/icon rows.
- Log columns: add source entity/attribute/label/unit rows.
- Widget stat lists: add label/entity/attribute/unit rows.
- Steps: add one row per step with freeform whole-number controls for parallel
  jobs and relative-width parts, plus a guided or custom color. Collapsed rows
  summarize all four values, so a long
  dishwasher wash stage remains both easy to scan and independent from the
  number of visual job rows.

## Delivery channels

PushWard HACS exposes each channel independently, so an automation can use any
combination:

| Goal | Home Assistant action |
| --- | --- |
| Live Activity only | `pushward_hacs.update_activity_<layout>` (upserts automatically) |
| Notification only | `pushward_hacs.send_notification` |
| Any combination of channels | `pushward_hacs.dispatch` |
| Email only | `pushward_hacs.send_email` |
| Entity-driven Live Activity | Add a tracked entity in Devices & services |
| Entity-driven widget | Add a tracked widget in Devices & services |

The notification action includes interruption level, critical volume, grouping
and collapse IDs, rich media, icon, metadata, activity linking, up to ten action
buttons, foreground links or silent webhooks, and inbox-only delivery. Live
Activity actions cover every layout plus structured tap targets, priority,
sound, lifecycle, TTLs, AlarmKit, timelines, boards, logs, and current-step live
progress.

`Send via PushWard` puts Live Activity, notification, widget, and email channels
in collapsed sections; enable only the channels that automation needs. The
focused layout actions remain the clearest choice for a single Live Activity.
All activity updates use API upsert automatically, so a separate create action
is optional unless you want to set a display name or TTL metadata first:

```yaml
actions:
  - action: pushward_hacs.update_activity_steps
    data:
      slug: dishwasher
      state: ongoing
      current_step: 1
      steps:
        - label: Wash
          parallel_jobs: 1
          weight: 4
          color: Blue
        - label: Rinse
          parallel_jobs: 1
          weight: 1
          color: Cyan
        - label: Dry
          parallel_jobs: 1
          weight: 2
          color: Orange
      progress: 0.25
  - action: pushward_hacs.send_notification
    data:
      title: Dishwasher
      body: Wash cycle started
      activity_slug: dishwasher
```

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

This repository already uses the standalone layout required by HACS. To install
it as a custom repository:

1. Open **HACS > Integrations**.
2. Choose **Custom repositories**.
3. Add `https://github.com/Ceveos/pushward-hacs` as category **Integration**.
4. Search for **PushWard HACS**, install it, and restart Home Assistant.
5. Go to **Settings > Devices & services > Add integration** and search for
   **PushWard HACS**.
6. Paste an integration key from the PushWard iOS app.

The integration uses the separate `pushward_hacs` domain, so it can be installed
alongside the official `pushward` integration. HACS installs this fork into
`/config/custom_components/pushward_hacs`.

## Manual installation

Copy `custom_components/pushward_hacs` into your Home Assistant configuration:

```text
/config/custom_components/pushward_hacs
```

Restart Home Assistant and add **PushWard HACS** from **Devices & services**.

## Development

The project targets Home Assistant 2026.6 or newer and Python 3.14.2 or newer.

```bash
python -m pip install -e . --group dev
pytest
ruff check .
```

The inherited upstream test suite covers API behavior, mappers, managers,
services, configuration flows, diagnostics, and quota handling. PushWard HACS
adds staged-flow and structured-selector coverage alongside those tests.
