# Dungeon Mapper

A self-hosted, browser-based dungeon generator and live play tool for D&D 5e. Part of the HomeHub suite on Raspberry Pi.

Designed to grow across four phases — from a standalone procedural dungeon generator to a full multiplayer virtual tabletop with fog of war and integrated random encounters.

---

## Planned Features

### Phase 1 — Dungeon Generator (Offline Tool)
- Procedural dungeon/cave/crypt generation from configurable parameters
- Area type presets: Dungeon, Cave, Crypt, Sewer, Forest Ruins
- Configurable size (small / medium / large / epic) and number of levels
- Automatic room layout, corridor connections, doors
- Special room placement: entrance, boss room, treasure room, dead ends
- Staircases connecting levels (up/down, positioned logically)
- Mob spawn point placement scaled to room size and dungeon level
- Printable / exportable map view
- Save and reload dungeons

### Phase 2 — Live Play (Single Session, Shared Screen)
- Load a saved dungeon into a live session
- Player tokens: name, color, icon — each player controls their own token
- DM places/removes tokens and monsters
- **Drag-and-drop** token movement on the canvas (pointer events, works on touch and mouse)
- Real-time sync via WebSockets — all connected browsers update instantly
- DM view: full map always visible
- No login required — session join via 6-character code shared by the DM

### Phase 3 — Fog of War
- Player view: only tiles the player has visited or can currently see are visible
- Line-of-sight engine: field-of-view per token using raycasting
- Fog persists per player across the session (visited tiles stay revealed)
- DM controls: reveal a room, reveal entire level, reset fog
- DM view always shows full map with a fog overlay showing what players can see
- Configurable sight radius per token (torchlight vs darkvision)

### Phase 4 — Encounter Integration
- DM clicks a mob spawn point → DM panel shows an "Import Encounter" button (never auto-triggered)
- Calls the Encounter Generator HTTP API (port 8084) with party level + CR range → returns encounter JSON
- Imported encounter assigned to the room; monsters appear as tokens on the map
- Track encounter state per room: Not Started / In Progress / Cleared
- Encounter rooms highlighted on map by state (green = cleared, red = active, gray = pending)
- XP tally for the session shown in DM panel

---

## Technical Design

### Stack

| Layer | Tech | Notes |
|-------|------|-------|
| Backend | FastAPI | Same as Encounter Generator |
| Real-time | FastAPI WebSockets | Required for Phase 2+ multiplayer sync |
| Templates | Jinja2 | Initial page load only in Phase 2+ |
| Map Rendering | HTML5 Canvas | Tile-based; handles fog, tokens, LOS efficiently |
| UI Controls | Alpine.js | Panels, modals, form state |
| Styling | Tailwind CSS CDN | Consistent with rest of HomeHub |
| Database | SQLite + SQLAlchemy | Dungeon storage and session state |
| Server | Uvicorn | systemd service on Pi |

**Why Canvas over SVG or CSS Grid?**
Canvas handles fog of war (per-pixel alpha masking), raycasting line-of-sight, and smooth token animation at 60fps. SVG struggles with large tile grids and fog masking. CSS Grid can't do LOS at all.

**Why WebSockets over HTMX polling?**
Token movement and fog updates need sub-100ms latency for a good play experience. HTMX long-polling would work for fog reveal (DM action → all players update) but not for smooth token drag-and-drop. WebSockets handle both cleanly.

**Touch + mouse support (iPad & laptop)**
Canvas drag-and-drop uses the [Pointer Events API](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events) (`pointerdown`, `pointermove`, `pointerup`) which works identically for touch, stylus, and mouse without separate event handlers. Target devices: iPad (Chrome/Safari) and laptop (Windows + Mac).

**Authentication**
Session code only for now (no accounts). The `Player` model and session lookup are isolated behind a thin `auth.py` module so that a proper login system (username/password or OAuth) can be dropped in later without touching the WebSocket handlers or canvas code.

### Port
`8085` (adjacent to Encounter Generator at `8084`)

---

## Dungeon Generation Algorithm

### Area Type → Algorithm

