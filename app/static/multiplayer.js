// Tile constants (must match dungeon_gen.py)
const MP_T = { WALL:0, FLOOR:1, DOOR:2, STAIR_UP:3, STAIR_DN:4, SPAWN:5, TREASURE:6, ENTRANCE:7 };
const MP_TILE_BG = [
  '#1a1a2e','#c8b89a','#6b4c1e','#d4a017',
  '#c07010','#b03030','#c8a020','#2a7a3a',
];
const MP_SYMBOLS    = { 3:'▲', 4:'▼', 5:'⚔', 6:'★', 7:'⊙' };
const MP_TILE_NAMES = ['Wall','Floor','Door','Stairs Up','Stairs Down','Spawn Point','Treasure','Entrance'];
const MP_GRID_LINE  = 'rgba(90,70,40,0.25)';

// Recursive shadowcasting — 8 octant transform matrices [xx, xy, yx, yy]
const FOV_OCTANTS = [
  [ 1,  0,  0,  1],
  [ 0,  1,  1,  0],
  [ 0, -1,  1,  0],
  [-1,  0,  0,  1],
  [-1,  0,  0, -1],
  [ 0, -1, -1,  0],
  [ 0,  1, -1,  0],
  [ 1,  0,  0, -1],
];

function dungeonSession() {
  return {
    // ── Data ───────────────────────────────────────────────────────────────
    dungeon: null,
    role: 'player',
    myId: null,
    code: null,
    dmToken: null,
    pid: null,

    currentLevel: 0,
    tokens: [],
    openDoors: {},
    activeClients: [],
    hoveredSquare: null,
    hoveredToken: null,
    connected: false,

    // Zoom
    zoom: 1.0,
    _pinchDist: null,
    _pinchZoom: null,

    // Fog of War
    fogEnabled: true,
    sightRadius: 6,
    visibleTiles: new Set(),     // "x,y" — currently in FOV (this level)
    exploredByLevel: {},         // level → Set<"x,y"> — ever seen

    // Interaction state
    selectedTokenId: null,
    dragging: null,

    // DM monster placement
    placing: false,
    monsterName: '',
    monsterColor: '#dc2626',
    joinLinkCopied: false,

    // Map pan state
    panning: false,
    _panOrigin: null,  // { clientX, clientY, scrollLeft, scrollTop, tileX, tileY }

    ws: null,
    _wsUrl: null,

    // ── Init ───────────────────────────────────────────────────────────────
    init() {
      const el = this.$el;
      this.dungeon = JSON.parse(el.dataset.dungeon);
      this.role    = el.dataset.role || 'player';
      this.code    = el.dataset.code;

      // Init per-level explored sets
      for (let i = 0; i < this.dungeon.num_levels; i++) {
        this.exploredByLevel[i] = new Set();
      }

      if (this.role === 'dm') {
        this.dmToken = el.dataset.token;
        this.myId    = 'dm';
      } else {
        this.pid  = parseInt(el.dataset.pid, 10);
        this.myId = `player_${this.pid}`;
      }

      const proto  = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const params = this.role === 'dm'
        ? `role=dm&token=${this.dmToken}`
        : `role=player&pid=${this.pid}`;
      this._wsUrl = `${proto}//${location.host}/ws/${this.code}?${params}`;

      this.connectWS();

      this.$nextTick(() => {
        const ro = new ResizeObserver(() => this.render());
        ro.observe(this.$refs.wrap);
        setTimeout(() => this.render(), 100);
      });
    },

    // ── WebSocket ──────────────────────────────────────────────────────────
    connectWS() {
      this.ws = new WebSocket(this._wsUrl);
      this.ws.onopen  = () => { this.connected = true; };
      this.ws.onclose = () => {
        this.connected = false;
        setTimeout(() => this.connectWS(), 3000);
      };
      this.ws.onmessage = (e) => {
        try { this.handleMessage(JSON.parse(e.data)); } catch(_) {}
      };
    },

    send(msg) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(msg));
      }
    },

    handleMessage(msg) {
      switch (msg.event) {
        case 'state_sync':
          this.tokens        = msg.tokens         || [];
          this.openDoors     = msg.open_doors     || {};
          this.activeClients = msg.active_clients || [];
          this.fogEnabled    = msg.fog_enabled    ?? true;
          this.sightRadius   = msg.sight_radius   ?? 6;
          this.updateFOV();
          break;

        case 'token_moved':
          this.tokens = this.tokens.map(t =>
            t.id === msg.token_id
              ? { ...t, x: msg.x, y: msg.y, level: msg.level }
              : t
          );
          // Recompute FOV if another player moved (they might have revealed something)
          // Our own moves already trigger FOV in _moveToken (optimistic)
          if (msg.token_id !== this.myId) this.render();
          break;

        case 'token_added':
          this.tokens = [...this.tokens, msg.token];
          this.render();
          break;

        case 'token_removed':
          if (this.selectedTokenId === msg.token_id) this.selectedTokenId = null;
          this.tokens = this.tokens.filter(t => t.id !== msg.token_id);
          this.render();
          break;

        case 'door_toggled': {
          const key = `${msg.x},${msg.y}`;
          this.openDoors = { ...this.openDoors, [key]: msg.open };
          this.updateFOV();  // doors open/close change LOS
          break;
        }

        case 'fog_settings_changed':
          this.fogEnabled  = msg.fog_enabled;
          this.sightRadius = msg.sight_radius;
          this.updateFOV();
          break;

        case 'fog_reveal_all':
          // Mark every tile on all levels as explored
          for (let lvl = 0; lvl < this.dungeon.num_levels; lvl++) {
            const grid = this.dungeon.levels[lvl].grid;
            const H = this.dungeon.height;
            const W = this.dungeon.width;
            for (let y = 0; y < H; y++) {
              for (let x = 0; x < W; x++) {
                if (grid[y][x] !== MP_T.WALL) {
                  this.exploredByLevel[lvl].add(`${x},${y}`);
                }
              }
            }
          }
          this.render();
          break;

        case 'client_connected':
          this.activeClients = this.activeClients.find(c => c.id === msg.client_id)
            ? this.activeClients.map(c =>
                c.id === msg.client_id ? { ...c, online: true } : c)
            : [...this.activeClients, {
                id: msg.client_id, name: msg.name, role: msg.role, online: true
              }];
          break;

        case 'client_disconnected':
          this.activeClients = this.activeClients.map(c =>
            c.id === msg.client_id ? { ...c, online: false } : c
          );
          break;
      }
    },

    // ── Fog of War / FOV ───────────────────────────────────────────────────

    // Recompute visible tiles from the player's current token position.
    // DM always sees everything — no-op for DM role.
    updateFOV() {
      if (this.role === 'dm') {
        this.render();
        return;
      }
      const myTok = this.tokens.find(t => t.id === this.myId);
      if (!myTok) {
        this.render();
        return;
      }

      // Switch explored set to current level if needed
      if (!this.exploredByLevel[myTok.level]) {
        this.exploredByLevel[myTok.level] = new Set();
      }

      if (this.fogEnabled) {
        const vis = this.computeFOV(myTok.x, myTok.y, myTok.level, this.sightRadius);
        this.visibleTiles = vis;
        // Accumulate explored tiles
        for (const key of vis) {
          this.exploredByLevel[myTok.level].add(key);
        }
      } else {
        // Fog disabled: reveal everything as explored
        this.visibleTiles = new Set();
        const grid = this.dungeon.levels[myTok.level].grid;
        const H = this.dungeon.height;
        const W = this.dungeon.width;
        for (let y = 0; y < H; y++) {
          for (let x = 0; x < W; x++) {
            if (grid[y][x] !== MP_T.WALL) {
              const k = `${x},${y}`;
              this.visibleTiles.add(k);
              this.exploredByLevel[myTok.level].add(k);
            }
          }
        }
      }
      this.render();
    },

    // Recursive shadowcasting FOV. Returns a Set of "x,y" visible tile keys.
    computeFOV(ox, oy, level, radius) {
      const W    = this.dungeon.width;
      const H    = this.dungeon.height;
      const vis  = new Set();
      vis.add(`${ox},${oy}`);
      for (const [xx, xy, yx, yy] of FOV_OCTANTS) {
        this._castShadow(vis, ox, oy, level, W, H, radius, 1, 1.0, 0.0, xx, xy, yx, yy);
      }
      return vis;
    },

    _castShadow(vis, cx, cy, level, W, H, radius, row, startSlope, endSlope, xx, xy, yx, yy) {
      if (startSlope < endSlope) return;
      let nextStart = startSlope;
      let blocked   = false;

      for (let dist = row; dist <= radius && !blocked; dist++) {
        const dy = -dist;

        for (let dx = -dist; dx <= 0; dx++) {
          const lSlope = (dx - 0.5) / (dy + 0.5);
          const rSlope = (dx + 0.5) / (dy - 0.5);

          if (startSlope < rSlope) continue;
          if (endSlope   > lSlope) break;

          const ax = cx + dx * xx + dy * yx;
          const ay = cy + dx * xy + dy * yy;

          if (dx * dx + dy * dy <= radius * radius &&
              ax >= 0 && ax < W && ay >= 0 && ay < H) {
            vis.add(`${ax},${ay}`);
          }

          const wall = this._blocksLight(ax, ay, level, W, H);

          if (blocked) {
            if (wall) {
              nextStart = rSlope;
            } else {
              blocked    = false;
              startSlope = nextStart;
            }
          } else if (wall && dist < radius) {
            blocked = true;
            this._castShadow(
              vis, cx, cy, level, W, H, radius,
              dist + 1, startSlope, lSlope,
              xx, xy, yx, yy
            );
            nextStart = rSlope;
          }
        }
      }
    },

    _blocksLight(x, y, level, W, H) {
      if (x < 0 || x >= W || y < 0 || y >= H) return true;
      const t = this.dungeon.levels[level].grid[y][x];
      if (t === MP_T.WALL) return true;
      if (t === MP_T.DOOR && !this.openDoors[`${x},${y}`]) return true;
      return false;
    },

    // Is a tile visible or explored on the current level?
    _tileVisible(x, y) {
      return this.visibleTiles.has(`${x},${y}`);
    },
    _tileExplored(x, y) {
      return (this.exploredByLevel[this.currentLevel] || new Set()).has(`${x},${y}`);
    },

    // ── DM Fog Controls (send to server) ───────────────────────────────────
    toggleFog() {
      const next = !this.fogEnabled;
      this.send({ action: 'toggle_fog', enabled: next });
    },
    setSightRadius(r) {
      r = Math.max(1, Math.min(15, r));
      this.send({ action: 'set_sight_radius', radius: r });
    },
    revealAll() {
      this.send({ action: 'reveal_all' });
    },

    // ── Zoom ───────────────────────────────────────────────────────────────
    zoomIn()    { this.zoom = Math.min(5, +(this.zoom * 1.3).toFixed(2)); this.render(); },
    zoomOut()   { this.zoom = Math.max(0.3, +(this.zoom / 1.3).toFixed(2)); this.render(); },
    zoomReset() { this.zoom = 1.0; this.render(); },
    get zoomPct() { return Math.round(this.zoom * 100) + '%'; },

    onWheel(e) {
      e.preventDefault();
      e.deltaY < 0 ? this.zoomIn() : this.zoomOut();
    },

    onTouchStart(e) {
      if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        this._pinchDist = Math.hypot(dx, dy);
        this._pinchZoom = this.zoom;
      }
    },
    onTouchMove(e) {
      if (e.touches.length === 2 && this._pinchDist !== null) {
        e.preventDefault();
        const dx   = e.touches[0].clientX - e.touches[1].clientX;
        const dy   = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.hypot(dx, dy);
        this.zoom  = Math.max(0.3, Math.min(5, +(this._pinchZoom * dist / this._pinchDist).toFixed(2)));
        this.render();
      }
    },
    onTouchEnd(e) {
      if (e.touches.length < 2) {
        this._pinchDist = null;
        this._pinchZoom = null;
      }
    },

    // ── Pointer Interaction ────────────────────────────────────────────────
    canControl(tok) {
      return this.role === 'dm' || tok.id === this.myId;
    },

    _tokenAt(x, y) {
      return this.tokens.find(
        t => t.x === x && t.y === y && t.level === this.currentLevel
      ) || null;
    },

    _moveToken(tokenId, x, y) {
      if (!this.dungeon) return;
      const grid = this.dungeon.levels[this.currentLevel].grid;
      if (x < 0 || x >= this.dungeon.width || y < 0 || y >= this.dungeon.height) return;
      if (grid[y][x] === MP_T.WALL) return;
      const lvl = this.currentLevel;
      this.tokens = this.tokens.map(t =>
        t.id === tokenId ? { ...t, x, y, level: lvl } : t
      );
      this.send({ action: 'move_token', token_id: tokenId, x, y, level: lvl });
      // Recompute FOV immediately for own token move (optimistic)
      if (tokenId === this.myId) this.updateFOV();
      else this.render();
    },

    pointerTile(e) {
      const canvas = this.$refs.canvas;
      const rect   = canvas.getBoundingClientRect();
      const ts     = this.tileSize();
      const sx     = canvas.width  / rect.width;
      const sy     = canvas.height / rect.height;
      return [
        Math.floor(((e.clientX - rect.left) * sx) / ts),
        Math.floor(((e.clientY - rect.top)  * sy) / ts),
      ];
    },

    onPointerDown(e) {
      if (!this.dungeon) return;
      if (this._pinchDist !== null) return;
      e.preventDefault();

      const [x, y] = this.pointerTile(e);
      const tok     = this._tokenAt(x, y);

      // 1. Click on a controllable token → select + start drag
      if (tok && this.canControl(tok)) {
        this.$refs.canvas.setPointerCapture(e.pointerId);
        this.selectedTokenId = tok.id;
        this.dragging = { token: tok, ghostX: x, ghostY: y, startX: x, startY: y };
        this.render();
        return;
      }

      // 2. Token selected + click floor → move it
      if (this.selectedTokenId) {
        const selTok = this.tokens.find(
          t => t.id === this.selectedTokenId && this.canControl(t)
        );
        if (selTok) {
          this._moveToken(this.selectedTokenId, x, y);
          this.selectedTokenId = null;
          this.dragging = null;
          return;
        }
        this.selectedTokenId = null;
      }

      // 3. DM placement mode
      if (this.role === 'dm' && this.placing) {
        const grid = this.dungeon.levels[this.currentLevel].grid;
        if (grid[y]?.[x] !== undefined && grid[y][x] !== MP_T.WALL) {
          this.send({
            action: 'place_token',
            name: this.monsterName.trim() || 'M',
            color: this.monsterColor,
            x, y, level: this.currentLevel,
          });
          this.placing = false;
          this.render();
        }
        return;
      }

      // 4. Everything else → start pan; door toggle handled on pointerup if no movement
      const wrap = this.$refs.wrap;
      this.$refs.canvas.setPointerCapture(e.pointerId);
      this._panOrigin = {
        clientX: e.clientX, clientY: e.clientY,
        scrollLeft: wrap.scrollLeft, scrollTop: wrap.scrollTop,
        tileX: x, tileY: y,
      };
      this.panning = false;
    },

    onPointerMove(e) {
      // Pan in progress
      if (this._panOrigin) {
        const dx = e.clientX - this._panOrigin.clientX;
        const dy = e.clientY - this._panOrigin.clientY;
        // Activate pan once pointer moves more than 5 px (avoids misfire on clicks)
        if (!this.panning && (Math.abs(dx) > 5 || Math.abs(dy) > 5)) {
          this.panning = true;
        }
        if (this.panning) {
          const wrap = this.$refs.wrap;
          wrap.scrollLeft = this._panOrigin.scrollLeft - dx;
          wrap.scrollTop  = this._panOrigin.scrollTop  - dy;
          return;
        }
      }

      const [x, y] = this.pointerTile(e);

      if (!this.dragging) {
        const d = this.dungeon;
        if (d && x >= 0 && x < d.width && y >= 0 && y < d.height) {
          this.hoveredSquare = { x, y, tile: d.levels[this.currentLevel].grid[y][x] };
        } else {
          this.hoveredSquare = null;
        }
        this.hoveredToken = this._tokenAt(x, y);
        return;
      }

      if (x !== this.dragging.ghostX || y !== this.dragging.ghostY) {
        this.dragging = { ...this.dragging, ghostX: x, ghostY: y };
        this.render();
      }
    },

    onPointerUp(e) {
      // Token drag completion
      if (this.dragging) {
        const [x, y]   = this.pointerTile(e);
        const movedTile = x !== this.dragging.startX || y !== this.dragging.startY;
        if (movedTile) {
          this._moveToken(this.dragging.token.id, x, y);
          this.selectedTokenId = null;
        }
        this.dragging = null;
        this.render();
        return;
      }

      // Pan / click completion
      if (this._panOrigin) {
        if (!this.panning) {
          // Pointer didn't move — treat as a click; toggle door if applicable
          const { tileX: x, tileY: y } = this._panOrigin;
          const grid = this.dungeon.levels[this.currentLevel].grid;
          if (grid[y]?.[x] === MP_T.DOOR) {
            this.send({ action: 'toggle_door', x, y });
          }
        }
        this.panning    = false;
        this._panOrigin = null;
      }
    },

    onPointerLeave() {
      this.hoveredSquare = null;
      this.hoveredToken  = null;
      if (this.dragging) {
        this.dragging = null;
        this.render();
      }
      // Don't cancel pan on leave — setPointerCapture keeps events flowing
    },

    // ── DM helpers ─────────────────────────────────────────────────────────
    removeToken(tokenId) {
      if (this.selectedTokenId === tokenId) this.selectedTokenId = null;
      this.send({ action: 'remove_token', token_id: tokenId });
    },
    startPlacing()  { this.placing = true; },
    cancelPlacing() { this.placing = false; },
    _copyText(text) {
      // navigator.clipboard requires HTTPS; fall back to execCommand for HTTP (webpi.local)
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).catch(() => this._execCommandCopy(text));
      } else {
        this._execCommandCopy(text);
      }
    },
    _execCommandCopy(text) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try { document.execCommand('copy'); } catch (_) {}
      document.body.removeChild(ta);
    },
    copyJoinLink() {
      const url = `${location.protocol}//${location.host}/join?code=${this.code}`;
      this._copyText(url);
      // Visual feedback: briefly change button label via a flag
      this.joinLinkCopied = true;
      setTimeout(() => { this.joinLinkCopied = false; }, 2000);
    },

    // ── Rendering ──────────────────────────────────────────────────────────
    tileSize() {
      const wrap = this.$refs.wrap;
      if (!wrap || !this.dungeon) return 12;
      const base    = Math.floor((wrap.clientWidth - 2) / this.dungeon.width);
      const clamped = Math.max(4, Math.min(20, base));
      return Math.max(3, Math.round(clamped * this.zoom));
    },

    render() {
      const canvas = this.$refs.canvas;
      if (!canvas || !this.dungeon) return;
      const ts  = this.tileSize();
      const W   = this.dungeon.width;
      const H   = this.dungeon.height;
      canvas.width  = W * ts;
      canvas.height = H * ts;

      const ctx   = canvas.getContext('2d');
      const grid  = this.dungeon.levels[this.currentLevel].grid;
      const hasFog = this.role === 'player' && this.fogEnabled;

      // ── Tiles ──────────────────────────────────────────────────────────
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          // For player view, skip tiles that have never been seen
          const neverSeen = hasFog && !this._tileVisible(x, y) && !this._tileExplored(x, y);
          if (neverSeen) {
            ctx.fillStyle = '#0a0a12';
            ctx.fillRect(x * ts, y * ts, ts, ts);
            continue;
          }

          let t = grid[y][x];
          if (t === MP_T.DOOR && this.openDoors[`${x},${y}`]) t = MP_T.FLOOR;

          ctx.fillStyle = MP_TILE_BG[t] ?? '#000';
          ctx.fillRect(x * ts, y * ts, ts, ts);

          if (t !== MP_T.WALL && ts >= 6) {
            ctx.strokeStyle = MP_GRID_LINE;
            ctx.lineWidth = 0.5;
            ctx.strokeRect(x * ts + 0.25, y * ts + 0.25, ts - 0.5, ts - 0.5);
          }

          if (MP_SYMBOLS[t] && ts >= 8) {
            const sz = Math.max(7, Math.floor(ts * 0.62));
            ctx.fillStyle = 'rgba(255,255,255,0.92)';
            ctx.font = `bold ${sz}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(MP_SYMBOLS[t], x * ts + ts / 2, y * ts + ts / 2 + 0.5);
          }

          if (grid[y][x] === MP_T.DOOR && !this.openDoors[`${x},${y}`] && ts >= 8) {
            const bw = Math.max(2, Math.floor(ts * 0.18));
            const bh = Math.floor(ts * 0.55);
            ctx.fillStyle = '#c89a50';
            const wallN = y > 0   && grid[y - 1][x] === MP_T.WALL;
            const wallS = y < H-1 && grid[y + 1][x] === MP_T.WALL;
            if (wallN || wallS) {
              ctx.fillRect(x * ts + (ts - bw) / 2, y * ts + (ts - bh) / 2, bw, bh);
            } else {
              ctx.fillRect(x * ts + (ts - bh) / 2, y * ts + (ts - bw) / 2, bh, bw);
            }
          }

          // Explored-but-not-visible dim overlay
          if (hasFog && !this._tileVisible(x, y) && this._tileExplored(x, y)) {
            ctx.fillStyle = 'rgba(0,0,0,0.58)';
            ctx.fillRect(x * ts, y * ts, ts, ts);
          }
        }
      }

      // ── Tokens ─────────────────────────────────────────────────────────
      for (const tok of this.tokens) {
        if (tok.level !== this.currentLevel) continue;
        if (this.dragging && tok.id === this.dragging.token.id) continue;

        // In player view with fog: monster tokens only visible if currently in FOV.
        // Player tokens are always visible (party awareness).
        if (hasFog && tok.type !== 'player' && !this._tileVisible(tok.x, tok.y)) continue;

        this.drawToken(ctx, tok, ts, 1);
      }

      // Ghost while dragging
      if (this.dragging) {
        this.drawToken(ctx, {
          ...this.dragging.token,
          x: this.dragging.ghostX,
          y: this.dragging.ghostY,
        }, ts, 0.5);
      }

      // Selection ring
      if (this.selectedTokenId && !this.dragging) {
        const selTok = this.tokens.find(t => t.id === this.selectedTokenId);
        if (selTok && selTok.level === this.currentLevel) {
          ctx.strokeStyle = 'rgba(255,255,100,0.8)';
          ctx.lineWidth = 2;
          ctx.strokeRect(selTok.x * ts + 1, selTok.y * ts + 1, ts - 2, ts - 2);
        }
      }

      // FOV radius indicator (faint circle, only in player view with fog)
      if (hasFog) {
        const myTok = this.tokens.find(t => t.id === this.myId);
        if (myTok && myTok.level === this.currentLevel) {
          ctx.beginPath();
          ctx.arc(
            myTok.x * ts + ts / 2,
            myTok.y * ts + ts / 2,
            this.sightRadius * ts,
            0, Math.PI * 2
          );
          ctx.strokeStyle = 'rgba(255,255,200,0.07)';
          ctx.lineWidth = ts * 0.5;
          ctx.stroke();
        }
      }

      this.drawScaleBar(ctx, ts, W, H);
    },

    drawToken(ctx, tok, ts, alpha) {
      if (ts < 4) return;
      const cx = tok.x * ts + ts / 2;
      const cy = tok.y * ts + ts / 2;
      const r  = Math.max(3, Math.floor(ts * 0.38));

      ctx.globalAlpha = alpha;
      ctx.shadowColor = 'rgba(0,0,0,0.6)';
      ctx.shadowBlur  = 4;

      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fillStyle = tok.color;
      ctx.fill();

      ctx.shadowBlur = 0;

      const isMe       = tok.id === this.myId;
      const isSelected = tok.id === this.selectedTokenId;
      const isHovered  = this.hoveredToken?.id === tok.id;

      ctx.strokeStyle = (isMe || isSelected || isHovered) ? '#ffffff' : 'rgba(255,255,255,0.5)';
      ctx.lineWidth   = (isMe || isSelected) ? 2.5 : isHovered ? 2 : 1.5;
      ctx.stroke();

      if ((isSelected || isHovered) && ts >= 6) {
        ctx.beginPath();
        ctx.arc(cx, cy, r + 3, 0, Math.PI * 2);
        ctx.strokeStyle = isSelected ? 'rgba(255,255,100,0.85)' : 'rgba(255,255,255,0.45)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      if (ts >= 10) {
        ctx.fillStyle = '#fff';
        ctx.font = `bold ${Math.floor(r * 1.15)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(tok.name[0].toUpperCase(), cx, cy + 0.5);
      }

      ctx.globalAlpha = 1;
    },

    drawScaleBar(ctx, ts, W, H) {
      const sqCount = 5;
      const barW = sqCount * ts;
      const barH = Math.max(6, Math.floor(ts * 0.5));
      const margin = 8;
      const bx = W * ts - barW - margin;
      const by = H * ts - barH - margin - 14;

      ctx.fillStyle = 'rgba(10,10,20,0.65)';
      ctx.beginPath();
      ctx.roundRect(bx - 4, by - 4, barW + 8, barH + 22, 4);
      ctx.fill();

      for (let i = 0; i < sqCount; i++) {
        ctx.fillStyle = i % 2 === 0 ? '#fff' : '#666';
        ctx.fillRect(bx + i * ts, by, ts, barH);
      }
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1;
      ctx.strokeRect(bx, by, barW, barH);
      for (let i = 0; i <= sqCount; i++) {
        ctx.fillStyle = '#fff';
        ctx.fillRect(bx + i * ts - 0.5, by + barH, 1, 3);
      }
      ctx.fillStyle = '#fff';
      ctx.font = `bold ${Math.max(8, Math.floor(ts * 0.55))}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText('0', bx, by + barH + 4);
      ctx.fillText(`${sqCount * 5} ft`, bx + barW, by + barH + 4);
      ctx.font = `${Math.max(7, Math.floor(ts * 0.45))}px sans-serif`;
      ctx.fillStyle = 'rgba(255,255,255,0.7)';
      ctx.fillText('□ = 5 ft', bx + barW / 2, by + barH + 4);
    },

    // ── Computed ───────────────────────────────────────────────────────────
    get tileName() {
      if (!this.hoveredSquare) return '';
      return MP_TILE_NAMES[this.hoveredSquare.tile] ?? '';
    },
    get levelTokens() {
      return this.tokens.filter(t => t.level === this.currentLevel);
    },
    get onlinePlayers() {
      return this.activeClients.filter(c => c.role === 'player');
    },
  };
}
