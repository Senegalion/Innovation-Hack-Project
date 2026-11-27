# SMARTLAB: Laboratory Digital Twin

SMARTLAB is a "smart lab" ecosystem. A live 3D twin of the lab connects navigation, daily **quests**, inventory with consumption forecasting, chat tied to places, smart help, safety escalation and gamification. Together they form one loop (*Laboratory Intelligence*):

> The inventory sees trypsin expiring in 3 days → the calendar shows it is needed for tomorrow's Enzyme Kinetics run → a quest is generated → the worker accepts it on the morning board → the map plans the optimal route → they scan the QR code at the freezer → verify and log it → inventory updates → XP is awarded.

## Run it

**Docker (full stack: Postgres + Qdrant + S3-compatible storage):**
```bash
docker compose up --build                      # UI → http://localhost:8080, API docs → http://localhost:8000/docs
WITH_DOCLING=1 docker compose up --build       # also installs Docling for PDF parsing (large image)
```

**Local dev (SQLite + local file storage, hot reload):**
```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/pytest                               # 16 end-to-end API tests

cd frontend && npm install && npm run dev      # http://localhost:5173 (proxies /api and /ws to 127.0.0.1:8000)
```
Every external service is optional and has a fallback. Without `S3_ENDPOINT`, files go to `backend/data/files`. Without `QDRANT_URL`, search runs in the database. Without Docling, PDFs are parsed with pypdf. Without `SEGMENTATION_URL`, segmentation uses the built-in geometric method. The demo data is seeded on first start, with dates relative to today. Delete `backend/smartlab.db` and `backend/data` (or run `docker compose down -v`) to reset it.
The UI is **Polish by default**. The PL | EN switch in the header changes the interface, and the backend renders system-generated text (quests, suggestions, Smart Help, routes, assistant, onboarding, emergency steps) in the language from the `Accept-Language` header. Text that people type (names, notes, messages) is shown as written. The demo data is in Polish.
Add `?tour=0` to the URL to skip onboarding. Add `?scan=HPLC-04` to simulate a QR scan.
Write requests identify the user with the `X-User-Id` header (demo identity). Leader and admin endpoints check the user's access level.

## Backend layout
```
backend/app/
  db.py            roles, users, labs, spaces, workstations, machines, materials, samples, experiments,
                   tasks (quests), activity_logs, channels, messages, incidents, notifications,
                   documents + document_chunks, point_rules, challenges, reconstructions
  services/        forecast · quests · spatial (A*, floor plans) · segmentation · documents (Docling/Qdrant)
                   storage (S3/local) · people (smart help, competence, onboarding) · gamification · assistant
  routers/         labs · assets · quests · social · incidents · admin · documents · spatial · optional
```

## Features → where

| Requirement | Backend | UI |
|---|---|---|
| 3D twin, rotate/zoom/pinch, lab dropdown | `GET /api/labs/{id}` (machines + workstations + spaces) | `LabScene.tsx`, header title |
| **2D floor plan from 3D maps** | `POST /api/labs/{id}/floorplan/from-model` (GLB/OBJ/PLY/XYZ → occupancy grid by height band). `GET …/floorplan?format=svg`. Export the twin as `…/export/model.glb` (for Blender) or a synthetic `…/export/pointcloud.ply` | |
| **Semantic + instance segmentation** | `POST /api/labs/{id}/reconstructions` with `method=geometric\|sam3d\|openpcseg`. The geometric method splits objects by height, labels them (bench / instrument / cabinet / fume hood / wall) and matches them to known assets. SAM-3D / OpenPCSeg go through an external service at `SEGMENTATION_URL`, with geometric as the fallback. `POST /api/reconstructions/{id}/accept` turns a detected object into a new asset | |
| Optimal route with restrictions and task time | `POST /api/route` with `stops` or `quest_ids`. A* adds extra cost in hazard zones, blocks closed areas, and blocks restricted areas for roles not on the access list. It returns per-stop arrival and work times plus a list of unreachable stops | "Plan optimal route" |
| QR / manual ID (stations, reagents, tubes) | `GET /api/scan/{code}` (also returns the quests at that location), `GET /api/qr/{code}.svg`, samples CRUD + history | Scan dialog, card QR |
| Equipment: verification date + uncertainty, service, certificate, last user / servicer, logs, notes | `POST /api/equipment/{id}/logs` (a reading outside the uncertainty raises an alert and an incident). Predicts the next failure from past failure intervals, and the next inspection date | Equipment card |
| Materials: expiry, forecast → order-by date, logs, notes | Forecast from planned experiments, plus checks for wrong storage (storage class), count mismatches, missing SDS and waste risk in €. Actions: take / restock / check / move / dispose / use-before-expiry | Stock tab, reagent card |
| Hybrid daily quests + AI-style suggestions | Generated from inventory, calendar, failure predictions, incidents, help requests and intern activity, plus leader quests. Suggestions are personalised by distance to your planned work and by your skills | Quests tab ("Suggested: …") |
| Accept / reject with reason / later / hand to leader / report problem / escalate | `POST /api/quests/{id}/action` (`accept`, `reject`, `snooze`, `delegate`, `problem`, `escalate`, `complete`, `unassign`) | Quest cards |
| Rejection analytics | `GET /api/admin/stats` → `rejection_signals`, `execution_problems` | Management panel |
| Chat: lab, per device, DMs, groups with invites, attachments, sharing, @Name / @role / @here | `/api/channels`, `/api/channels/{id}/invite`, `/api/messages` (`attachments`, `share`) | Chat drawer |
| Smart Help, knowledge base (problem / cause / solution), competence map | `/api/help`, `/api/knowledge`, `/api/competence` | Smart help tab |
| Newcomer side quests and intern alerts | An intern's first use of an instrument, or taking a hazardous reagent, notifies the responsible person and the mentor and creates an "Assist …" quest | |
| Onboarding (tips per role, who does what, mentor) | `GET /api/onboarding/{user}` | Onboarding dialog |
| Notifications | `GET /api/notifications`, pushed live over `/ws` | Toasts |
| Gamification: rules set by management, badges, team challenges, ESG | `/api/point-rules` (admin), `/api/challenges`, `GET /api/admin/stats` → `esg` | Me tab, Management panel |
| Escalation, roles, admin panel | `POST /api/incidents` returns the steps to take and the nearest eyewash / shower / exit for high and critical reports. Admin: `/api/users`, `/api/roles`, `/api/labs/{id}/assets`, `/api/assets/{id}`, `/api/labs/{id}/spaces/{id}`, `PATCH /api/labs/{id}` | Management panel |
| Documents (Docling, S3, Qdrant) | `POST /api/documents` → stored in S3 → Docling (or pypdf) → chunked → indexed in Qdrant. `GET /api/documents/search` | |
| Assistant "where is…?" (EN/PL) | `POST /api/assistant`: matches devices, reagents, samples, spaces and safety points, and adds relevant documentation snippets | Bottom search bar |