| Area Type | Algorithm | Character |
|-----------|-----------|-----------|
| Dungeon | BSP Tree (Binary Space Partitioning) | Rectangular rooms, straight corridors |
| Cave | Cellular Automata | Organic, irregular, open caverns |
| Crypt | BSP Tree + symmetry pass | Symmetrical wings, long halls |
| Sewer | Drunk Walk + grid snap | Winding tunnels, occasional chambers |
| Forest Ruins | BSP Tree + erosion pass | Rooms with crumbling irregular edges |

### BSP Tree (primary algorithm)
1. Start with the full map as a single rectangle
2. Recursively split into two sub-rectangles (alternate horizontal/vertical cuts)
3. Place a room inside each leaf node with random padding
4. Connect sibling rooms with an L-shaped corridor
5. Walk back up the tree connecting all rooms via corridors

### Tile Types

| Tile | Value | Description |
|------|-------|-------------|
| Wall | 0 | Impassable, blocks LOS |
| Floor | 1 | Passable |
| Door | 2 | Passable, blocks LOS until opened |
| Stairs Up | 3 | Transition to level above |
| Stairs Down | 4 | Transition to level below |
| Spawn Point | 5 | Mob encounter marker |
| Treasure | 6 | Treasure room marker |
| Entrance | 7 | Party entry point |

### Size Presets (tiles)

| Size | Grid | Rooms (approx) |
|------|------|----------------|
| Small | 40×30 | 6–10 |
| Medium | 70×50 | 12–20 |
| Large | 100×70 | 20–35 |
| Epic | 150×100 | 35–60 |

### Multi-Level
- Each level is an independent grid stored as a JSON 2D array
- Stairs Down on level N paired with Stairs Up on level N+1 (positions matched)
- Dungeon difficulty scales with depth: spawn point CR range increases per level

---

## Data Models

### Dungeon
```
id            int PK
name          str
area_type     str          ("dungeon", "cave", "crypt", "sewer", "ruins")
width         int
height        int
num_levels    int
seed          int          (RNG seed for reproducibility)
levels_json   text         JSON array of 2D tile grids, one per level
rooms_json    text         JSON array of room metadata (position, type, level)
created_at    datetime
```

### DungeonSession (Phase 2)
```
id            int PK
dungeon_id    int FK
session_code  str          (6-char join code, e.g. "XK7R2M")
dm_token      str          (secret token for DM browser)
state_json    text         JSON: token positions, door states, encounter states
fog_json      text         JSON: per-player revealed tile sets, keyed by player_id
created_at    datetime
```

### Player (Phase 2)
```
id            int PK
session_id    int FK
name          str
color         str          (hex, e.g. "#3b82f6")
icon          str          ("warrior", "mage", "rogue", "cleric", "ranger")
x             int
y             int
level         int          (dungeon level the player is currently on)
```

### RoomEncounter (Phase 4)
```
id            int PK
session_id    int FK
room_index    int
encounter_id  int          (FK to Encounter Generator DB, if integrated)
status        str          ("pending", "active", "cleared")
monsters_json text         imported encounter data snapshot
```

---

## WebSocket Protocol (Phase 2)

All messages are JSON. Client → Server actions:

```json
{ "action": "drag_start",  "player_id": 3 }
{ "action": "drag_end",    "player_id": 3, "x": 12, "y": 7 }
{ "action": "open_door",   "x": 10, "y": 6 }
{ "action": "reveal_room", "room_index": 4 }             // DM only
{ "action": "place_token", "type": "monster", "x": 15, "y": 9 } // DM only
{ "action": "import_encounter", "room_index": 2, "encounter_json": {...} } // DM only
{ "action": "ping" }
```

Server → All clients broadcast:

```json
{ "event": "state_update", "state": { ...full session state... } }
{ "event": "fog_update",   "player_id": 3, "revealed": [[x,y], ...] }
{ "event": "player_joined","player": { "id": 3, "name": "Cory", "color": "#3b82f6" } }
```

---

## Fog of War Design (Phase 3)

