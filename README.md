# Dungeon Mapper

A self-hosted, browser-based dungeon generator and live-play VTT for D&D 5e. Part of the HomeHub suite on Raspberry Pi.

**Live at:** `http://webpi.local:8085`

---

## Current Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1 — Generator | ✅ Complete | Generate, render, save/load dungeons |
| Phase 2 — Live Play | ✅ Complete | WebSocket multiplayer, tokens, DM controls |
| Phase 3 — Fog of War | ✅ Complete | Shadowcasting FOV, explored tiles, DM reveal controls |
| Phase 4 — Encounter Integration | Planned | |

---

## How to Use

### Starting a Session (DM)

1. Go to `http://webpi.local:8085`
2. Choose dungeon type, size, and levels → click **Generate**
3. When satisfied with the map, click **Start Live Session**
4. You land on the DM view — share the 6-character session code from the sidebar
5. Players join at `http://webpi.local:8085/join`

### Joining as a Player

1. Go to `http://webpi.local:8085/join`
2. Enter the session code, your name, and pick a token color
3. You appear on the map at the dungeon entrance with fog covering unexplored areas

### Moving Tokens

- **Tap/click** your token → yellow ring appears (selected)
- **Tap/click** any floor tile → token moves there
- **Drag** the token directly to a tile — also works

### Navigating the Map

| Action | How |
|--------|-----|
| Zoom in/out | Scroll wheel · +/− buttons · Pinch on iPad |
| Pan / scroll | Click and drag on empty map space |
| Reset zoom | Click the % display between +/− buttons |

### DM Controls (Sidebar)

| Control | What it does |
|---------|-------------|
| Session Code | Share with players to join |
| Copy Join Link | Copies the full join URL to clipboard |
| Fog of War | Toggle fog on/off, set sight radius, reveal all |
| Map Legend | Expandable key showing all map icons |
| All Tokens | Lists tokens on current level; click ✕ to remove monsters |
| Place Monster | Enter name, pick color, click **Place on Map**, then click a floor tile |

### Map Icon Key

| Icon | Color | Meaning |
|------|-------|---------|
| ⊙ | Green | Entrance — party starts here |
| ▲ | Gold | Stairs Up — climb to previous level |
| ▼ | Orange | Stairs Down — descend to next level |
| ⚔ | Red | Spawn Point — enemy encounter location |
| ★ | Yellow | Treasure — loot or chest |
| ▬ | Brown | Door — tap/click to open or close |
| ● | Custom color | Player token — shows first initial |
| ● | Custom color | Monster token — placed by DM |

Hover over any tile or token to see its name in the status bar.

---

## Fog of War

### How it works

- **Black** — never seen; tile type completely hidden
- **Dim overlay** — previously explored; you remember the layout but can't see details
- **Full color** — currently visible; within your line of sight

