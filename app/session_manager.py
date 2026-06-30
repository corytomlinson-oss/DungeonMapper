from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from fastapi import WebSocket


@dataclass
class ActiveSession:
    code: str
    dm_token: str
    dungeon: dict
    tokens: list = field(default_factory=list)
    open_doors: dict = field(default_factory=dict)      # "x,y" → True/False
    connections: list = field(default_factory=list)     # (WebSocket, role, client_id)
    active_clients: list = field(default_factory=list)  # {id, name, role, online}
    fog_enabled: bool = True
    sight_radius: int = 6


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, ActiveSession] = {}

    def create(self, code: str, dm_token: str, dungeon: dict) -> ActiveSession:
        session = ActiveSession(code=code, dm_token=dm_token, dungeon=dungeon)
        self._sessions[code.upper()] = session
        return session

    def get(self, code: str) -> Optional[ActiveSession]:
        return self._sessions.get(code.upper())

    def remove(self, code: str):
        self._sessions.pop(code.upper(), None)

    async def connect(self, code: str, ws: WebSocket, role: str, client_id: str,
                      display_name: str) -> bool:
        session = self._sessions.get(code.upper())
        if not session:
            return False
        await ws.accept()
        session.connections.append((ws, role, client_id))
        # Update or add to active_clients list
        existing = next((c for c in session.active_clients if c["id"] == client_id), None)
        if existing:
            existing["online"] = True
        else:
            session.active_clients.append({
                "id": client_id, "name": display_name, "role": role, "online": True
            })
        return True

    def disconnect(self, code: str, ws: WebSocket):
        session = self._sessions.get(code.upper())
        if not session:
            return
        session.connections = [
            (w, r, c) for w, r, c in session.connections if w is not ws
        ]
        # Mark client offline
        client_id = None
        for w, r, c in session.connections:
            pass  # we already removed it; find from active_clients via ws identity
        # We need to find which client_id belonged to this ws — track separately
        # (handled by caller who knows the client_id)

    def mark_offline(self, code: str, client_id: str):
        session = self._sessions.get(code.upper())
        if not session:
            return
        for c in session.active_clients:
            if c["id"] == client_id:
                c["online"] = False
                break

    async def broadcast(self, code: str, message: dict,
                        exclude: Optional[WebSocket] = None):
        session = self._sessions.get(code.upper())
        if not session:
            return
        dead: list[WebSocket] = []
        for ws, _, _ in session.connections:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            session.connections = [
                (w, r, c) for w, r, c in session.connections if w is not ws
            ]

    def snapshot(self, code: str) -> dict:
        session = self._sessions.get(code.upper())
        if not session:
            return {}
        return {
            "event": "state_sync",
            "tokens": session.tokens,
            "open_doors": session.open_doors,
            "active_clients": session.active_clients,
            "fog_enabled": session.fog_enabled,
            "sight_radius": session.sight_radius,
        }

    def find_entrance(self, dungeon: dict) -> tuple[int, int]:
        grid = dungeon["levels"][0]["grid"]
        H, W = dungeon["height"], dungeon["width"]
        for y in range(H):
            for x in range(W):
                if grid[y][x] == 7:  # ENTRANCE
                    return (x, y)
        for y in range(H):
            for x in range(W):
                if grid[y][x] == 1:  # FLOOR fallback
                    return (x, y)
        return (1, 1)


manager = SessionManager()
