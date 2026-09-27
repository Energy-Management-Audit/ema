# S18c OpenAPI diff

Generated contract: `openapi/ema.v1.json` and `openapi/s16-diff.md` are refreshed with
`scripts/generate_openapi_s16.py`.

| Operation | Change |
|---|---|
| `GET /settings/update` | Added session-protected `UpdateInfo` response: `current`, `latest`, `newer`, `notes`, `page_url`, `download_url`, `checked_at`, `state` (`ok`, `no_release`, `unavailable`). No route-specific problem code. |
| `POST /backups` | Added documented `400 backup_dir_invalid` response. |