Fog uses **recursive shadowcasting** (Björn Bergström's algorithm) computed locally in the browser. Walls and closed doors block line of sight. The FOV recalculates instantly whenever your token moves or a door opens/closes.

### Token visibility

- **Player tokens** are always visible to all players (you know where your party is)
- **Monster tokens** are hidden in fog — players only see enemies in their current FOV

### DM Fog Controls

| Control | Effect |
|---------|--------|
| Fog Enabled toggle | Turns fog on/off for all players simultaneously |
| Sight Radius | Sets how far players can see (1–15 squares; default 6 sq = 30 ft torch) |
| Reveal All | Instantly marks every non-wall tile as explored for all players |

The DM always sees the full map regardless of fog settings.

---

## TV / Table Display

The app is designed to run on a 55" TV installed in a tabletop. The DM controls the session from a laptop while the TV shows the player view full-screen.

- Scroll to zoom in for larger tokens, scroll back out for full-map view
- Click and drag to pan when zoomed in — no scrollbars
- For mini-figure play, zoom out to use the grid as position reference (each □ = 5 ft)

---

## Planned: Session Save/Resume (Phase 2.5)

Session state (token positions, open doors, explored fog) lives in memory and is lost if the server restarts. Planned: persist to SQLite so a game can be paused and resumed later.

---

## Phase 4 — Encounter Integration (Planned)

- DM panel "Import Encounter" button per spawn-point room (always manual, never auto)
- Calls the Encounter Generator HTTP API (port 8084) with party level + CR range
- Monsters from the encounter appear as tokens on the map
- Track encounter state per room: Not Started / In Progress / Cleared
- Session XP tally in DM panel

---

## Technical Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI |
| Real-time | FastAPI WebSockets + `websockets>=12.0` |
| Templates | Jinja2 |
| Map Rendering | HTML5 Canvas 2D API |
| UI | Alpine.js |
| Styling | Tailwind CSS CDN |
| Database | SQLite + SQLAlchemy |
| Server | Uvicorn on Raspberry Pi (systemd) |

### WebSocket Protocol

**Client → Server:**
```json
{ "action": "move_token",       "token_id": "player_1", "x": 12, "y": 7, "level": 0 }
{ "action": "place_token",      "name": "Goblin", "color": "#dc2626", "x": 15, "y": 9, "level": 0 }
{ "action": "remove_token",     "token_id": "monster_abc12345" }
{ "action": "toggle_door",      "x": 10, "y": 6 }
{ "action": "toggle_fog",       "enabled": true }
{ "action": "set_sight_radius", "radius": 8 }
{ "action": "reveal_all" }
{ "action": "ping" }
```

**Server → Client broadcasts:**
```json
{ "event": "state_sync",          "tokens": [...], "open_doors": {...}, "active_clients": [...], "fog_enabled": true, "sight_radius": 6 }
{ "event": "token_moved",         "token_id": "player_1", "x": 12, "y": 7, "level": 0 }
{ "event": "token_added",         "token": { "id": "...", "name": "...", "color": "...", ... } }
{ "event": "token_removed",       "token_id": "monster_abc12345" }
{ "event": "door_toggled",        "x": 10, "y": 6, "open": true }
{ "event": "fog_settings_changed","fog_enabled": true, "sight_radius": 8 }
{ "event": "fog_reveal_all" }
{ "event": "client_connected",    "client_id": "player_1", "name": "Cory", "role": "player" }
{ "event": "client_disconnected", "client_id": "player_1" }
```

---

## Dungeon Generation

### Area Type → Algorithm

| Area Type | Algorithm | Character |
|-----------|-----------|-----------|
| Dungeon | BSP Tree | Rectangular rooms, straight corridors |
| Cave | Cellular Automata | Organic, irregular caverns |
| Crypt | BSP Tree + symmetry | Symmetrical wings, long halls |
| Sewer | Drunk Walk + grid snap | Winding tunnels |
| Forest Ruins | BSP Tree + erosion | Crumbling irregular edges |

### Size Presets

| Size | Grid | Approx Rooms |
|------|------|--------------|
| Small | 40×30 | 6–10 |
| Medium | 70×50 | 12–20 |
| Large | 100×70 | 20–35 |
| Epic | 150×100 | 35–60 |

Each square = 5 ft. Dungeons are saved as seed + parameters and regenerated deterministically — the DB stores no tile data.

---

## Project Structure

```
DungeonMapper/
├── app/
│   ├── templates/
│   │   ├── base.html               # Nav + shared head (generator pages)
│   │   ├── index.html              # Generator form + saved list
│   │   ├── dm_view.html            # DM live session (standalone)
│   │   ├── player_view.html        # Player live session (standalone)
│   │   ├── player_join.html        # Join form
│   │   └── partials/
│   │       ├── dungeon_result.html # Canvas + controls (HTMX swap)
│   │       └── saved_list.html
│   ├── static/
│   │   ├── canvas.js               # Generator map rendering (Alpine component)
│   │   └── multiplayer.js          # Live-play rendering + WebSocket + FOV (Alpine component)
│   ├── auth.py                     # Session code + token generation
│   ├── database.py
│   ├── dungeon_gen.py              # Procedural generation algorithms
│   ├── main.py                     # FastAPI routes + WebSocket handlers
│   ├── models.py                   # SavedDungeon, DungeonSession, Player
│   └── session_manager.py          # In-memory WebSocket connection registry
├── requirements.txt
└── README.md
```

---

## Implementation Notes

### Fog of War (Phase 3)
FOV is computed **client-side** in `multiplayer.js` using recursive shadowcasting across 8 octants. Each player maintains their own `exploredByLevel` set (one `Set<"x,y">` per dungeon level) that accumulates as they explore. Currently stored in browser memory — lost on page refresh until session save/resume is implemented.

### Token Interaction
Click-to-select + click-to-move (standard VTT model):
1. Click a token you control → yellow selection ring
2. Click any floor tile → token moves there
3. Drag directly to a tile also works

### Map Navigation
Pan and zoom use independent mechanisms:
- **Zoom**: tile-size multiplier (0.3×–5×); canvas grows and the wrap div overflows
- **Pan**: `pointerdown` on empty space records `scrollLeft`/`scrollTop` + cursor position; `pointermove` updates scroll offset; a 5px threshold prevents pan from firing on clicks
- Scrollbars hidden via `scrollbar-width: none` / `::-webkit-scrollbar` CSS while keeping `overflow-auto` for programmatic pan

### Session Recovery
If the server restarts, the in-memory `ActiveSession` is lost. The WebSocket endpoint regenerates the dungeon from DB params on reconnect — token positions and fog state reset. Addressed in the planned session save/resume feature.

---

## Design Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | FOV computation | Client-side JS — no server round-trip per move, instant feedback |
| 2 | Token visibility | Player tokens always visible; monster tokens hidden by fog |
| 3 | Pan vs scroll | Click-drag pan with hidden scrollbars — cleaner for TV/tablet use |
| 4 | Zoom | Scroll wheel (no modifier needed) + pinch + buttons |
| 5 | Auth | Session code + DM token only; `auth.py` isolated for future login |
| 6 | Encounter trigger | Always manual — DM clicks Import, never auto |
| 7 | Encounter integration | HTTP API to port 8084 (apps stay independent) |
