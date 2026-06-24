"""
Dungeon generation for DungeonMapper.

Area types:
  dungeon  - BSP tree: rectangular rooms + straight corridors
  cave     - Cellular automata: organic, open caverns
  crypt    - BSP tree: wider rooms, longer sparse halls
  sewer    - BSP tree + erosion: jagged tunnel chambers
  ruins    - BSP tree + heavy erosion: crumbling irregular rooms
"""

import random
from dataclasses import dataclass, field
from typing import Optional

# ── Tile constants ──────────────────────────────────────────────────────────

WALL     = 0
FLOOR    = 1
DOOR     = 2
STAIR_UP = 3
STAIR_DN = 4
SPAWN    = 5
TREASURE = 6
ENTRANCE = 7

TILE_NAMES = {
    WALL: "Wall", FLOOR: "Floor", DOOR: "Door",
    STAIR_UP: "Stairs Up", STAIR_DN: "Stairs Down",
    SPAWN: "Spawn Point", TREASURE: "Treasure", ENTRANCE: "Entrance",
}

SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "small":  (40, 30),
    "medium": (70, 50),
    "large":  (100, 70),
    "epic":   (150, 100),
}

# ── Room dataclass ───────────────────────────────────────────────────────────

@dataclass
class Room:
    id: int
    x: int
    y: int
    w: int
    h: int
    room_type: str = "standard"

    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def area(self) -> int:
        return self.w * self.h

    def to_dict(self) -> dict:
        cx, cy = self.center()
        return {
            "id": self.id, "x": self.x, "y": self.y,
            "w": self.w, "h": self.h, "type": self.room_type,
            "cx": cx, "cy": cy,
        }


# ── BSP tree ─────────────────────────────────────────────────────────────────

class BSPNode:
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.left: Optional["BSPNode"] = None
        self.right: Optional["BSPNode"] = None
        self.room: Optional[Room] = None

    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


def _bsp_split(node: BSPNode, min_size: int, rng: random.Random, depth: int = 0) -> None:
    if depth > 12:
        return
    can_h = node.h >= min_size * 2
    can_v = node.w >= min_size * 2
    if not can_h and not can_v:
        return

    if can_h and can_v:
        horizontal = node.h > node.w * 1.3 or (node.w <= node.h * 1.3 and rng.random() < 0.5)
    else:
        horizontal = can_h

    if horizontal:
        split = rng.randint(min_size, node.h - min_size)
        node.left  = BSPNode(node.x, node.y,          node.w, split)
        node.right = BSPNode(node.x, node.y + split,   node.w, node.h - split)
    else:
        split = rng.randint(min_size, node.w - min_size)
        node.left  = BSPNode(node.x,         node.y, split,          node.h)
        node.right = BSPNode(node.x + split, node.y, node.w - split, node.h)

    _bsp_split(node.left,  min_size, rng, depth + 1)
    _bsp_split(node.right, min_size, rng, depth + 1)


def _bsp_place_rooms(node: BSPNode, rooms: list[Room], rng: random.Random,
                     pad: int, min_room: int) -> None:
    if node.is_leaf():
        max_w = max(min_room, node.w - pad * 2)
        max_h = max(min_room, node.h - pad * 2)
        rw = rng.randint(min_room, max_w)
        rh = rng.randint(min_room, max_h)
        rx = node.x + pad + rng.randint(0, max(0, node.w - rw - pad * 2))
        ry = node.y + pad + rng.randint(0, max(0, node.h - rh - pad * 2))
        room = Room(id=len(rooms), x=rx, y=ry, w=rw, h=rh)
        node.room = room
        rooms.append(room)
    else:
        if node.left:
            _bsp_place_rooms(node.left,  rooms, rng, pad, min_room)
        if node.right:
            _bsp_place_rooms(node.right, rooms, rng, pad, min_room)


def _leaf_room(node: BSPNode) -> Optional[Room]:
    if node.is_leaf():
        return node.room
    lr = _leaf_room(node.left)  if node.left  else None
    rr = _leaf_room(node.right) if node.right else None
    return lr or rr


