"""
services/mock_mode.py

One flag, one file. Every place in the service layer that can
generate fake data checks this before doing so.

By default MOCK_DATA_ENABLED is False: a fresh run of this app shows
real, honest empty states everywhere (no cameras, no records, 0
statistics) because there genuinely is no data yet - exactly the
state a production build would be in before a backend is connected. This was
a deliberate fix made during the UI/UX audit: the previous version
auto-generated 2 fake cameras and 50 fake plate records on startup so
the screens looked "full", which misrepresents what real data will
look like and hides bugs in the empty-state UI.

To turn mock/demo data on for a design review or a demo, run:

    setx RENO_MOCK_DATA 1        (Windows, permanent)
    set RENO_MOCK_DATA=1         (Windows, current terminal only)
    python main.py

or on macOS/Linux:

    RENO_MOCK_DATA=1 python main.py

This must stay the ONLY switch. If you add more mock data generators
later, gate them on MOCK_DATA_ENABLED too, so turning demo data off
always turns all of it off.
"""

import os

MOCK_DATA_ENABLED = os.environ.get("RENO_MOCK_DATA", "").strip() == "1"
