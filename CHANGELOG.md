# Changelog

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