def _carve_corridor(grid: list, x1: int, y1: int, x2: int, y2: int,
                    rng: random.Random, width: int = 1) -> None:
    h, w = len(grid), len(grid[0])

    def set_tile(x: int, y: int) -> None:
        for dy in range(width):
            for dx in range(width):
                ny, nx = y + dy, x + dx
                if 0 < ny < h - 1 and 0 < nx < w - 1:
                    grid[ny][nx] = FLOOR

    if rng.random() < 0.5:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            set_tile(x, y1)
        for y in range(min(y1, y2), max(y1, y2) + 1):
            set_tile(x2, y)
    else:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            set_tile(x1, y)
        for x in range(min(x1, x2), max(x1, x2) + 1):
            set_tile(x, y2)


def _connect_nodes(node: BSPNode, grid: list, rng: random.Random,
                   corridor_width: int = 1) -> None:
    if node.is_leaf():
        return
    if node.left:
        _connect_nodes(node.left,  grid, rng, corridor_width)
    if node.right:
        _connect_nodes(node.right, grid, rng, corridor_width)
    lr = _leaf_room(node.left)  if node.left  else None
    rr = _leaf_room(node.right) if node.right else None
    if lr and rr:
        lx, ly = lr.center()
        rx, ry = rr.center()
        _carve_corridor(grid, lx, ly, rx, ry, rng, corridor_width)


def _carve_rooms(grid: list, rooms: list[Room]) -> None:
    h, w = len(grid), len(grid[0])
    for r in rooms:
        for y in range(r.y, r.y + r.h):
            for x in range(r.x, r.x + r.w):
                if 0 <= y < h and 0 <= x < w:
                    grid[y][x] = FLOOR


def _add_doors(grid: list, rooms: list[Room], rng: random.Random) -> None:
    h, w = len(grid), len(grid[0])
    room_set: set[tuple[int, int]] = set()
    for r in rooms:
        for ry in range(r.y, r.y + r.h):
            for rx in range(r.x, r.x + r.w):
                room_set.add((rx, ry))

    for room in rooms:
        candidates: list[tuple[int, int]] = []
        for x in range(room.x, room.x + room.w):
            for dy in (-1, room.h):
                oy = room.y + dy
                if 0 < oy < h - 1 and grid[oy][x] == FLOOR and (x, oy) not in room_set:
                    candidates.append((x, oy))
        for y in range(room.y, room.y + room.h):
            for dx in (-1, room.w):
                ox = room.x + dx
                if 0 < ox < w - 1 and grid[y][ox] == FLOOR and (ox, y) not in room_set:
                    candidates.append((ox, y))
        if candidates and rng.random() < 0.55:
            dx, dy = rng.choice(candidates)
            grid[dy][dx] = DOOR


def _erode_walls(grid: list, rng: random.Random, passes: int = 2,
                 threshold: int = 4, chance: float = 0.6) -> None:
    h, w = len(grid), len(grid[0])
    for _ in range(passes):
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if grid[y][x] == WALL:
                    floors = sum(
                        1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                        if grid[y + dy][x + dx] == FLOOR
                    )
                    if floors >= threshold and rng.random() < chance:
                        grid[y][x] = FLOOR


# ── Cave (cellular automata) ─────────────────────────────────────────────────

def _gen_cave(width: int, height: int, rng: random.Random) -> list:
    grid = [
        [WALL if (x == 0 or x == width - 1 or y == 0 or y == height - 1
                  or rng.random() < 0.44)
         else FLOOR
         for x in range(width)]
        for y in range(height)
    ]
    for _ in range(5):
        new = [[WALL] * width for _ in range(height)]
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                walls = sum(
                    1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                    if grid[y + dy][x + dx] == WALL
                )
                new[y][x] = WALL if walls >= 5 else FLOOR
        grid = new
    return grid


def _largest_region(grid: list) -> tuple[list, list[tuple[int, int]]]:
    """Keep only the largest connected floor region; return grid and its tiles."""
    h, w = len(grid), len(grid[0])
    visited = [[False] * w for _ in range(h)]
    best: list[tuple[int, int]] = []

    for sy in range(h):
        for sx in range(w):
            if grid[sy][sx] == FLOOR and not visited[sy][sx]:
                region: list[tuple[int, int]] = []
                stack = [(sx, sy)]
                while stack:
                    cx, cy = stack.pop()
                    if visited[cy][cx]:
                        continue
                    visited[cy][cx] = True
                    region.append((cx, cy))
                    for ddx, ddy in ((1,0),(-1,0),(0,1),(0,-1)):
                        nx, ny = cx + ddx, cy + ddy
                        if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx] and grid[ny][nx] == FLOOR:
                            stack.append((nx, ny))
                if len(region) > len(best):
                    best = region

    best_set = set(best)
    for y in range(h):
        for x in range(w):
            if grid[y][x] == FLOOR and (x, y) not in best_set:
                grid[y][x] = WALL
    return grid, best


