# Translations

`en.json` is the canonical source file. The other language catalogs currently
contain the same English source so every locale receives accurate, internally
consistent instructions while the pre-release UI is still changing. Translate a
catalog only when the complete file can be reviewed; partially translated,
outdated screens are intentionally not shipped.

## Reporting a bad translation

Open an issue at <https://github.com/Ceveos/pushward-hacs/issues> with:

- The language code (filename without `.json`)
- The JSON key path (e.g. `config.step.user.data.integration_key`)
- The current text and your suggested correction

## Submitting a correction

1. Edit the appropriate `<lang>.json` file
2. Keep the key structure identical to `en.json` — do not add, remove, or rename keys
3. Preserve placeholders like `{entity_id}` verbatim
4. Open a PR

## Adding a new language

1. Copy `en.json` to `<tag>.json` using the [HA-supported language tag](https://www.home-assistant.io/docs/configuration/customizing-devices/#translating-your-integration) (e.g. `sv.json`, `ko.json`)
2. Translate the string values, leaving keys and placeholders untouched
3. Open a PR — no code changes required; HA picks up new translation files automatically

## Using English regardless of HA language

Change your Home Assistant user profile language to English in **Settings → user profile → Language**. This only affects your account, not the whole HA instance.
