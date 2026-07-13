# Changelog

## 0.3.0

- Replace raw Steps arrays with named repeatable rows for parallel jobs,
  relative step length, and color; collapsed rows summarize all four values.
- Replace state-label and Timeline mini-languages with structured rows and
  improve source/value summaries for thresholds, series, tiles, log columns,
  and widget statistics.
- Add all three structured foreground/deep-link/silent-webhook action slots to
  every Live Activity layout and every widget layout.
- Add guided notification media/actions, Board tiles, Log lines, Timeline
  series/thresholds, and strict local validation for colors, lengths, and limits.
- Add `Send via PushWard`, which can deliver any combination of Live Activity,
  notification, widget, and email channels from one Home Assistant action.
- Remove the deprecated catch-all activity action and obsolete staged-flow UI.
- Replace stale partial translations with a consistent English fallback until
  each complete catalog can be reviewed.
- Align the development runtime with Home Assistant 2026.6 (Python 3.14.2+).

## 0.2.0

- Replace the multi-page post-template setup with one form containing
  collapsible lifecycle, content, appearance, and refresh sections.
- Replace ambiguous Steps lists with per-step rows that distinguish parallel
  jobs from relative duration/width and optional color.
- Add current-step live progress, duration weighting, and per-step colors.
- Require Home Assistant 2026.6 or newer for native config-flow sections.
- Add friendly field titles, valid ranges, units, and named-option labels across
  the guided forms.
- Pre-populate PushWard's 12 named colors while retaining custom RGB/RGBA hex
  input and compatibility with previously saved RGB picker values.

## 0.1.0

- Fork the full PushWard Home Assistant integration under the MIT license.
- Add guided four-stage Live Activity and widget setup flows.
- Replace comma-delimited timeline, threshold, board, log, and stat-list inputs
  with repeatable structured forms.
- Retain the upstream PushWard entity and widget data model.
- Use the isolated `pushward_hacs` Home Assistant domain so this integration can
  coexist with the official `pushward` integration.
