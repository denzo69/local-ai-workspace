# Plugin Interface Test Plan

This test plan defines validation for the planned plugin interface.

## Test categories

| Area | Tests |
|---|---|
| Manifest parsing | valid manifest, invalid JSON, missing fields, unknown capability |
| Plugin path safety | safe plugin path, traversal attempt, symlink/outside-root handling |
| Risk classification | low/medium/high accepted, missing risk rejected |
| Registration | valid plugin registers tool, invalid plugin skipped, duplicate plugin rejected |
| Failure handling | plugin import error, plugin register error, malformed entrypoint |
| Capability checks | tool capability allowed, source connector capability allowed, unknown capability denied |
| Audit logging | plugin load, enable, disable and failure events are logged |
| Tool policy | high-risk plugin blocked by default, explicit enable required |
| Example plugin | example CRM lookup plugin returns safe mocked output |
| Docs/release | plugin docs exist and README does not claim marketplace support |

## Suggested test files

```text
tests/test_plugin_manifest.py
tests/test_plugin_registry.py
tests/test_plugin_safety.py
tests/test_example_crm_plugin.py
tests/test_enterprise_plugin_docs.py
```

## Golden plugin test

1. create a temporary plugin directory
2. write a valid `plugin.json`
3. load the plugin registry
4. assert the plugin is discovered
5. assert the capability and risk level are recorded
6. assert the example tool can be called through a safe mock path
7. assert an audit event is written

## Negative tests

The sprint must include tests for:

- invalid JSON manifest
- missing plugin name
- missing risk level
- unknown capability
- plugin path traversal
- duplicate plugin name
- plugin import failure
- high-risk plugin without explicit enablement

## Done criteria

Sprint 3 is done when:

- plugin manifest validation has tests
- plugin registry has tests
- plugin risk classification has tests
- unsafe plugins are denied by default
- plugin registration failures are contained
- example plugin is documented and tested
- core app still works without plugins
