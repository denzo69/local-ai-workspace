# Plugin Architecture

This document describes the planned plugin architecture for Local AI Workspace Enterprise Edition.

## Design principles

- Plugins must declare their capabilities explicitly.
- Plugins must have a risk classification before they can be enabled.
- Plugin failures must not crash the core application.
- Plugin loading must be auditable.
- Unsafe plugin behavior must be blocked by default.
- The core app should remain usable without plugins.

## Proposed plugin layout

```text
plugins/
  example_crm_lookup/
    plugin.json
    plugin.py
    README.md
    tests/
```

## Manifest format

Suggested `plugin.json` shape:

```json
{
  "name": "example_crm_lookup",
  "version": "0.1.0",
  "description": "Example CRM lookup plugin",
  "entrypoint": "plugin:register",
  "capabilities": ["tool"],
  "risk_level": "low|medium|high",
  "requires_network": false,
  "requires_filesystem": false,
  "requires_secrets": false
}
```

## Plugin registry

Suggested module:

```text
app/plugin_registry.py
```

Suggested responsibilities:

- discover plugin directories
- parse and validate manifests
- reject invalid or unsafe plugins
- register safe tools/connectors
- expose plugin status for admin/debug views
- write audit events for plugin load/enable/disable

## Risk model

| Risk level | Meaning | Default behavior |
|---|---|---|
| low | pure computation or read-only local metadata | allow when enabled |
| medium | local file or source access | require explicit enable + audit |
| high | network, secrets, mutation or external side effects | disabled by default |

## Registration flow

```text
plugin directory discovered
  -> manifest parsed
  -> schema validated
  -> risk classified
  -> admin/config enable check
  -> entrypoint imported
  -> plugin registers tools/sources
  -> audit event written
```

## Safety checks

Before enabling a plugin, the system should check:

- manifest is valid JSON
- plugin name is safe
- entrypoint is defined
- capabilities are allowed
- risk level is present
- requested capabilities match configured policy
- plugin path stays under configured plugin root

## Example plugin idea

`example_crm_lookup`:

- accepts a customer id or name
- returns mocked CRM data in tests
- does not require real network access
- demonstrates input validation and safe output formatting

## Open questions

- Should plugins be enabled through config, admin UI or both?
- Should plugin import be allowed in production mode?
- Should plugins run in-process or behind a subprocess boundary later?
- Should high-risk plugins require signed manifests in future?