**Optional features (stubs that return `{"enabled": false}`, never an exception):** AI answers over documentation (`POST /api/assistant/ai`), automatic inspection notifications (`/api/notifications/inspections`), MCP (`/mcp`, `/api/mcp/tools`), NFC tags (`POST /api/nfc/{tag}`, which points to `/api/scan`).

## Your own labs (3D models)

1. Sign in as a manager (avatar menu → Dr. Anna Kowalska) and open **Management panel → Labs & map**.
2. **New laboratory**: enter a code, name and size. The lab appears in the lab dropdown.
3. **Upload your lab 3D model**: a GLB from Blender (OBJ/PLY/STL are converted to GLB). The backend:
   - aligns the model to the lab coordinates and resizes the lab to the model bounds,
   - creates equipment and workstations from top-level objects (objects named like asset IDs, e.g. `HPLC-04`; walls, floor and ceiling are skipped),
   - links each 3D object to its asset, so clicking the object opens the equipment card,
   - regenerates the 2D floor plan used for routing.
4. Optional: in Blender, add custom properties to objects (`smartlab_id`, `smartlab_name`, `smartlab_kind`, `smartlab_category`, `smartlab_storage`, `smartlab_skip`) and run:
   ```bash
   blender lab.blend --background --python tools/blender/smartlab_export.py -- out/ --upload http://localhost:8000 lab-lab-305 u-anna
   ```
   This exports the GLB plus a `*.smartlab.json` manifest and uploads both (`POST /api/labs/{id}/model`).
5. Fine-tune in the same tab: equipment positions and sizes, zones (closed / restricted by role), and safety points (exits, eyewash, shower, first aid, extinguisher).
6. **AI reconstruction from a scan**: upload a point cloud or mesh, run segmentation, then add any detected objects that don't match existing equipment.

API: `POST /api/labs`, `POST|DELETE /api/labs/{id}/model`, `PUT /api/labs/{id}/spaces/{space}`, `PATCH /api/labs/{id}`, `POST /api/labs/{id}/assets`, `PATCH|DELETE /api/assets/{id}`.

## Stack
- **Backend:** Python, FastAPI, SQLAlchemy, PostgreSQL, WebSocket, NumPy + trimesh (3D), Qdrant, S3 (boto3; SeaweedFS in Docker), Docling / pypdf, segno (QR)
- **Frontend:** React 19, TypeScript, Vite, Tailwind v4, shadcn-style components (Radix), Three.js / React Three Fiber / drei, Zustand
- **Theme:** black and white with one Tiffany accent (`#3CD0C0`)

## 5-minute demo script
1. Show the **onboarding** as Tomek (intern), then the 3D twin. Rotate and zoom it. HPLC-04 is pulsing.
2. Open **Quests**. Accept "Reorder Trypsin" and "Prepare WB-1", then use **Plan optimal route**.
3. Open **Stock → Acetonitrile**. The forecast shows when it drops below the minimum and the *order-by* date.
4. Click **HPLC-04 → Smart help**. Michał is the top match, and the knowledge base already has the fix.
5. Ask for help in the device **Discussion** and show the chat badge plus the real-time update.
6. **Report** a spill (high), then switch the user to Dr. Anna Kowalska, open the **Management panel** and resolve it. The resolution goes into the knowledge base.

## Why it matters (pitch numbers, from survey-based research)
- 45% of lab workers had an accident (Nasrallah et al. 2022, N=220). Accidents correlate with missing training.
- 25–38% of researchers took part in an accident they didn't report (Ménard & Trant 2020).
- Only 26% get safety training within 30 days of starting. Only 68% of labs document near-misses. 25% can't find required training (Pinhas et al. 2026).

These are self-reported, perception-level data, not hard accident statistics.
