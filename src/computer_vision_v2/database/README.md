# Database schema

`schema.sql` creates a fresh database. It keeps `gate.id` and `camera.id`
independent; `camera.gate_id` is unique, so a gate cannot have two cameras.
Configure the gate and camera records in PostgreSQL before starting the vision
pipeline. The pipeline checks this relation and synchronizes the camera source,
type and role from `reno/data/cameras.json` on each start.

For a new camera configured as `cam-1`, register its distinct gate first:

```sql
INSERT INTO gate (id) VALUES ('north-gate');
INSERT INTO camera (id, gate_id, source, source_type, role)
VALUES ('cam-1', 'north-gate', 'rtsp://camera/stream', 'rtsp', 'entry');
```

Keep the actual RTSP credentials in the local configuration, not in examples or
logs. The camera ID in PostgreSQL must match the camera ID in the JSON file.

For a database created with the earlier `TIMESTAMP` columns, first inspect
`SHOW TimeZone` and confirm that existing times were recorded in that zone.
Then apply `migrations/001_timestamptz.sql` with `psql -X -v ON_ERROR_STOP=1 -f`.
The migration preserves rows and interprets old wall-clock values in the
database's configured time zone. It does not invent or change gate IDs.
