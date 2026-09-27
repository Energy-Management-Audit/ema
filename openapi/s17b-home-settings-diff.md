# S17b home and settings OpenAPI diff

Generated from `openapi/ema.v1.json` after `uv run python scripts/generate_openapi_s16.py`, compared with the S17b shell contract.

| Operation | Change |
|---|---|
| `POST /backups` | New; `{}` → 201 `BackupResult`; 409 `backup_dir_missing` or `backup_changed`, 424 `backup_failed` |
| `PUT /settings/providers/{provider}/key` | New; `ProviderKeyInput` → 204; 400 `provider_invalid`, 422 `validation_error`, 424 `keyring_unavailable` |
| `DELETE /settings/providers/{provider}/key` | New; 204; 400 `provider_invalid`, 424 `keyring_unavailable` |
| `PUT /settings` | Adds `backup_dir_invalid` 400 and the `backup_dir` patch field |

New schemas: `BackupResult`, `BackupState`, `ProviderKeyInput`. `ProviderState` adds `hint` and `source`; `SettingsView` adds `workspace` and `backup`; `SettingsPatch` adds `backup_dir`.
