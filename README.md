# monitorforge-core

Shared canonical schema and ingestion contract for environmental monitoring
web apps (Peñasquito, Bisbee, and future projects).

## What this is

Extracted from the Peñasquito monitoring database, generalized. See
`../monitorforge-ideas.md` for the original extraction plan and
`../DB Review/` for the lessons-learned/blueprint documents this follows.

## What actually transfers between projects (and what doesn't)

Reading Peñasquito's `sensor_mapping.py`, `upload_parsing.py`, and
`auto_qc.py` made this concrete: **parsing and channel-binding logic is not
reusable code.** It is fused to Peñasquito's specific sensor vocabulary
(TEROS depth/nest tokens), its CSV/HTML upload formats, and its exact flag
taxonomy. Bisbee's CR6/TOA5 `.dat` files share none of that.

What *does* transfer:

- **The canonical schema** (`models/`) — Sensor → SensorDeployment →
  Measurement/DerivedMeasurement, calibration history, Upload/UploadRowIssue
  audit trail, quality flags. Vendor-agnostic.
- **The ingestion contract** (`contracts/`) — typed shapes every project's
  parser and binder must produce, so they're interchangeable from the
  writer's point of view.
- **The ingestion writer** (`ingestion/`) — idempotent insert, duplicate/
  conflict detection, Upload audit record creation. This only needs
  `(deployment_id, variable_id, ts, value)` tuples — it doesn't care what
  produced them.

Each project (Peñasquito, Bisbee, ...) still writes its own parser and
binder against its own sensors. That work is not optional and not
skippable by this package — it's the part that is genuinely
project-specific.

## Scope of this version

Deliberately minimal ("minimal slice" over "big-bang extraction" — see
project history). Explicitly **not** included yet, and left in each
project's own codebase until a project actually needs it pulled out:

- QC rule engine (auto_qc.py's flagging/summary logic)
- Calibration math
- Derived variable calculations
- Charting
- GIS / shapefile ingestion (also why location models use plain
  lat/lon floats instead of PostGIS `Geography` for now)

## Genericizations made vs. Peñasquito's schema

- Dropped the `deployment_plot_required` NOT NULL constraint — "plot"
  (1x1 mile mining polygon) is Peñasquito-specific. Deployments require a
  station, not a plot/area.
- Location hierarchy is `Project -> MonitoringArea? -> MonitoringStation`,
  with `MonitoringArea` optional — not every project groups stations into
  large-area polygons.
- Dropped the hardcoded `America/Mexico_City` default on `Upload.source_timezone`
  — every project must set its own default explicitly.
- PostGIS `Geography` columns replaced with plain `latitude`/`longitude`
  floats until GIS ingestion is actually built for a project that needs it.

## Usage

A consuming Flask app initializes `monitorforge_core.db` (a
`flask_sqlalchemy.SQLAlchemy` instance) against its own app, then imports
the models it needs from `monitorforge_core.models`.

```python
from monitorforge_core.db import db
from monitorforge_core import models  # registers ORM models with db

db.init_app(app)
```
