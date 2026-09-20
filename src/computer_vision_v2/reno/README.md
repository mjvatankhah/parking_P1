# RENO — Parking ANPR Desktop App (UI prototype)

A Kivy desktop application for a multi-camera parking ANPR system:
Login, Dashboard (statistics + recent plate records), Cameras, and Camera
Settings. The Cameras screen displays annotated frames from the running backend.

---

## 1. Requirements

- Windows 10/11 (this is the target platform; it also runs on macOS/Linux for testing)
- Python 3.10 or newer

## 2. Setup

Open a terminal / PowerShell inside this folder and run:

```
python -m venv venv
venv\Scripts\activate          (on Windows)
# source venv/bin/activate     (on macOS/Linux, for testing)

pip install -r requirements.txt
```

## 3. Run it

```
python main.py
```

A window titled **RENO** opens on the Login screen.

**Demo login:**
- Username: `admin`
- Password: `1234`

Anything else shows the Persian error message and keeps you on the
Login screen, exactly like a real login would.

## 4. Persian text / font

Persian text is rendered with the bundled **Vazirmatn** font on every platform.

## 5. Project structure

```
reno/
├── main.py                    # starts the app, wires screens together — only wiring, no logic
├── ui/
│   ├── theme.py                # colors, spacing, font registration, the rtl() Persian helper
│   ├── login.py                 # Login screen
│   ├── dashboard.py             # Dashboard screen
│   ├── camera_settings.py       # Camera Settings screen
│   └── components/              # small reusable pieces shared by screens
│       ├── common.py             # Card, buttons, rounded text input, status dot
│       ├── icons.py              # hand-drawn vector icons (no icon files needed)
│       ├── sidebar.py            # left navigation column
│       ├── camera_selector.py    # the "All Cameras ▼" dropdown, driven by camera_service
│       ├── camera_card.py        # one camera tile (name, status, placeholder video)
│       ├── stat_card.py          # one statistic card (big number + icon)
│       └── recent_records.py     # the 50-row recent plate records table
├── services/                   # <-- connect your real backend here (see section 6)
│   ├── auth_service.py
│   ├── camera_service.py
│   ├── dashboard_service.py
│   └── plate_service.py
├── models/
│   ├── camera.py                # Camera dataclass
│   └── plate_record.py          # PlateRecord dataclass
└── assets/
    └── fonts/                   # bundled Vazirmatn font
```

## 6. Where to connect your real backend

Each file in `services/` is a small class with 2-5 methods, currently
backed by in-memory/mock data. To connect your real backend, edit the
**inside** of these methods only — keep the method names and return
types the same, and every screen keeps working without changes:

| File | Methods to replace | Should eventually call |
|---|---|---|
| `services/auth_service.py` | `login(username, password)` | your real authentication |
| `services/camera_service.py` | `get_cameras`, `add_camera`, `update_camera`, `delete_camera` | your `CameraManager` |
| `services/plate_service.py` | `get_recent_records(limit)` | your PostgreSQL query |
| `services/dashboard_service.py` | `get_statistics()` | your real counters |

`camera_service` also has a small publish/subscribe mechanism
(`subscribe()` / `_notify()`): whenever you change the camera list,
call `self._notify()` at the end, and the Dashboard's camera selector
and camera grid will refresh themselves automatically — you do not
need to touch `ui/dashboard.py`.

## 7. What each screen does

- **Login** (`ui/login.py`) — RENO branding, username/password
  fields, "remember me", a login button and a "forgot password" link.
  Calls `auth_service.login()`; on success it hands control back to
  `main.py`, which switches to the Dashboard.
- **Dashboard** (`ui/dashboard.py`) — a header with a Help & Support
  button, three statistic cards, the live camera panel with its dynamic
  selector, and a full-width table of the 50 most recent plate records.
- **Camera Settings** (`ui/camera_settings.py`) — a form to add or
  edit a camera (ID, RTSP/video-file source type, source, entry/exit
  role) and a table of configured cameras with edit/delete actions.
- **Search / Reports** (`ui/placeholder_screen.py`) — real, navigable
  screens (same header + sidebar shell as every other page) with
  nothing built into them yet on purpose — an honest "not ready yet"
  empty state instead of a popup that interrupted navigation. Build
  the real feature into `PlaceholderScreen._build()`'s content area
  when it's ready; the header/sidebar/navigation wiring doesn't need
  to change.

## 8. Known limitations (by design, for this iteration)

- Camera configuration is stored in `data/cameras.json`; plate records and
  authentication still use the prototype services.
- Search and Reports are empty placeholder screens (see above).

## 9. Notes on the source files you sent me

The Balsamiq wireframe (`New_Project_1.bmpr`) has three pages —
لاگین (Login), داشبورد (Dashboard), تنظیمات (Settings) — and I built
the layout of each screen to match its structure and control
positions. The reference screenshot was used only for the visual
style (colors, rounded cards, spacing), as instructed.

Two small additions beyond a literal 1:1 wireframe trace, both called
out explicitly elsewhere in your written instructions rather than
invented by me: the **"forgot password" link** on Login, and the
**Add/Edit/Delete/Save/Cancel buttons** on Camera Settings (the
wireframe's Camera Settings page didn't have visible button controls
in the exported data, but your notes explicitly asked for them).

## Processed camera previews

From the repository root, run the backend and UI in separate terminals:

```sh
.venv/bin/python -m computer_vision_v2.main_v2
.venv/bin/python -m computer_vision_v2.reno.main
```

Open **دوربین‌ها** to see the backend frames with person/car bounding boxes,
track IDs and confidence. Both processes must run as the same user on the same
machine, using the same temporary directory. The preview bridge retains only
the newest JPEG per camera, at up to 10 updates/second. Frames older than five
seconds are hidden. The UI does not open another capture or run another model.

The backend reads camera configuration at startup; restart it after changing
camera settings. Preview drawing works on a copy and does not alter the images
used by tracking, line crossing, crop selection or OCR.