def _sample_positions(floor_tiles: list[tuple[int, int]], rng: random.Random,
                      count: int, min_dist: int = 10) -> list[tuple[int, int]]:
    """Pick `count` floor tiles with minimum Manhattan distance between them."""
    rng.shuffle(floor_tiles)
    chosen: list[tuple[int, int]] = []
    for pt in floor_tiles:
        if all(abs(pt[0]-p[0]) + abs(pt[1]-p[1]) >= min_dist for p in chosen):
            chosen.append(pt)
            if len(chosen) >= count:
                break
    return chosen


def _cave_pseudo_rooms(floor_tiles: list[tuple[int, int]],
                       rng: random.Random, count: int) -> list[Room]:
    positions = _sample_positions(floor_tiles, rng, count + 4, min_dist=8)
    rooms = []
    for i, (x, y) in enumerate(positions[:count]):
        rooms.append(Room(id=i, x=x - 1, y=y - 1, w=3, h=3))
    return rooms


# ── BSP-based level builder ───────────────────────────────────────────────────

def _bsp_level(width: int, height: int, rng: random.Random,
               area_type: str) -> tuple[list, list[Room]]:
    if area_type == "crypt":
        min_size, pad, min_room, corridor_w = 10, 2, 5, 1
    elif area_type in ("sewer", "ruins"):
        min_size, pad, min_room, corridor_w = 7, 2, 4, 2
    else:  # dungeon default
        min_size, pad, min_room, corridor_w = 8, 2, 4, 1

    grid = [[WALL] * width for _ in range(height)]
    root = BSPNode(1, 1, width - 2, height - 2)
    _bsp_split(root, min_size, rng)
    rooms: list[Room] = []
    _bsp_place_rooms(root, rooms, rng, pad, min_room)
    _carve_rooms(grid, rooms)
    _connect_nodes(root, grid, rng, corridor_width=corridor_w)

    if area_type == "sewer":
        _erode_walls(grid, rng, passes=2, threshold=3, chance=0.5)
    elif area_type == "ruins":
        _erode_walls(grid, rng, passes=3, threshold=3, chance=0.65)

    _add_doors(grid, rooms, rng)
    return grid, rooms


# ── Special tile placement ────────────────────────────────────────────────────

def _nearest_floor(grid: list, x: int, y: int, max_dist: int = 15) -> Optional[tuple[int, int]]:
    h, w = len(grid), len(grid[0])
    if 0 <= y < h and 0 <= x < w and grid[y][x] == FLOOR:
        return (x, y)
    visited: set[tuple[int, int]] = set()
    queue = [(x, y)]
    for _ in range(max_dist * max_dist):
        if not queue:
            break
        cx, cy = queue.pop(0)
        if (cx, cy) in visited:
            continue
        visited.add((cx, cy))
        if 0 <= cy < h and 0 <= cx < w and grid[cy][cx] == FLOOR:
            return (cx, cy)
        for ddx, ddy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx, ny = cx + ddx, cy + ddy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                queue.append((nx, ny))
    return None


def _place_tile(grid: list, x: int, y: int, tile: int) -> None:
    h, w = len(grid), len(grid[0])
    if 0 <= y < h and 0 <= x < w:
        grid[y][x] = tile