### Field of View Algorithm
Using **recursive shadowcasting** (Björn Bergström's algorithm) — the standard for tile-based roguelikes:
- O(visible tiles) time complexity — fast enough for 60fps
- Handles walls, pillars, and diagonal occlusion correctly
- Sight radius configurable per token (default 6 tiles; darkvision extends to 12)

### Fog Rendering (Canvas)
1. Render the full dungeon tile grid to an offscreen canvas
2. Create a fog layer: black fill over the entire map
3. For each player token, compute their FOV and "cut out" visible tiles using `globalCompositeOperation = 'destination-out'`
4. Previously-visited tiles rendered at 40% opacity (seen but not currently visible)
5. Never-seen tiles stay fully black
6. Composite the fog layer over the map canvas

### DM Panel
- Toggle between "DM View" (no fog) and "Player Preview" (see what players see)
- Room-by-room reveal buttons in the sidebar
- "Reveal All" and "Reset Fog" controls

---

## Session Flow (Phase 2+)

```
DM opens app → Creates dungeon (or loads saved) → Starts session
  → Gets session code (e.g. XK7R2M) + DM link
  → Shares code with players

Players open app → Enter session code + name + pick token color/icon
  → Dropped into player view at dungeon entrance

DM sees full map; players see fog-covered map with their token visible
DM controls: reveal rooms, place monster tokens, import encounters (always manual — never auto-triggered)
Players: drag token to move, tap doors to open/close
```

---

## Project Structure (planned)

```
DungeonMapper/
├── app/
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html          # Generator form
│   │   ├── dungeon_view.html   # DM view (full map)
│   │   ├── player_view.html    # Player view (fog of war)
│   │   └── partials/
│   │       ├── dungeon_result.html
│   │       └── session_panel.html
│   ├── static/
│   │   └── canvas.js           # Map rendering + WebSocket client
│   ├── database.py
│   ├── dungeon_gen.py          # Procedural generation algorithms
│   ├── fov.py                  # Field-of-view / shadowcasting
│   ├── main.py                 # FastAPI routes + WebSocket handlers
│   ├── models.py               # Dungeon, DungeonSession, Player, RoomEncounter
│   └── session_manager.py      # In-memory WebSocket connection registry
├── systemd/
│   └── dungeon-mapper.service
├── requirements.txt
└── README.md                   # This file
```

---

## Implementation Phases — Checklist

### Phase 1 — Generator
- [ ] BSP tree dungeon generation
- [ ] Cellular automata cave generation
- [ ] Multi-level support with linked stairs
- [ ] Spawn point placement
- [ ] Canvas rendering of generated dungeon
- [ ] Save / load dungeons (SQLite)
- [ ] Generator UI (form: type, size, levels, seed)
- [ ] systemd service + Pi deployment

### Phase 2 — Live Play
- [ ] WebSocket server with session management
- [ ] Session creation and join-code flow
- [ ] DM and player token rendering on canvas
- [ ] Token drag-and-drop (Pointer Events API — touch + mouse unified)
- [ ] Door open/close state sync
- [ ] DM-only controls panel
- [ ] `auth.py` session-code layer (designed to be swappable for login later)

### Phase 3 — Fog of War
- [ ] Recursive shadowcasting FOV
- [ ] Canvas fog layer with composite rendering
- [ ] Per-player revealed tile persistence
- [ ] DM reveal controls (room, level, all)
- [ ] Sight radius by token type (torch / darkvision)

### Phase 4 — Encounter Integration
- [ ] HTTP API endpoint on Encounter Generator (port 8084) for external calls
- [ ] DM panel "Import Encounter" button per spawn-point room
- [ ] Call Encounter Generator API with party level + CR → receive encounter JSON
- [ ] Assign encounter to room; place monster tokens on map
- [ ] Encounter state tracking per room (pending / active / cleared)
- [ ] Session XP tally

---

## Design Decisions Log

| # | Question | Decision | Notes |
|---|----------|----------|-------|
| 1 | Token movement style | **Drag-and-drop** | Pointer Events API (touch + mouse unified) |
| 2 | Authentication | **Session code only** for now | `auth.py` isolated so login can be added later without touching WS handlers |
| 3 | Encounter trigger | **Always manual** (DM clicks Import) | Never auto-triggered when players enter a room |
| 4 | Target devices | **iPad + laptop** (Windows & Mac) | No phone optimization needed; Pointer Events covers iPad touch |
| 5 | Encounter Generator integration | **HTTP API call** to port 8084 | Keeps apps independent; Encounter Generator will need a JSON endpoint added |
