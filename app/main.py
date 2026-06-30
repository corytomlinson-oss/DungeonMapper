import os
from fastapi import FastAPI, Request, Form, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Optional

from app.database import Base, engine, get_db, SessionLocal
from app.models import SavedDungeon, DungeonSession, Player
from app.dungeon_gen import generate_dungeon
from app.auth import generate_code, generate_token
from app.session_manager import manager

os.makedirs("data", exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


# ── Phase 1: Dungeon Generator ───────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    saved = db.query(SavedDungeon).order_by(SavedDungeon.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(request, "index.html", {"saved": saved})


@app.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    area_type: str = Form(...),
    size: str = Form(...),
    num_levels: int = Form(...),
    seed: str = Form(""),
):
    parsed_seed = int(seed) if seed.strip().isdigit() else None
    dungeon = generate_dungeon(area_type, size, num_levels, parsed_seed)
    return templates.TemplateResponse(request, "partials/dungeon_result.html", {"dungeon": dungeon})


@app.post("/save", response_class=HTMLResponse)
def save_dungeon(
    request: Request,
    name: str = Form(""),
    area_type: str = Form(...),
    size: str = Form(...),
    num_levels: int = Form(...),
    seed: int = Form(...),
    db: Session = Depends(get_db),
):
    record = SavedDungeon(
        name=name.strip() or None,
        area_type=area_type,
        size=size,
        num_levels=num_levels,
        seed=seed,
    )
    db.add(record)
    db.commit()
    return HTMLResponse(
        "<p class='text-green-600 font-semibold'>Saved!</p>"
        "<script>window.dispatchEvent(new Event('dungeon-saved'))</script>"
    )


