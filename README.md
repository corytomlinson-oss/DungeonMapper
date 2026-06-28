# Dungeon Mapper

A self-hosted, browser-based dungeon generator and live-play VTT for D&D 5e. Part of the HomeHub suite on Raspberry Pi.

Designed to grow across four phases — from a standalone procedural dungeon generator to a full multiplayer virtual tabletop with fog of war and integrated random encounters.

**Live at:** `http://webpi.local:8085`

---

## Current Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1 — Generator | ✅ Complete | Generate, render, save/load dungeons |
| Phase 2 — Live Play | ✅ Complete | WebSocket multiplayer, tokens, DM controls |
| Phase 3 — Fog of War | Planned | |
| Phase 4 — Encounter Integration | Planned | |

---

## How to Use

### Starting a Session (DM)

1. Go to `http://webpi.local:8085`
2. Choose dungeon type, size, and levels → click **Generate**
3. When satisfied with the map, click **Start Live Session**
4. You land on the DM view — note the 6-character session code at the top of the sidebar
5. Share the code with players: `http://webpi.local:8085/join`

### Joining as a Player

1. Go to `http://webpi.local:8085/join`
2. Enter the session code, your name, and pick a token color
3. You appear on the map at the dungeon entrance

### Moving Tokens

- **Tap/click** your token → it highlights with a yellow ring (selected)
- **Tap/click** any floor tile → token moves there
- **Drag** the token directly to a tile — also works
- **Pinch** on iPad to zoom in/out; use **+/−** buttons or **Ctrl+scroll** on desktop

### DM Controls (Sidebar)

| Control | What it does |
|---------|-------------|
| Copy Join Link | Copies the player join URL to clipboard |
| Map Legend | Expandable key showing all map icons |
| All Tokens | Lists tokens on current level; click ✕ to remove monsters |
| Place Monster | Enter a name, pick color, click **Place on Map**, then click a floor tile |

### Map Icon Key

| Icon | Color | Meaning |
|------|-------|---------|
| ⊙ | Green | Entrance — party starts here |
| ▲ | Gold | Stairs Up — climb to previous level |
| ▼ | Orange | Stairs Down — descend to next level |
| ⚔ | Red | Spawn Point — enemy encounter location |
| ★ | Yellow | Treasure — loot or chest |
| ▬ | Brown | Door — tap/click to open or close |
| ● | Custom | Player token — initial letter of player name |
| ● | Custom | Monster token — placed by DM |

Hover over any tile or token to see its name in the status bar.

---

## TV / Table Display

The app is designed to run on a 55" TV installed in a table top. At default zoom the map scales to the browser width; zoom in for larger token display. The DM controls the map from a laptop while the TV shows the player view full-screen.

- Use **+** zoom button (or pinch/Ctrl+scroll) to scale up for the TV
- The canvas grows beyond the viewport and becomes scrollable — use a keyboard or mouse to pan on the TV browser
- For mini-figure play, zoom out to see the whole map and use the grid as position reference (each □ = 5 ft)

---

## Planned: Session Save/Resume (Phase 2.5)

Currently session state (token positions, open doors) lives in memory and is lost if the server restarts. Planned feature: persist session state to SQLite so a game can be paused and resumed.

---

## Planned Features

### Phase 3 — Fog of War
- Player view: only tiles the player has visited or can currently see are visible
- Line-of-sight engine: field-of-view per token using recursive shadowcasting
- Fog persists per player across the session (visited tiles stay revealed)
- DM controls: reveal a room, reveal entire level, reset fog
- DM view always shows full map with a fog overlay showing what players can see
- Configurable sight radius per token (torchlight vs darkvision)

### Phase 4 — Encounter Integration
- DM clicks a mob spawn point → "Import Encounter" button appears in DM panel
- Calls the Encounter Generator HTTP API (port 8084) with party level + CR range
- Imported encounter assigned to the room; monsters appear as tokens on the map
- Track encounter state per room: Not Started / In Progress / Cleared
- Rooms highlighted on map by encounter state
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

All messages are JSON.

**Client → Server:**
```json
{ "action": "move_token",   "token_id": "player_1", "x": 12, "y": 7, "level": 0 }
{ "action": "place_token",  "name": "Goblin", "color": "#dc2626", "x": 15, "y": 9, "level": 0 }
{ "action": "remove_token", "token_id": "monster_abc12345" }
{ "action": "toggle_door",  "x": 10, "y": 6 }
{ "action": "ping" }
```

**Server → Client broadcasts:**
```json
{ "event": "state_sync",         "tokens": [...], "open_doors": {...}, "active_clients": [...] }
{ "event": "token_moved",        "token_id": "player_1", "x": 12, "y": 7, "level": 0 }
{ "event": "token_added",        "token": { "id": "...", "name": "...", "color": "...", ... } }
{ "event": "token_removed",      "token_id": "monster_abc12345" }
{ "event": "door_toggled",       "x": 10, "y": 6, "open": true }
{ "event": "client_connected",   "client_id": "player_1", "name": "Cory", "role": "player" }
{ "event": "client_disconnected","client_id": "player_1" }
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
│   │   └── multiplayer.js          # Live-play rendering + WebSocket (Alpine component)
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

## Phase 2 Implementation Notes

### Token Interaction Model
Tokens use a **click-to-select / click-to-move** model (same as Roll20):
1. Tap/click a token you control → yellow selection ring appears
2. Tap/click any floor tile → token moves there
3. Drag directly to a tile also works in one gesture

This model works identically on iPad touch and desktop mouse, which was the key design requirement.

### Player Token Sync
When a player's WebSocket connects, their token is added to server memory and:
- The connecting player receives a full `state_sync` (all tokens + doors)
- All other clients (DM) receive a `token_added` event so the token appears immediately

### Zoom
The base tile size is calculated to fit the dungeon width in the container. The zoom multiplier (0.3×–5×) scales tiles up or down. At zoom > 1, the canvas overflows its container and becomes scrollable — `overflow-auto` on the wrapper handles this.

### Session Recovery
If the server restarts, the in-memory `ActiveSession` is lost. The WebSocket endpoint regenerates the dungeon from DB parameters when a client reconnects to a session not in memory. Token positions are reset; this will be addressed in the session save/resume feature.

---

## Design Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Token movement | Click-to-select + click-to-move (also supports drag) |
| 2 | Zoom | Tile-size multiplier (0.3×–5×) + scrollable container |
| 3 | Authentication | Session code + DM token only (auth.py isolated for future login) |
| 4 | Encounter trigger | Always manual — DM clicks Import, never auto |
| 5 | Target devices | iPad + laptop; TV display at 5× zoom via player view |
| 6 | Encounter integration | HTTP API call to port 8084 (apps stay independent) |