def _place_special_tiles(
    grid: list,
    rooms: list[Room],
    level_num: int,
    num_levels: int,
    rng: random.Random,
    stair_up_hint: Optional[tuple[int, int]] = None,
) -> tuple[list[Room], Optional[tuple[int, int]]]:
    """Assign room types and place special tiles. Returns (rooms, stair_down_pos)."""
    if not rooms:
        return rooms, None

    shuffled = rooms[:]
    rng.shuffle(shuffled)

    used_ids: set[int] = set()
    stair_down_pos: Optional[tuple[int, int]] = None

    # ── Entrance (level 1 only) ──────────────────────────────────────────────
    if level_num == 1:
        entry = shuffled[0]
        entry.room_type = "entrance"
        cx, cy = entry.center()
        pos = _nearest_floor(grid, cx, cy)
        if pos:
            _place_tile(grid, pos[0], pos[1], ENTRANCE)
        used_ids.add(entry.id)

    # ── Stairs up (levels 2+) ────────────────────────────────────────────────
    if level_num > 1:
        if stair_up_hint:
            pos = _nearest_floor(grid, stair_up_hint[0], stair_up_hint[1])
        else:
            pos = None
        if not pos:
            for r in shuffled:
                if r.id not in used_ids:
                    cx, cy = r.center()
                    pos = _nearest_floor(grid, cx, cy)
                    if pos:
                        break
        if pos:
            _place_tile(grid, pos[0], pos[1], STAIR_UP)
            # Mark the room containing this position
            for r in rooms:
                if r.x <= pos[0] < r.x + r.w and r.y <= pos[1] < r.y + r.h:
                    r.room_type = "stairs_up"
                    used_ids.add(r.id)
                    break

    # ── Stairs down (all but deepest level) ─────────────────────────────────
    if level_num < num_levels:
        for r in shuffled:
            if r.id not in used_ids:
                cx, cy = r.center()
                pos = _nearest_floor(grid, cx, cy)
                if pos:
                    _place_tile(grid, pos[0], pos[1], STAIR_DN)
                    r.room_type = "stairs_down"
                    used_ids.add(r.id)
                    stair_down_pos = pos
                    break

    # ── Boss room (deepest level: largest unused room) ───────────────────────
    if level_num == num_levels:
        boss = max(
            (r for r in rooms if r.id not in used_ids),
            key=lambda r: r.area(),
            default=None,
        )
        if boss:
            cx, cy = boss.center()
            pos = _nearest_floor(grid, cx, cy)
            if pos:
                _place_tile(grid, pos[0], pos[1], SPAWN)
            boss.room_type = "boss"
            used_ids.add(boss.id)

    # ── Treasure room (1 per level) ──────────────────────────────────────────
    for r in shuffled:
        if r.id not in used_ids:
            cx, cy = r.center()
            pos = _nearest_floor(grid, cx, cy)
            if pos:
                _place_tile(grid, pos[0], pos[1], TREASURE)
            r.room_type = "treasure"
            used_ids.add(r.id)
            break

    # ── Spawn points in remaining rooms (65% chance each) ───────────────────
    for r in rooms:
        if r.id not in used_ids and r.area() >= 8:
            if rng.random() < 0.65:
                cx, cy = r.center()
                pos = _nearest_floor(grid, cx, cy)
                if pos:
                    _place_tile(grid, pos[0], pos[1], SPAWN)
                r.room_type = "spawn"
                used_ids.add(r.id)

    return rooms, stair_down_pos


# ── Public API ────────────────────────────────────────────────────────────────

def generate_dungeon(area_type: str, size: str, num_levels: int,
                     seed: Optional[int] = None) -> dict:
    width, height = SIZE_PRESETS.get(size, SIZE_PRESETS["medium"])
    if seed is None:
        seed = random.randint(1, 999_999)

    rng = random.Random(seed)
    levels = []
    stair_hint: Optional[tuple[int, int]] = None

    for level_num in range(1, num_levels + 1):
        if area_type == "cave":
            grid = _gen_cave(width, height, rng)
            grid, floor_tiles = _largest_region(grid)
            num_rooms = max(4, len(floor_tiles) // 80)
            rooms = _cave_pseudo_rooms(floor_tiles, rng, num_rooms)
        else:
            grid, rooms = _bsp_level(width, height, rng, area_type)

        rooms, stair_hint = _place_special_tiles(
            grid, rooms, level_num, num_levels, rng, stair_up_hint=stair_hint
        )

        # Count tiles for summary
        counts = {t: 0 for t in (FLOOR, DOOR, STAIR_UP, STAIR_DN, SPAWN, TREASURE, ENTRANCE)}
        for row in grid:
            for t in row:
                if t in counts:
                    counts[t] += 1

        levels.append({
            "level": level_num,
            "grid": grid,
            "rooms": [r.to_dict() for r in rooms],
            "counts": {TILE_NAMES[k]: v for k, v in counts.items()},
        })

    return {
        "area_type": area_type,
        "size": size,
        "width": width,
        "height": height,
        "num_levels": num_levels,
        "seed": seed,
        "levels": levels,
    }