@app.get("/dungeons", response_class=HTMLResponse)
def list_dungeons(request: Request, db: Session = Depends(get_db)):
    saved = db.query(SavedDungeon).order_by(SavedDungeon.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(request, "partials/saved_list.html", {"saved": saved})


@app.get("/dungeons/{dungeon_id}", response_class=HTMLResponse)
def load_dungeon(dungeon_id: int, request: Request, db: Session = Depends(get_db)):
    record = db.query(SavedDungeon).get(dungeon_id)
    if not record:
        return HTMLResponse("<p class='text-red-500'>Dungeon not found.</p>", status_code=404)
    dungeon = generate_dungeon(record.area_type, record.size, record.num_levels, record.seed)
    dungeon["saved_name"] = record.name
    return templates.TemplateResponse(request, "partials/dungeon_result.html", {"dungeon": dungeon})


@app.post("/dungeons/{dungeon_id}/delete", response_class=HTMLResponse)
def delete_dungeon(dungeon_id: int, request: Request, db: Session = Depends(get_db)):
    record = db.query(SavedDungeon).get(dungeon_id)
    if record:
        db.delete(record)
        db.commit()
    saved = db.query(SavedDungeon).order_by(SavedDungeon.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(request, "partials/saved_list.html", {"saved": saved})


# ── Phase 2: Live Sessions ───────────────────────────────────────────────────

def _load_or_create_active_session(record: DungeonSession):
    """Ensure dungeon is live in memory, regenerating from DB params if needed."""
    active = manager.get(record.code)
    if not active:
        dungeon = generate_dungeon(record.area_type, record.size, record.num_levels, record.seed)
        active = manager.create(record.code, record.dm_token, dungeon)
    return active


@app.post("/session/create")
def create_session(
    area_type: str = Form(...),
    size: str = Form(...),
    num_levels: int = Form(...),
    seed: int = Form(...),
    db: Session = Depends(get_db),
):
    code = generate_code()
    while db.query(DungeonSession).filter(DungeonSession.code == code).first():
        code = generate_code()

    dm_token = generate_token()
    record = DungeonSession(
        code=code, dm_token=dm_token,
        area_type=area_type, size=size, num_levels=num_levels, seed=seed,
    )
    db.add(record)
    db.commit()

    dungeon = generate_dungeon(area_type, size, num_levels, seed)
    manager.create(code, dm_token, dungeon)

    return RedirectResponse(f"/session/{code}/dm?token={dm_token}", status_code=303)


@app.get("/session/{code}/dm", response_class=HTMLResponse)
def dm_view(code: str, token: str, request: Request, db: Session = Depends(get_db)):
    record = db.query(DungeonSession).filter(DungeonSession.code == code.upper()).first()
    if not record or token != record.dm_token:
        return HTMLResponse("<p class='text-red-500'>Invalid session or DM token.</p>",
                            status_code=403)
    active = _load_or_create_active_session(record)
    return templates.TemplateResponse(request, "dm_view.html", {
        "dungeon": active.dungeon,
        "session": record,
    })


@app.get("/join", response_class=HTMLResponse)
def join_page(request: Request, code: str = ""):
    return templates.TemplateResponse(request, "player_join.html", {"prefill_code": code.upper()})


@app.post("/join")
def join_session(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    color: str = Form(...),
    db: Session = Depends(get_db),
):
    code = code.upper().strip()
    record = db.query(DungeonSession).filter(DungeonSession.code == code).first()
    if not record:
        return templates.TemplateResponse(request, "player_join.html",
            {"prefill_code": code, "error": "Session not found. Check the code and try again."},
            status_code=404)
    player = Player(session_code=code, name=name.strip()[:20], color=color)
    db.add(player)
    db.commit()
    db.refresh(player)
    return RedirectResponse(f"/session/{code}/play?pid={player.id}", status_code=303)


@app.get("/session/{code}/play", response_class=HTMLResponse)
def player_view(code: str, pid: int, request: Request, db: Session = Depends(get_db)):
    code = code.upper()
    record = db.query(DungeonSession).filter(DungeonSession.code == code).first()
    player = db.query(Player).filter(Player.id == pid, Player.session_code == code).first()
    if not record or not player:
        return HTMLResponse("<p class='text-red-500'>Session or player not found.</p>",
                            status_code=404)
    active = _load_or_create_active_session(record)
    return templates.TemplateResponse(request, "player_view.html", {
        "dungeon": active.dungeon,
        "session": record,
        "player": player,
    })


# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{code}")
async def websocket_endpoint(
    ws: WebSocket,
    code: str,
    role: str = Query("player"),
    pid: Optional[int] = Query(None),
    token: Optional[str] = Query(None),
):
    code = code.upper()
    db = SessionLocal()
    try:
        # Recover session from DB if not in memory
        active = manager.get(code)
        if not active:
            record = db.query(DungeonSession).filter(DungeonSession.code == code).first()
            if not record:
                await ws.close(code=4004)
                return
            if role == "dm" and token != record.dm_token:
                await ws.close(code=4003)
                return
            dungeon = generate_dungeon(record.area_type, record.size, record.num_levels, record.seed)
            active = manager.create(code, record.dm_token, dungeon)

        # Auth
        new_player_token = None
        if role == "dm":
            if token != active.dm_token:
                await ws.close(code=4003)
                return
            client_id = "dm"
            display_name = "DM"
        else:
            if not pid:
                await ws.close(code=4003)
                return
            client_id = f"player_{pid}"
            existing_token = next((t for t in active.tokens if t["id"] == client_id), None)
            if not existing_token:
                player = db.query(Player).filter(
                    Player.id == pid, Player.session_code == code
                ).first()
                if not player:
                    await ws.close(code=4004)
                    return
                display_name = player.name
                ex, ey = manager.find_entrance(active.dungeon)
                new_tok = {
                    "id": client_id, "type": "player",
                    "name": player.name, "color": player.color,
                    "x": ex, "y": ey, "level": 0,
                }
                active.tokens.append(new_tok)
                new_player_token = new_tok
            else:
                display_name = existing_token["name"]

        await manager.connect(code, ws, role, client_id, display_name)
        await ws.send_json(manager.snapshot(code))
        # Notify all OTHER clients (DM) about the new player token
        if new_player_token:
            await manager.broadcast(code, {
                "event": "token_added", "token": new_player_token,
            }, exclude=ws)
        await manager.broadcast(code, {
            "event": "client_connected",
            "client_id": client_id,
            "name": display_name,
            "role": role,
        }, exclude=ws)

        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "move_token":
                token_id = data.get("token_id")
                if role == "player" and token_id != client_id:
                    continue
                x, y, lvl = data.get("x"), data.get("y"), data.get("level", 0)
                for t in active.tokens:
                    if t["id"] == token_id:
                        t["x"], t["y"], t["level"] = x, y, lvl
                        break
                await manager.broadcast(code, {
                    "event": "token_moved",
                    "token_id": token_id, "x": x, "y": y, "level": lvl,
                })

            elif action == "place_token" and role == "dm":
                tok = {
                    "id": f"monster_{len(active.tokens)}",
                    "type": "monster",
                    "name": data.get("name", "M"),
                    "color": data.get("color", "#dc2626"),
                    "x": data["x"], "y": data["y"],
                    "level": data.get("level", 0),
                }
                active.tokens.append(tok)
                await manager.broadcast(code, {"event": "token_added", "token": tok})

            elif action == "remove_token" and role == "dm":
                tid = data.get("token_id")
                active.tokens = [t for t in active.tokens if t["id"] != tid]
                await manager.broadcast(code, {"event": "token_removed", "token_id": tid})

            elif action == "toggle_door":
                x, y = data.get("x"), data.get("y")
                key = f"{x},{y}"
                active.open_doors[key] = not active.open_doors.get(key, False)
                await manager.broadcast(code, {
                    "event": "door_toggled", "x": x, "y": y,
                    "open": active.open_doors[key],
                })

            elif action == "toggle_fog" and role == "dm":
                active.fog_enabled = bool(data.get("enabled", not active.fog_enabled))
                await manager.broadcast(code, {
                    "event": "fog_settings_changed",
                    "fog_enabled": active.fog_enabled,
                    "sight_radius": active.sight_radius,
                })

            elif action == "set_sight_radius" and role == "dm":
                active.sight_radius = max(1, min(15, int(data.get("radius", 6))))
                await manager.broadcast(code, {
                    "event": "fog_settings_changed",
                    "fog_enabled": active.fog_enabled,
                    "sight_radius": active.sight_radius,
                })

            elif action == "reveal_all" and role == "dm":
                await manager.broadcast(code, {"event": "fog_reveal_all"})

            elif action == "ping":
                await ws.send_json({"event": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(code, ws)
        manager.mark_offline(code, client_id if 'client_id' in locals() else "unknown")
        await manager.broadcast(code, {
            "event": "client_disconnected", "client_id": client_id,
        })
    finally:
        db.close()
