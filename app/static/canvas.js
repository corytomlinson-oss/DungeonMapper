// Tile constants (must match dungeon_gen.py)
const T = { WALL:0, FLOOR:1, DOOR:2, STAIR_UP:3, STAIR_DN:4, SPAWN:5, TREASURE:6, ENTRANCE:7 };

const TILE_BG = [
  '#1a1a2e', // 0 wall       - dark navy
  '#c8b89a', // 1 floor      - parchment tan
  '#6b4c1e', // 2 door       - dark brown
  '#d4a017', // 3 stairs up  - gold
  '#c07010', // 4 stairs dn  - amber-orange
  '#b03030', // 5 spawn      - blood red
  '#c8a020', // 6 treasure   - bright gold
  '#2a7a3a', // 7 entrance   - forest green
];

// Symbol drawn on top of special tiles (white, centered)
const SYMBOLS = { 3:'▲', 4:'▼', 5:'⚔', 6:'★', 7:'⊙' };

// Grid line color drawn on floor tiles to show 5-ft squares
const GRID_LINE = 'rgba(90,70,40,0.25)';

function dungeonMap() {
  return {
    data: null,
    currentLevel: 0,
    hoveredSquare: null,

    init() {
      // Read dungeon JSON from the data-dungeon attribute (HTML-escaped, safe to embed)
      this.data = JSON.parse(this.$el.dataset.dungeon);
      this.$watch('currentLevel', () => this.render());
      this.$nextTick(() => {
        const ro = new ResizeObserver(() => this.render());
        ro.observe(this.$refs.wrap);
        setTimeout(() => this.render(), 50);
      });
    },

    tileSize() {
      const wrap = this.$refs.wrap;
      if (!wrap || !this.data) return 12;
      const containerW = wrap.clientWidth - 2; // subtract 1px border each side
      const ts = Math.floor(containerW / this.data.width);
      return Math.max(4, Math.min(20, ts));
    },

    render() {
      const canvas = this.$refs.canvas;
      if (!canvas || !this.data) return;
      const ts = this.tileSize();
      const W = this.data.width;
      const H = this.data.height;
      canvas.width  = W * ts;
      canvas.height = H * ts;

      const ctx = canvas.getContext('2d');
      const grid = this.data.levels[this.currentLevel].grid;

      // ── Draw tiles ───────────────────────────────────────────────────────
      for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
          const t = grid[y][x];
          ctx.fillStyle = TILE_BG[t] ?? '#000';
          ctx.fillRect(x * ts, y * ts, ts, ts);

          // 5-ft grid lines on floor + special floor-based tiles
          if (t !== T.WALL && ts >= 6) {
            ctx.strokeStyle = GRID_LINE;
            ctx.lineWidth = 0.5;
            ctx.strokeRect(x * ts + 0.25, y * ts + 0.25, ts - 0.5, ts - 0.5);
          }

          // Symbol overlay on special tiles
          if (SYMBOLS[t] && ts >= 8) {
            const sz = Math.max(7, Math.floor(ts * 0.62));
            ctx.fillStyle = 'rgba(255,255,255,0.92)';
            ctx.font = `bold ${sz}px sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(SYMBOLS[t], x * ts + ts / 2, y * ts + ts / 2 + 0.5);
          }

          // Door: draw a small perpendicular bar
          if (t === T.DOOR && ts >= 8) {
            const bw = Math.max(2, Math.floor(ts * 0.18));
            const bh = Math.floor(ts * 0.55);
            ctx.fillStyle = '#c89a50';
            // Detect door orientation by checking neighbors
            const wallN = y > 0   && grid[y-1][x] === T.WALL;
            const wallS = y < H-1 && grid[y+1][x] === T.WALL;
            if (wallN || wallS) {
              // Horizontal corridor — draw vertical bar
              ctx.fillRect(x * ts + (ts - bw) / 2, y * ts + (ts - bh) / 2, bw, bh);
            } else {
              // Vertical corridor — draw horizontal bar
              ctx.fillRect(x * ts + (ts - bh) / 2, y * ts + (ts - bw) / 2, bh, bw);
            }
          }
        }
      }

      // ── Scale indicator ──────────────────────────────────────────────────
      this.drawScaleBar(ctx, ts, W, H);
    },

    drawScaleBar(ctx, ts, W, H) {
      // Draw a 5-square scale bar (= 25 ft) in the bottom-right corner
      const sqCount = 5;
      const barW = sqCount * ts;
      const barH = Math.max(6, Math.floor(ts * 0.5));
      const margin = 8;
      const bx = W * ts - barW - margin;
      const by = H * ts - barH - margin - 14;

      // Background pill
      ctx.fillStyle = 'rgba(10,10,20,0.65)';
      ctx.beginPath();
      ctx.roundRect(bx - 4, by - 4, barW + 8, barH + 22, 4);
      ctx.fill();

      // Alternating black/white segments
      for (let i = 0; i < sqCount; i++) {
        ctx.fillStyle = i % 2 === 0 ? '#fff' : '#666';
        ctx.fillRect(bx + i * ts, by, ts, barH);
      }
      // Border around bar
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1;
      ctx.strokeRect(bx, by, barW, barH);
      // Tick marks
      for (let i = 0; i <= sqCount; i++) {
        ctx.fillStyle = '#fff';
        ctx.fillRect(bx + i * ts - 0.5, by + barH, 1, 3);
      }
      // Labels
      ctx.fillStyle = '#fff';
      ctx.font = `bold ${Math.max(8, Math.floor(ts * 0.55))}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText('0', bx, by + barH + 4);
      ctx.fillText(`${sqCount * 5} ft`, bx + barW, by + barH + 4);
      ctx.textAlign = 'center';
      ctx.font = `${Math.max(7, Math.floor(ts * 0.45))}px sans-serif`;
      ctx.fillStyle = 'rgba(255,255,255,0.7)';
      ctx.fillText('□ = 5 ft', bx + barW / 2, by + barH + 4);
    },

    // Canvas pointer → tile coordinate
    pointerTile(e) {
      const canvas = this.$refs.canvas;
      const rect = canvas.getBoundingClientRect();
      const ts = this.tileSize();
      const scaleX = canvas.width  / rect.width;
      const scaleY = canvas.height / rect.height;
      const px = (e.clientX - rect.left) * scaleX;
      const py = (e.clientY - rect.top)  * scaleY;
      return [Math.floor(px / ts), Math.floor(py / ts)];
    },

    onCanvasMove(e) {
      if (!this.data) return;
      const [x, y] = this.pointerTile(e);
      const grid = this.data.levels[this.currentLevel].grid;
      const H = this.data.height, W = this.data.width;
      if (x >= 0 && x < W && y >= 0 && y < H) {
        this.hoveredSquare = { x, y, tile: grid[y][x] };
      } else {
        this.hoveredSquare = null;
      }
    },

    onCanvasLeave() {
      this.hoveredSquare = null;
    },

    get tileName() {
      if (!this.hoveredSquare) return '';
      const names = ['Wall','Floor','Door','Stairs Up','Stairs Down','Spawn Point','Treasure','Entrance'];
      return names[this.hoveredSquare.tile] ?? '';
    },

    get levelRooms() {
      return this.data.levels[this.currentLevel].rooms;
    },

    get levelCounts() {
      return this.data.levels[this.currentLevel].counts;
    },
  };
}
