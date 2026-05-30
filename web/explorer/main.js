/**
 * 大地图探索：地图以 TILE 方格 TILE_MAP 渲染与碰撞；矢量 ROADS / FACILITIES / DECOR 仅用于构建栅格，保持原有排版。玩家与 NPC 仅可站在路格 T_ROAD。
 * 本地打开：从仓库根用静态服务器（如 python -m http.server）打开 web/explorer/；
 * file:// 下 module 可能被拦截，亦可 npx serve web/explorer。
 * 模拟经营：设施决议由 GET /api/state 的 facility_hints 返回；静默期侧栏集成基地日、远征、地图资源行动与科技摘要。
 */

/** 与 docs/map_design.md 大纲一致：北为废弃矿场叠层与沉没实验室，主轴贯通基地核心—通讯—源矿—圣树；西侧回声信标、东侧议会废墟 */
const WORLD = { w: 6400, h: 4800 };

/** 地图剖分为等距方格（世界坐标需为 TILE 整数倍）；渲染与可走判定均基于 TILE_MAP */
const TILE = 40;
const MAP_TILES_X = WORLD.w / TILE;
const MAP_TILES_Y = WORLD.h / TILE;
const T_VOID = 0;
const T_ROAD = 1;
const T_BUILD = 2;

/** 栅格化时在几何路宽之外每侧再加的半宽（世界单位），使路格连续约 2~3 格宽（斜路段略增） */
const ROAD_CORRIDOR_EXTRA_HALF = TILE * 0.68;
/** 仅用于 TILE_MAP 栅格化：略小于默认 inset，避免几何路带被收得过窄而出现单格「细线」 */
const ROAD_TILE_GEOM_INSET = 1;
const TARGET_VISIBLE_WORLD_WIDTH = 2200;

function getWorldViewZoom(vw) {
  if (!vw || vw < 1) return 3;
  const raw = vw / TARGET_VISIBLE_WORLD_WIDTH;
  return Math.max(1.45, Math.min(6.5, raw));
}

/** 玩家与 NPC 共用圆形碰撞半径（须早于 facilityAnchor） */
const ENTITY_R = 16;

/** 道路中心线（折线）；主轴 X≈2860 贯通南北，横轴 Y≈2140 串联防线—核心—医疗并接驳侧翼 */
const ROADS = [
  { width: 96, points: [[2860, 380], [2860, 4720]] },
  { width: 84, points: [[1680, 2140], [4580, 2140]] },
  { width: 72, points: [[1680, 2140], [620, 2140]] },
  { width: 72, points: [[4580, 2140], [5580, 2140]] },
  { width: 68, points: [[2860, 860], [3820, 860], [3820, 1320], [2860, 1320]] },
  { width: 64, points: [[2180, 2280], [1560, 2760]] },
  { width: 64, points: [[3960, 2140], [4180, 2480]] },
  { width: 60, points: [[2860, 2860], [2460, 3220]] },
];

/** 工坊入口已整合至基地核心设施交互中 */
const MAP_POIS = [];

/**
 * zone：片区示意；core：占地碰撞与交互（格网内 T_BUILD，须沿路缘贴近）。
 * 可选 sprite：仅绘制用；anchor：bottom-center（底边居中）、bottom-left（底边左对齐 core，不向西侵占道路）。
 * 设施 id 与 game/narrative_map.py API 一致（comm/mine/lab…）。
 */
/** 主纵街 x=2860 宽 96 → 东缘 2908；主轴 y=2140 宽 84 → 北缘 2098、南缘 2182。建筑 core 与路缘留约 4 单位间隙。 */
const FACILITIES = [
  { id: "sunk_lab", name: "沉没实验室", zone: { x: 2552, y: 280, w: 1080, h: 480 }, core: { x: 2912, y: 440, w: 460, h: 260 } },
  {
    id: "mine_ruins",
    name: "废弃矿场表层",
    zone: { x: 2532, y: 820, w: 1160, h: 500 },
    /** 左缘对齐原 2912，不侵占主纵街（x≈2860 路宽 96）；贴图向东上展开 */
    core: { x: 2912, y: 960, w: 560, h: 320 },
    sprite: { w: 720, h: 400, anchor: "bottom-left" },
  },
  {
    id: "helipad",
    name: "停机坪",
    zone: { x: 3320, y: 1000, w: 560, h: 360 },
    core: { x: 3450, y: 1060, w: 400, h: 220 },
    sprite: { w: 520, h: 290, anchor: "bottom-center" },
  },
  { id: "echo_site", name: "回声集团信标塔", zone: { x: 400, y: 1550, w: 640, h: 580 }, core: { x: 620, y: 1794, w: 320, h: 280 } },
  { id: "parliament_ruin", name: "议会前哨站废墟", zone: { x: 5040, y: 1574, w: 660, h: 600 }, core: { x: 5280, y: 1794, w: 340, h: 280 } },
  { id: "defense", name: "海岸防线", zone: { x: 2088, y: 1554, w: 920, h: 640 }, core: { x: 2388, y: 1794, w: 420, h: 300 } },
  { id: "command", name: "基地核心", zone: { x: 2672, y: 1574, w: 780, h: 660 }, core: { x: 2912, y: 1794, w: 380, h: 300 } },
  { id: "lab", name: "医疗实验室", zone: { x: 3020, y: 1594, w: 840, h: 620 }, core: { x: 3300, y: 1794, w: 360, h: 300 } },
  { id: "shore_cave", name: "海岸线洞穴", zone: { x: 1180, y: 2480, w: 480, h: 420 }, core: { x: 1280, y: 2540, w: 280, h: 220 } },
  { id: "comm", name: "通讯阵列", zone: { x: 2612, y: 2006, w: 780, h: 560 }, core: { x: 2912, y: 2186, w: 360, h: 260 } },
  { id: "listen", name: "地下监听站", zone: { x: 3348, y: 1986, w: 800, h: 580 }, core: { x: 3668, y: 2186, w: 340, h: 280 } },
  { id: "mine", name: "源矿采集点", zone: { x: 2512, y: 2900, w: 980, h: 640 }, core: { x: 2912, y: 3140, w: 460, h: 300 } },
  { id: "purify_grove", name: "净空会圣树", zone: { x: 2572, y: 3620, w: 840, h: 480 }, core: { x: 2912, y: 3800, w: 380, h: 280 } },
];

/** 设施碰撞/交互占地（始终为 core） */
function facilityFootprint(f) {
  return f.core;
}

/** 设施贴图绘制框（有 sprite 时按锚点相对 core 展开） */
function facilityDrawRect(f) {
  const c = f.core;
  const sp = f.sprite;
  if (!sp) return { x: c.x, y: c.y, w: c.w, h: c.h };
  const w = sp.w ?? c.w;
  const h = sp.h ?? c.h;
  if (sp.anchor === "bottom-center") {
    return { x: c.x + c.w * 0.5 - w * 0.5, y: c.y + c.h - h, w, h };
  }
  if (sp.anchor === "bottom-left") {
    return { x: c.x, y: c.y + c.h - h, w, h };
  }
  return { x: c.x, y: c.y, w, h };
}

function distPointToSegmentSquared(px, py, x1, y1, x2, y2) {
  const vx = x2 - x1;
  const vy = y2 - y1;
  const wx = px - x1;
  const wy = py - y1;
  const c2 = vx * vx + vy * vy;
  if (c2 < 1e-10) {
    const dx = px - x1;
    const dy = py - y1;
    return dx * dx + dy * dy;
  }
  let t = (wx * vx + wy * vy) / c2;
  t = Math.max(0, Math.min(1, t));
  const qx = x1 + t * vx;
  const qy = y1 + t * vy;
  const dx = px - qx;
  const dy = py - qy;
  return dx * dx + dy * dy;
}

/** 几何路带检测；extraHalf 仅在栅格化时加宽路面；geomInset 默认与路面禁入边距一致，栅格化可减小以覆盖斜路 */
function pointInRoadCorridorGeom(px, py, r, extraHalf = 0, geomInset = 5) {
  const inset = geomInset;
  for (const road of ROADS) {
    const half = road.width * 0.5 - r - inset + extraHalf;
    if (half < 8) continue;
    const lim2 = half * half;
    const pts = road.points;
    for (let i = 0; i < pts.length - 1; i++) {
      if (distPointToSegmentSquared(px, py, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) <= lim2) return true;
    }
  }
  return false;
}

function closestPointOnRoadNetwork(px, py) {
  let bestX = px;
  let bestY = py;
  let bestD2 = Infinity;
  for (const road of ROADS) {
    const pts = road.points;
    for (let i = 0; i < pts.length - 1; i++) {
      const x1 = pts[i][0],
        y1 = pts[i][1],
        x2 = pts[i + 1][0],
        y2 = pts[i + 1][1];
      const vx = x2 - x1,
        vy = y2 - y1;
      const wx = px - x1,
        wy = py - y1;
      const c2 = vx * vx + vy * vy;
      const t = c2 > 1e-10 ? Math.max(0, Math.min(1, (wx * vx + wy * vy) / c2)) : 0;
      const qx = x1 + t * vx;
      const qy = y1 + t * vy;
      const dx = px - qx;
      const dy = py - qy;
      const d2 = dx * dx + dy * dy;
      if (d2 < bestD2) {
        bestD2 = d2;
        bestX = qx;
        bestY = qy;
      }
    }
  }
  return { x: bestX, y: bestY };
}

function rectOverlapsPad(a, b, pad) {
  return !(a.x + a.w + pad <= b.x || b.x + b.w + pad <= a.x || a.y + a.h + pad <= b.y || b.y + b.h + pad <= a.y);
}

/** 点是否在「路面 + pad」范围内（用于防止布景楼体角侵占道路） */
function pointOverlapsRoadPavement(px, py, pad = 3) {
  for (const road of ROADS) {
    const half = road.width * 0.5 + pad;
    const lim2 = half * half;
    const pts = road.points;
    for (let i = 0; i < pts.length - 1; i++) {
      if (distPointToSegmentSquared(px, py, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) <= lim2) return true;
    }
  }
  return false;
}

function rotatedRectCorners(cx, cy, w, h, ang) {
  const c = Math.cos(ang);
  const s = Math.sin(ang);
  const hw = w * 0.5;
  const hh = h * 0.5;
  const loc = [
    [-hw, -hh],
    [hw, -hh],
    [hw, hh],
    [-hw, hh],
  ];
  return loc.map(([lx, ly]) => [cx + c * lx - s * ly, cy + s * lx + c * ly]);
}

function decorAabbFromOriented(cx, cy, w, h, ang) {
  const pts = rotatedRectCorners(cx, cy, w, h, ang);
  let minx = Infinity;
  let miny = Infinity;
  let maxx = -Infinity;
  let maxy = -Infinity;
  for (const [qx, qy] of pts) {
    minx = Math.min(minx, qx);
    miny = Math.min(miny, qy);
    maxx = Math.max(maxx, qx);
    maxy = Math.max(maxy, qy);
  }
  return { x: minx, y: miny, w: maxx - minx, h: maxy - miny };
}

function decorLotValid(cx, cy, w, depth, ang) {
  for (const [qx, qy] of rotatedRectCorners(cx, cy, w, depth, ang)) {
    if (pointOverlapsRoadPavement(qx, qy, 2)) return false;
  }
  const aabb = decorAabbFromOriented(cx, cy, w, depth, ang);
  for (const f of FACILITIES) {
    if (rectOverlapsPad(aabb, f.core, 14)) return false;
  }
  if (aabb.x < 8 || aabb.y < 8 || aabb.x + aabb.w > WORLD.w - 8 || aabb.y + aabb.h > WORLD.h - 8) return false;
  return true;
}

/**
 * 沿路侧规律排列的街块（商住体量）：沿路段等距开间，两侧对称，旋转与路平行；角点不压路面。
 */
function buildDecorBuildings() {
  const out = [];
  const seen = new Set();
  const cellMap = new Map();
  const cellSize = 88;
  function cellKey(cx, cy) {
    return `${Math.floor(cx / cellSize)},${Math.floor(cy / cellSize)}`;
  }
  function registerLot(lo) {
    const k = cellKey(lo.cx, lo.cy);
    if (!cellMap.has(k)) cellMap.set(k, []);
    cellMap.get(k).push(lo);
  }
  function nearbyCrowded(cx, cy, minD) {
    const gx = Math.floor(cx / cellSize);
    const gy = Math.floor(cy / cellSize);
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const arr = cellMap.get(`${gx + dx},${gy + dy}`);
        if (!arr) continue;
        for (const o of arr) {
          if (Math.hypot(o.cx - cx, o.cy - cy) < minD) return true;
        }
      }
    }
    return false;
  }

  const stepBase = 76;
  let segIndex = 0;
  for (const road of ROADS) {
    const pts = road.points;
    const half = road.width * 0.5;
    const gap = 10;
    for (let i = 0; i < pts.length - 1; i++) {
      const x1 = pts[i][0],
        y1 = pts[i][1],
        x2 = pts[i + 1][0],
        y2 = pts[i + 1][1];
      const dx = x2 - x1,
        dy = y2 - y1;
      const len = Math.hypot(dx, dy);
      if (len < stepBase * 1.25) {
        segIndex++;
        continue;
      }
      const ux = dx / len,
        uy = dy / len;
      const nx = -uy,
        ny = ux;
      const step = stepBase + (segIndex % 3) * 4;
      const ang = Math.atan2(uy, ux);

      for (const side of [-1, 1]) {
        let slot = 0;
        for (let s = step * 0.42; s < len - step * 0.42; s += step) {
          const px = x1 + ux * s;
          const py = y1 + uy * s;
          const depth = 48 + ((segIndex * 17 + slot * 23) % 26);
          const facW = 60 + ((slot * 7 + segIndex) % 6) * 3;
          const d = half + gap + depth * 0.5 + 3;
          const cx = px + nx * d * side;
          const cy = py + ny * d * side;

          if (!decorLotValid(cx, cy, facW, depth, ang)) {
            slot++;
            continue;
          }
          const k = `${Math.round(cx / 20)}_${Math.round(cy / 20)}`;
          if (seen.has(k)) {
            slot++;
            continue;
          }
          if (nearbyCrowded(cx, cy, 32)) {
            slot++;
            continue;
          }
          seen.add(k);
          const lo = { cx, cy, w: facW, h: depth, ang };
          out.push(lo);
          registerLot(lo);
          slot++;
        }
      }
      segIndex++;
    }
  }
  return out;
}

const DECOR_BUILDINGS = buildDecorBuildings();

function aabbIntersects(a, b) {
  return !(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h <= b.y || b.y + b.h <= a.y);
}

/** 格心在轴对齐矩形内（半开区间）。TILE_MAP 用此代替「整块格子与 core 相交」，避免紧邻建筑的缝格整格标成建筑、主轴只剩 1 格路面 */
function tileCenterInAabb(cx, cy, box) {
  return cx >= box.x && cx < box.x + box.w && cy >= box.y && cy < box.y + box.h;
}

function tileWorldAabb(tx, ty) {
  return { x: tx * TILE, y: ty * TILE, w: TILE, h: TILE };
}

/** 格子是否与「加宽后的」路带相交（密网格采样，斜路/窄条与对角邻接不会因漏采样变成断续单格） */
function tileCellHasRoad(tx, ty) {
  const cell = tileWorldAabb(tx, ty);
  const ex = ROAD_CORRIDOR_EXTRA_HALF;
  const gi = ROAD_TILE_GEOM_INSET;
  const n = 7;
  const eps = 1.5;
  const span = TILE - 2 * eps;
  for (let iy = 0; iy < n; iy++) {
    for (let ix = 0; ix < n; ix++) {
      const sx = cell.x + eps + (n > 1 ? (span * ix) / (n - 1) : span * 0.5);
      const sy = cell.y + eps + (n > 1 ? (span * iy) / (n - 1) : span * 0.5);
      if (pointInRoadCorridorGeom(sx, sy, 0, ex, gi)) return true;
    }
  }
  return false;
}

/** 将仍为 T_VOID、但与已标路格 8 邻且格心在路带内的格子补为路，填平斜向/拐角处的单格漏缝（可跑多遍以弥合对角断档） */
function dilateRoadIntoCorridorVoid(tiles, passes = 2) {
  const w = MAP_TILES_X;
  const h = MAP_TILES_Y;
  const ex = ROAD_CORRIDOR_EXTRA_HALF;
  const gi = ROAD_TILE_GEOM_INSET;
  for (let pass = 0; pass < passes; pass++) {
    const snap = new Uint8Array(tiles);
    for (let ty = 0; ty < h; ty++) {
      for (let tx = 0; tx < w; tx++) {
        const i = ty * w + tx;
        if (snap[i] !== T_VOID) continue;
        let nearRoad = false;
        for (let dy = -1; dy <= 1 && !nearRoad; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if (dx === 0 && dy === 0) continue;
            const nx = tx + dx;
            const ny = ty + dy;
            if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
            if (snap[ny * w + nx] === T_ROAD) {
              nearRoad = true;
              break;
            }
          }
        }
        if (!nearRoad) continue;
        const cx = tx * TILE + TILE * 0.5;
        const cy = ty * TILE + TILE * 0.5;
        if (pointInRoadCorridorGeom(cx, cy, 0, ex, gi)) tiles[i] = T_ROAD;
      }
    }
  }
}

function pointInOrientedRect(px, py, b) {
  const dx = px - b.cx;
  const dy = py - b.cy;
  const c = Math.cos(-b.ang);
  const s = Math.sin(-b.ang);
  const lx = dx * c - dy * s;
  const ly = dx * s + dy * c;
  return Math.abs(lx) <= b.w * 0.5 + 1e-6 && Math.abs(ly) <= b.h * 0.5 + 1e-6;
}

/** 由设施 core、布景块与矢量路带栅格化得到的地图；保持原 ROADS/FACILITIES/DECOR 排版 */
function buildTileMap() {
  const tiles = new Uint8Array(MAP_TILES_X * MAP_TILES_Y);
  for (let ty = 0; ty < MAP_TILES_Y; ty++) {
    for (let tx = 0; tx < MAP_TILES_X; tx++) {
      const i = ty * MAP_TILES_X + tx;
      const cell = tileWorldAabb(tx, ty);
      const cx = cell.x + TILE * 0.5;
      const cy = cell.y + TILE * 0.5;
      let t = T_VOID;
      for (const f of FACILITIES) {
        if (tileCenterInAabb(cx, cy, facilityFootprint(f))) {
          t = T_BUILD;
          break;
        }
      }
      if (t === T_VOID) {
        for (const b of DECOR_BUILDINGS) {
          if (pointInOrientedRect(cx, cy, b)) {
            t = T_BUILD;
            break;
          }
        }
      }
      if (t === T_VOID && tileCellHasRoad(tx, ty)) t = T_ROAD;
      tiles[i] = t;
    }
  }
  dilateRoadIntoCorridorVoid(tiles);
  return tiles;
}

const TILE_MAP = buildTileMap();

function tileTypeAt(tx, ty) {
  if (tx < 0 || ty < 0 || tx >= MAP_TILES_X || ty >= MAP_TILES_Y) return T_VOID;
  return TILE_MAP[ty * MAP_TILES_X + tx];
}

function circleIntersectsTile(px, py, r, tx, ty) {
  const rx = tx * TILE;
  const ry = ty * TILE;
  const qx = Math.max(rx, Math.min(px, rx + TILE));
  const qy = Math.max(ry, Math.min(py, ry + TILE));
  const dx = px - qx;
  const dy = py - qy;
  return dx * dx + dy * dy <= r * r;
}

function movementObstacleFromTiles(px, py, r) {
  const tx0 = Math.floor((px - r) / TILE);
  const tx1 = Math.floor((px + r) / TILE);
  const ty0 = Math.floor((py - r) / TILE);
  const ty1 = Math.floor((py + r) / TILE);
  let hitBuild = false;
  let hitVoid = false;
  let hitRoad = false;
  for (let ty = ty0; ty <= ty1; ty++) {
    for (let tx = tx0; tx <= tx1; tx++) {
      if (!circleIntersectsTile(px, py, r, tx, ty)) continue;
      const tt = tileTypeAt(tx, ty);
      if (tt === T_BUILD) hitBuild = true;
      else if (tt === T_ROAD) hitRoad = true;
      else hitVoid = true;
    }
  }
  if (hitBuild) return { kind: "building" };
  if (hitVoid || !hitRoad) return { kind: "offroad" };
  return null;
}

/** 格地图上的可站立路格（不含剧情禁区；禁区在 movementObstacleAt 中另判） */
function pointOnRoadNetwork(px, py, r) {
  return movementObstacleFromTiles(px, py, r) === null;
}

let tileTerrainCanvas = null;

/** 与 TILE_MAP：T_VOID / T_ROAD / T_BUILD 对应的像素贴图（web/explorer/assets/） */
const voidTileTexture = new Image();
const roadTileTexture = new Image();
const buildTileTexture = new Image();
/** T_ROAD：若 tile_road.jpg 缺失则回退此前路面 PNG */
const roadTileFallbackTexture = new Image();

function tileAssetBaseUrl() {
  const el = document.querySelector('script[type="module"][src*="main.js"]');
  const scriptSrc = el?.src;
  if (scriptSrc) return scriptSrc;
  if (typeof import.meta !== "undefined" && import.meta.url) return import.meta.url;
  return window.location.href;
}

function invalidateTileTerrainCanvas() {
  tileTerrainCanvas = null;
}

function wireTileImage(img, relativePath, warnLabel) {
  const href = new URL(relativePath, tileAssetBaseUrl()).href;
  const onReady = () => {
    const dec = img.decode?.();
    if (dec && typeof dec.then === "function") dec.then(invalidateTileTerrainCanvas, invalidateTileTerrainCanvas);
    else invalidateTileTerrainCanvas();
  };
  img.onload = onReady;
  img.onerror = () => {
    console.warn(`[explorer] 地块贴图加载失败 [${warnLabel}]（须能通过静态服务访问 web/explorer/assets/）:`, href);
    invalidateTileTerrainCanvas();
  };
  img.src = href;
  if (img.complete && img.naturalWidth > 0) onReady();
}

/** 设施大地图 sprite：web/explorer/assets/facilities/{id}.png */
const facilitySpriteImages = new Map();

/** NPC / 设施对话立绘：web/explorer/assets/portraits/ */
const portraitSpriteImages = new Map();

const PORTRAIT_SPRITE_PATH = {
  karen: "./assets/portraits/karen.png",
  dr_lin: "./assets/portraits/dr_lin.jpg",
  chubby: "./assets/portraits/chubby.png",
  klein: "./assets/portraits/klein.png",
  echo_7: "./assets/portraits/echo_7.jpg",
  jin: "./assets/portraits/jin.jpg",
  elizabeth: "./assets/portraits/elizabeth.jpg",
  source: "./assets/portraits/source.png",
};

let storyPortraitKind = "";
let storyPortraitId = "";
let storyPortraitLabel = "";

function wireExplorerAsset(img, relativePath, warnLabel, onReady) {
  const href = new URL(relativePath, tileAssetBaseUrl()).href;
  const ready = () => {
    const dec = img.decode?.();
    if (dec && typeof dec.then === "function") dec.then(onReady, onReady);
    else onReady?.();
  };
  img.onload = ready;
  img.onerror = () => {
    console.warn(`[explorer] 资源加载失败 [${warnLabel}]:`, href);
    onReady?.();
  };
  img.src = href;
  if (img.complete && img.naturalWidth > 0) ready();
}

/** 按需加载单个设施贴图（替代启动时全量预加载） */
function loadFacilitySprite(id) {
  if (facilitySpriteImages.has(id)) return;
  const f = FACILITIES.find((x) => x.id === id);
  if (!f) return;
  const rel = `./assets/facilities/${f.id}.png`;
  const img = new Image();
  facilitySpriteImages.set(f.id, img);
  wireExplorerAsset(img, rel, `facility_${f.id}`, () => {});
}

/** 按需加载单个 NPC 立绘（替代启动时全量预加载） */
function loadPortraitSprite(id) {
  if (portraitSpriteImages.has(id)) return;
  const rel = PORTRAIT_SPRITE_PATH[id];
  if (!rel) return;
  const img = new Image();
  portraitSpriteImages.set(id, img);
  wireExplorerAsset(img, rel, `portrait_${id}`, () => {
    if (storyPortraitKind === "npc" && storyPortraitId === id) {
      setStoryPortrait("npc", id, storyPortraitLabel);
    }
  });
}

function startFacilitySpriteLoad() {
  for (const f of FACILITIES) {
    const rel = `./assets/facilities/${f.id}.png`;
    const img = new Image();
    facilitySpriteImages.set(f.id, img);
    wireExplorerAsset(img, rel, `facility_${f.id}`, () => {});
  }
}

function startPortraitSpriteLoad() {
  for (const [id, rel] of Object.entries(PORTRAIT_SPRITE_PATH)) {
    const img = new Image();
    portraitSpriteImages.set(id, img);
    wireExplorerAsset(img, rel, `portrait_${id}`, () => {
      if (storyPortraitKind === "npc" && storyPortraitId === id) {
        setStoryPortrait("npc", id, storyPortraitLabel);
      }
    });
  }
}

const WORKSHOP_DEVICE_ICON = {
  miner: "采",
  smelter: "冶",
  assembler: "组",
  refiner: "炼",
  printer: "印",
  power_plant: "电",
  power_core: "核",
  storage: "仓",
};

/** 与 tools/sync_explorer_icons.py 输出一致：web/explorer/assets/icons/{name}.png */
const EXPLORER_ICON_PATH = {
  miner: "./assets/icons/miner.png",
  smelter: "./assets/icons/smelter.png",
  assembler: "./assets/icons/assembler.png",
  refiner: "./assets/icons/refiner.png",
  printer: "./assets/icons/printer.png",
  power_plant: "./assets/icons/power_plant.png",
  power_core: "./assets/icons/power_core.png",
  storage: "./assets/icons/storage.png",
  resource_energy: "./assets/icons/resource_energy.png",
  resource_parts: "./assets/icons/resource_parts.png",
  resource_food: "./assets/icons/resource_food.png",
  resource_medical: "./assets/icons/resource_medical.png",
  resource_intel: "./assets/icons/resource_intel.png",
  tab_current: "./assets/icons/tab_current.png",
  tab_upcoming: "./assets/icons/tab_upcoming.png",
  tab_management: "./assets/icons/tab_management.png",
  tab_explore: "./assets/icons/tab_explore.png",
  tab_dossier: "./assets/icons/tab_dossier.png",
  tab_tutorial: "./assets/icons/tab_tutorial.png",
  favicon: "./assets/icons/favicon.png",
};

const OBJECTIVES_TAB_ICON_KEY = {
  current: "tab_current",
  upcoming: "tab_upcoming",
  mgmt: "tab_management",
  explore: "tab_explore",
  dossier: "tab_dossier",
};

const RESOURCE_STRIP_ICON_KEY = {
  energy: "resource_energy",
  food: "resource_food",
  medical: "resource_medical",
  intel: "resource_intel",
  parts: "resource_parts",
};

const explorerIconImages = new Map();

function startMapTileTexturesLoad() {
  wireTileImage(voidTileTexture, "./assets/tile_void.jpg", "void");
  wireTileImage(roadTileTexture, "./assets/tile_road.jpg", "road");
  wireTileImage(buildTileTexture, "./assets/tile_build.jpg", "build");
  wireTileImage(roadTileFallbackTexture, "./assets/walkable_floor_tile.png", "road_fallback");
  startFacilitySpriteLoad();
  startPortraitSpriteLoad();
  startExplorerIconLoad();
}

// ── 预加载器：加载页 + 全部资源预加载 ──
(function initPreloader() {
  const screen = document.getElementById("preloader");
  const bar = document.getElementById("preloader-bar");
  const text = document.getElementById("preloader-text");
  if (!screen || !bar || !text) {
    startMapTileTexturesLoad();
    return;
  }

  // 计算资源基础 URL
  const baseEl = document.querySelector('script[type="module"][src*="main.js"]');
  const base = baseEl?.src || (typeof import.meta !== "undefined" && import.meta.url) || window.location.href;

  // 收集所有图片 URL
  const tileRel = [
    "./assets/tile_void.jpg", "./assets/tile_road.jpg",
    "./assets/tile_build.jpg", "./assets/walkable_floor_tile.png",
  ];
  const facilityIds = FACILITIES.map((f) => f.id);
  const portraitRel = Object.values(PORTRAIT_SPRITE_PATH);
  const iconRel = Object.values(EXPLORER_ICON_PATH);

  const urls = [
    ...tileRel.map((r) => new URL(r, base).href),
    ...facilityIds.map((id) => new URL(`./assets/facilities/${id}.png`, base).href),
    ...portraitRel.map((r) => new URL(r, base).href),
    ...iconRel.map((r) => new URL(r, base).href),
  ];

  let loaded = 0;
  const total = urls.length;

  function updateProgress() {
    const pct = Math.round((loaded / total) * 100);
    bar.style.width = pct + "%";
    text.textContent = `正在加载资源... ${loaded}/${total}`;
  }

  function onAllDone() {
    bar.style.width = "100%";
    text.textContent = "初始化完成";
    setTimeout(() => {
      screen.classList.add("preloader--done");
      setTimeout(() => screen.remove(), 700);
    }, 200);
    startMapTileTexturesLoad();
  }

  updateProgress();

  if (urls.length === 0) {
    onAllDone();
    return;
  }

  for (const url of urls) {
    const img = new Image();
    img.onload = img.onerror = () => {
      loaded++;
      updateProgress();
      if (loaded >= total) onAllDone();
    };
    img.src = url;
  }
})();

function ensureTileTerrainCanvas() {
  if (tileTerrainCanvas) return tileTerrainCanvas;
  const c = document.createElement("canvas");
  c.width = WORLD.w;
  c.height = WORLD.h;
  const tctx = c.getContext("2d");
  const voidRgb = [14, 22, 36];
  const roadRgb = [48, 54, 68];
  const buildRgb = [26, 32, 44];
  const voidTexReady = voidTileTexture.complete && voidTileTexture.naturalWidth > 0;
  const roadTexReady = roadTileTexture.complete && roadTileTexture.naturalWidth > 0;
  const roadFbReady = roadTileFallbackTexture.complete && roadTileFallbackTexture.naturalWidth > 0;
  const buildTexReady = buildTileTexture.complete && buildTileTexture.naturalWidth > 0;
  if (voidTexReady || roadTexReady || roadFbReady || buildTexReady) tctx.imageSmoothingEnabled = false;
  for (let ty = 0; ty < MAP_TILES_Y; ty++) {
    for (let tx = 0; tx < MAP_TILES_X; tx++) {
      const tt = TILE_MAP[ty * MAP_TILES_X + tx];
      const x = tx * TILE;
      const y = ty * TILE;
      if (tt === T_ROAD) {
        if (roadTexReady) tctx.drawImage(roadTileTexture, x, y, TILE + 1, TILE + 1);
        else if (roadFbReady) tctx.drawImage(roadTileFallbackTexture, x, y, TILE + 1, TILE + 1);
        else {
          tctx.fillStyle = `rgb(${roadRgb[0]},${roadRgb[1]},${roadRgb[2]})`;
          tctx.fillRect(x, y, TILE + 1, TILE + 1);
        }
      } else if (tt === T_BUILD) {
        if (buildTexReady) tctx.drawImage(buildTileTexture, x, y, TILE + 1, TILE + 1);
        else {
          tctx.fillStyle = `rgb(${buildRgb[0]},${buildRgb[1]},${buildRgb[2]})`;
          tctx.fillRect(x, y, TILE + 1, TILE + 1);
        }
      } else {
        if (voidTexReady) tctx.drawImage(voidTileTexture, x, y, TILE + 1, TILE + 1);
        else {
          tctx.fillStyle = `rgb(${voidRgb[0]},${voidRgb[1]},${voidRgb[2]})`;
          tctx.fillRect(x, y, TILE + 1, TILE + 1);
        }
      }
    }
  }
  tctx.strokeStyle = "rgba(0, 0, 0, 0.14)";
  tctx.lineWidth = 1;
  for (let x = 0; x <= WORLD.w; x += TILE) {
    tctx.beginPath();
    tctx.moveTo(x, 0);
    tctx.lineTo(x, WORLD.h);
    tctx.stroke();
  }
  for (let y = 0; y <= WORLD.h; y += TILE) {
    tctx.beginPath();
    tctx.moveTo(0, y);
    tctx.lineTo(WORLD.w, y);
    tctx.stroke();
  }
  tileTerrainCanvas = c;
  return c;
}
const NPCS = [
  { id: "karen", name: "卡伦", blurb: "基地安全负责人" },
  { id: "dr_lin", name: "林博士", blurb: "科研主管" },
  { id: "chubby", name: "小胖", blurb: "机械维修工" },
  { id: "jin", name: "堇", blurb: "生态研究员" },
  { id: "echo_7", name: "回声-7", blurb: "通讯侧界面" },
  { id: "klein", name: "克莱因", blurb: "深层牢房中的老人" },
  { id: "elizabeth", name: "伊丽莎白·莫罗", blurb: "议会（远程联络）" },
];

let latestState = null;

/** 岸线侵入进度 0–1（无存档时与后端默认 25% 一致，便于本地预览仍有威胁带） */
function incursionRatio() {
  const v = Number(latestState?.session?.hidden?.INCURSION);
  if (!Number.isFinite(v)) return 0.25;
  return Math.max(0, Math.min(1, v / 100));
}

/**
 * 西岸侵入带：自西向东推进，随 INCURSION 加深；与 map_design 西侧海岸/洞穴侧一致。
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} ratio 0–1
 * @param {number} nowMs performance.now
 */
function drawShoreIntrusion(ctx, ratio, nowMs) {
  const t = nowMs * 0.001;
  const depth = Math.min(WORLD.w * 0.5, 140 + ratio * WORLD.w * 0.42);

  const bodyGrad = ctx.createLinearGradient(0, 0, depth, 0);
  bodyGrad.addColorStop(0, `rgba(0, 235, 255, ${0.14 + ratio * 0.16})`);
  bodyGrad.addColorStop(0.22, `rgba(160, 70, 255, ${0.07 + ratio * 0.1})`);
  bodyGrad.addColorStop(0.55, `rgba(30, 90, 160, ${0.06 + ratio * 0.08})`);
  bodyGrad.addColorStop(1, "rgba(8, 14, 28, 0)");
  ctx.fillStyle = bodyGrad;
  ctx.fillRect(0, 0, depth, WORLD.h);

  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, depth, WORLD.h);
  ctx.clip();
  ctx.globalCompositeOperation = "lighter";
  const bandStep = Math.max(56, Math.floor(520 - ratio * 320));
  for (let y = 0; y < WORLD.h; y += bandStep) {
    const flicker = 0.35 + 0.65 * Math.sin(y * 0.004 + t * 1.4);
    ctx.strokeStyle = `rgba(120, 255, 245, ${(0.04 + ratio * 0.1) * flicker})`;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    for (let x = 0; x <= depth + 20; x += 48) {
      ctx.lineTo(x, y + Math.sin(t * 2.2 + x * 0.012 + y * 0.001) * (10 + ratio * 18));
    }
    ctx.stroke();
  }
  ctx.globalCompositeOperation = "source-over";
  ctx.restore();

  ctx.strokeStyle = `rgba(200, 250, 255, ${0.28 + ratio * 0.42})`;
  ctx.lineWidth = 2 + ratio * 2;
  ctx.shadowColor = `rgba(0, 220, 255, ${0.25 + ratio * 0.35})`;
  ctx.shadowBlur = 8 + ratio * 10;
  ctx.beginPath();
  for (let y = 0; y <= WORLD.h; y += 20) {
    const x = depth + Math.sin(y * 0.022 + t * 0.65) * (16 + ratio * 36);
    if (y === 0) ctx.moveTo(x, 0);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  ctx.shadowBlur = 0;

  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, depth * 0.95, WORLD.h);
  ctx.clip();
  ctx.strokeStyle = `rgba(70, 210, 255, ${0.1 + ratio * 0.28})`;
  ctx.lineWidth = 5;
  const nDiag = 8 + Math.round(ratio * 10);
  for (let i = 0; i < nDiag; i++) {
    ctx.beginPath();
    const x0 = (i / nDiag) * depth * 0.55 + Math.sin(t + i) * 24;
    ctx.moveTo(x0, -40);
    ctx.lineTo(x0 + WORLD.w * 0.055 + i * 18, WORLD.h + 40);
    ctx.stroke();
  }
  ctx.restore();
}

/** 剧情聚焦 NPC → 大地图优先引导的设施（与 narrative_map 设施 id 一致） */
const NPC_FOCUS_GUIDE_FACILITY = {
  karen: "command",
  dr_lin: "lab",
  chubby: "mine",
  jin: "command",
  echo_7: "comm",
  klein: "sunk_lab",
  elizabeth: "comm",
};

function facilityZoneCenter(fid) {
  const f = FACILITIES.find((x) => x.id === fid);
  if (!f) return null;
  return { wx: f.zone.x + f.zone.w / 2, wy: f.zone.y + f.zone.h / 2, name: f.name };
}

/**
 * 当前剧情下一步指引（世界坐标 + 文案）；供箭头 HUD 与任务栏同步。
 * @returns {{ wx: number, wy: number, label_zh: string } | null}
 */
function computeNextStepGuide(state) {
  if (!state?.narrative) return null;
  const nar = state.narrative;
  const hints = nar.facility_hints || {};
  /** 与后端 facility_hints 键顺序一致（用于「剧情相关设施」兜底指引） */
  const facOrder = [
    "command",
    "comm",
    "mine",
    "lab",
    "listen",
    "defense",
    "helipad",
    "purify_grove",
    "sunk_lab",
  ];

  if (nar.node_id === "FIN-02") {
    const c = facilityZoneCenter("command");
    return c ? { wx: c.wx, wy: c.wy, label_zh: "前往基地核心：做出最终结局选择" } : null;
  }

  for (const fid of facOrder) {
    const h = hints[fid];
    if (h?.upgrade_choice_id) {
      const c = facilityZoneCenter(fid);
      if (!c) continue;
      // 尝试用选择标签替换笼统文案
      const pick = (nar.choices || []).find((ch) => ch.id === h.upgrade_choice_id);
      const action = pick ? `确认：${pick.label_zh}` : "确认优先方向";
      return { wx: c.wx, wy: c.wy, label_zh: `前往「${c.name}」${action}` };
    }
  }

  const focus = nar.npc_focus || [];
  const nonSource = focus.filter((id) => id !== "source");
  /** NPC 焦点优先于泛化的 story_relevant（避免多设施同时相关时误指会议室） */
  for (const npcId of nonSource) {
    const fid = NPC_FOCUS_GUIDE_FACILITY[npcId];
    if (!fid) continue;
    const c = facilityZoneCenter(fid);
    const npcName = NPCS.find((n) => n.id === npcId)?.name || npcId;
    if (c) return { wx: c.wx, wy: c.wy, npcId, label_zh: `前往「${c.name}」附近寻找 ${npcName}` };
  }

  for (const fid of facOrder) {
    if (hints[fid]?.story_relevant) {
      const c = facilityZoneCenter(fid);
      if (!c) continue;
      if (nar.node_id === "PRO-04" || nar.node_id === "03-03") {
        return { wx: c.wx, wy: c.wy, label_zh: `前往「${c.name}」与源交互 / 推进低语节点` };
      }
      if (nar.node_id === "02-02") {
        return { wx: c.wx, wy: c.wy, label_zh: `前往「${c.name}」——记忆闪回将自动触发` };
      }
      return { wx: c.wx, wy: c.wy, label_zh: `前往「${c.name}」推进当前剧情节点` };
    }
  }

  if (focus.includes("source")) {
    const c = facilityZoneCenter("listen");
    return c ? { wx: c.wx, wy: c.wy, label_zh: "前往「地下监听站」聆听源的低语" } : null;
  }

  if ((nar.choices?.length > 0 || nar.fin_endings?.length > 0) && !nar.can_advance_default) {
    const c = facilityZoneCenter("command");
    return c
      ? {
          wx: c.wx,
          wy: c.wy,
          label_zh: "靠近角色按 E 打开剧情，在选项中做出选择",
        }
      : null;
  }

  /** 纯自动推进节点：无焦点 NPC / 无剧情相关设施时再指向指挥中心（避免 01-04 等误判） */
  if (nar.can_advance_default) {
    const c = facilityZoneCenter("command");
    return c ? { wx: c.wx, wy: c.wy, label_zh: "前往基地核心：推进剧情（当前无分支选项）" } : null;
  }

  const c = facilityZoneCenter("command");
  return c ? { wx: c.wx, wy: c.wy, label_zh: "在基地继续探索；留意地图上的设施与角色" } : null;
}

/** 从点(px,py)沿方向(dx,dy)射到内框边，返回箭头落点 */
function rayToScreenEdge(px, py, dx, dy, w, h, margin, topMargin) {
  const L = margin;
  const R = w - margin;
  const T = topMargin !== undefined ? topMargin : margin;
  const B = h - margin;
  let bestT = Infinity;
  let bx = px;
  let by = py;
  function consider(t) {
    if (t <= 0 || !Number.isFinite(t)) return;
    const x = px + t * dx;
    const y = py + t * dy;
    if (x >= L - 1 && x <= R + 1 && y >= T - 1 && y <= B + 1 && t < bestT) {
      bestT = t;
      bx = x;
      by = y;
    }
  }
  if (Math.abs(dx) > 1e-6) {
    consider((L - px) / dx);
    consider((R - px) / dx);
  }
  if (Math.abs(dy) > 1e-6) {
    consider((T - py) / dy);
    consider((B - py) / dy);
  }
  return bestT === Infinity ? null : { x: bx, y: by };
}

function drawObjectiveGuideArrow(vw, vh, minVisibleY) {
  const g = computeNextStepGuide(latestState);
  if (!g) return;

  const { fx: cx, fy: cy } = viewportFocusInCanvas();
  const viewZoom = getWorldViewZoom(vw);

  // 如果有NPC ID，尝试获取NPC的实际位置
  let targetX = g.wx;
  let targetY = g.wy;
  if (g.npcId && npcScheduleSnapshot?.pos?.[g.npcId]) {
    targetX = npcScheduleSnapshot.pos[g.npcId].x;
    targetY = npcScheduleSnapshot.pos[g.npcId].y;
  }

  // 计算目标在屏幕上的位置
  const sx = (targetX - camX) * viewZoom + cx;
  const sy = (targetY - camY) * viewZoom + cy;

  // 计算从玩家到目标的方向
  const dxw = targetX - PLAYER.x;
  const dyw = targetY - PLAYER.y;
  const distW = Math.hypot(dxw, dyw) || 1;
  const ux = dxw / distW;
  const uy = dyw / distW;

  // 计算玩家在屏幕上的位置（用于边缘箭头起点）
  const playerScreenX = (PLAYER.x - camX) * viewZoom + cx;
  const playerScreenY = (PLAYER.y - camY) * viewZoom + cy;

  // 目标在屏幕内：不显示任何指示器
  const onScreen = sx >= 80 && sx <= vw - 80 && sy >= 120 && sy <= vh - 100;
  if (onScreen) return;

  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);

  // 目标在屏幕外：从玩家位置向目标方向投射到边缘
  // 顶部边缘增加安全距离，避免被基地资源DOM挡住
  const topMargin = Math.max(100, (minVisibleY || 88) + 20);
  const hit = rayToScreenEdge(playerScreenX, playerScreenY, ux, uy, vw, vh, 50, topMargin);
  if (hit) {
    const ang = Math.atan2(uy, ux);
    ctx.translate(hit.x, hit.y);
    ctx.rotate(ang);
    const pulse = 0.8 + 0.2 * Math.sin(performance.now() / 300);
    ctx.fillStyle = `rgba(90, 255, 190, ${pulse})`;
    ctx.strokeStyle = `rgba(0, 80, 50, ${pulse * 0.5})`;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(20, 0);
    ctx.lineTo(-10, 10);
    ctx.lineTo(-4, 0);
    ctx.lineTo(-10, -10);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.rotate(-ang);
    ctx.translate(-hit.x, -hit.y);
  }

  ctx.restore();
}

/** —— NPC 游荡：游戏内时钟（浮点小时 0–24，随真实时间流逝，不随玩家移动） —— */
let worldClockHours = 14;
/** 现实时间每经过这么多毫秒 → 游戏内推进 1 小时（默认 8 分钟现实 ≈ 1 游戏小时） */
const REAL_MS_PER_GAME_HOUR = 8 * 60 * 1000;
let worldClockLastRealTs = 0;

function tickWorldClock(ts) {
  if (!worldClockLastRealTs) worldClockLastRealTs = ts;
  const raw = ts - worldClockLastRealTs;
  worldClockLastRealTs = ts;
  const d = Math.min(Math.max(0, raw), 10_000);
  worldClockHours += d / REAL_MS_PER_GAME_HOUR;
  while (worldClockHours >= 24) worldClockHours -= 24;
}

function gameClockHourInt() {
  const sess = latestState?.session;
  const raw = sess?.world_minute_of_day;
  if (Number.isFinite(Number(raw))) {
    const md = Math.max(0, Math.min(1439, Number(raw)));
    return Math.floor(md / 60) % 24;
  }
  return Math.floor(worldClockHours) % 24;
}

function gameClockHHMM() {
  const sess = latestState?.session;
  const raw = sess?.world_minute_of_day;
  if (Number.isFinite(Number(raw))) {
    const md = Math.max(0, Math.min(1439, Number(raw)));
    return { hh: Math.floor(md / 60), mm: md % 60 };
  }
  const totalMin = Math.floor((worldClockHours % 24) * 60);
  const hh = Math.floor(totalMin / 60);
  const mm = totalMin % 60;
  return { hh, mm };
}

function hashHour(npcId, hourKey) {
  const s = `${npcId}:${hourKey}`;
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** 同名设施日程锚点的方位散开（像素级）；减轻多名 NPC 同时扎堆在同一转角 */
function npcSpreadOffset(npcId, seed) {
  if (!npcId) return { dx: 0, dy: 0 };
  const h = hashHour(npcId, seed ^ 0x9e3779b9);
  const ang = ((h >>> 8) % 360) * (Math.PI / 180);
  const rad = 52 + (h % 58);
  return { dx: Math.cos(ang) * rad, dy: Math.sin(ang) * rad };
}

function circleHitsRect(cx, cy, r, rect) {
  const nx = Math.max(rect.x, Math.min(cx, rect.x + rect.w));
  const ny = Math.max(rect.y, Math.min(cy, rect.y + rect.h));
  const ddx = cx - nx;
  const ddy = cy - ny;
  return ddx * ddx + ddy * ddy < r * r;
}

/** 设施片区外沿的可站立点（避开 core，否则 NPC 生在墙里无法移动）
 * @param {string} npcId 可选；传入时为该 NPC 叠加确定性方位偏移，减轻同设施重叠 */
function facilityAnchor(fid, seed = 0, npcId = "") {
  const f = FACILITIES.find((x) => x.id === fid);
  if (!f) return { x: 2860, y: 2120 };
  const z = f.zone;
  const c = f.core;
  const margin = ENTITY_R + 10;
  const candidates = [
    { x: c.x + margin + ((seed >>> 3) % 80), y: c.y + c.h + margin },
    { x: c.x + margin + ((seed >>> 7) % 80), y: c.y - margin },
    { x: c.x - margin, y: c.y + c.h / 2 + (((seed >>> 5) % 60) - 30) },
    { x: c.x + c.w + margin, y: c.y + c.h / 2 + (((seed >>> 9) % 60) - 30) },
    { x: z.x + z.w / 2 + ((seed % 61) - 30), y: z.y + z.h - margin },
    { x: z.x + margin + ((seed >>> 11) % Math.max(40, z.w - 2 * margin)), y: z.y + margin },
  ];
  const otherCores = FACILITIES.filter((g) => g.id !== f.id).map((g) => g.core);
  function inAnyCore(px, py) {
    if (circleHitsRect(px, py, ENTITY_R, c)) return true;
    for (const rct of otherCores) {
      if (circleHitsRect(px, py, ENTITY_R, rct)) return true;
    }
    return false;
  }
  const spread = npcSpreadOffset(npcId, seed);
  for (const p of candidates) {
    let px = p.x + spread.dx;
    let py = p.y + spread.dy;
    px = Math.max(z.x + margin, Math.min(z.x + z.w - margin, px));
    py = Math.max(z.y + margin, Math.min(z.y + z.h - margin, py));
    if (px - ENTITY_R < 0 || px + ENTITY_R > WORLD.w || py - ENTITY_R < 0 || py + ENTITY_R > WORLD.h) continue;
    if (!pointOnRoadNetwork(px, py, ENTITY_R)) continue;
    if (inAnyCore(px, py)) continue;
    const jx = ((seed % 251) / 251 - 0.5) * 56;
    const jy = (((seed >>> 8) % 251) / 251 - 0.5) * 42;
    px = Math.max(z.x + margin, Math.min(z.x + z.w - margin, px + jx));
    py = Math.max(z.y + margin, Math.min(z.y + z.h - margin, py + jy));
    if (!pointOnRoadNetwork(px, py, ENTITY_R)) continue;
    if (!inAnyCore(px, py)) return { x: px, y: py };
  }
  const cr = closestPointOnRoadNetwork(z.x + z.w * 0.5, z.y + z.h * 0.5);
  let ax = Math.max(z.x + margin, Math.min(z.x + z.w - margin, cr.x + spread.dx));
  let ay = Math.max(z.y + margin, Math.min(z.y + z.h - margin, cr.y + spread.dy));
  const fjx = ((seed % 251) / 251 - 0.5) * 56;
  const fjy = (((seed >>> 8) % 251) / 251 - 0.5) * 42;
  ax = Math.max(z.x + margin, Math.min(z.x + z.w - margin, ax + fjx));
  ay = Math.max(z.y + margin, Math.min(z.y + z.h - margin, ay + fjy));
  if (pointOnRoadNetwork(ax, ay, ENTITY_R) && !inAnyCore(ax, ay)) return { x: ax, y: ay };
  return { x: cr.x, y: cr.y };
}

/**
 * 根据当前游戏时刻与存档状态计算 NPC 日程目标点（片区内锚点）；实际位移由 stepAllNpcBodies（与玩家同速、匀速）走向该点。
 * @returns {{ pos: Record<string, {x:number,y:number}>, meta: Record<string, boolean> }}
 */
function scheduledNpcWorldPositions(state) {
  const hour = gameClockHourInt();
  const sess = state?.session || {};
  const hidden = sess.hidden || {};
  const plotFlags = new Set(sess.plot?.flags || []);
  const completed = new Set(sess.completed_nodes || []);
  const act = state?.narrative?.act || "prologue";
  const inc = Number(hidden.INCURSION ?? 25);
  const zones = state?.explorer_zones || [];
  const caveUnlocked = zones.some((z) => String(z.id) === "coastal_cave" && !z.blocks_movement);

  const pos = {};
  const meta = {};

  let kf = "command";
  if (inc >= 55) kf = "defense";
  else if (hour >= 20 || hour < 8) kf = "defense";
  else kf = Math.floor(hour / 2) % 2 === 0 ? "command" : "comm";
  pos.karen = facilityAnchor(kf, hashHour("karen", hour), "karen");

  const linSleep = hour >= 22 || hour < 8;
  meta.dr_lin_sleep = linSleep;
  if (linSleep) {
    pos.dr_lin = facilityAnchor("lab", hashHour("dr_lin_sleep", hour), "dr_lin");
  } else if (hour >= 18 && hour < 22) {
    const listenOk = plotFlags.has("listen_station_built");
    pos.dr_lin = facilityAnchor(listenOk ? "listen" : "lab", hashHour("dr_lin_pm", hour), "dr_lin");
  } else if (hour >= 12 && hour < 18) {
    pos.dr_lin = facilityAnchor("command", hashHour("dr_lin_no", hour), "dr_lin");
  } else {
    pos.dr_lin = facilityAnchor("lab", hashHour("dr_lin_am", hour), "dr_lin");
  }

  let chf = "mine";
  if (hour >= 18 && hour < 20) chf = "mine_ruins";
  else if (hour >= 20 || hour < 6) {
    const exposed = completed.has("02-04") || plotFlags.has("tracked_chubby");
    if (!exposed) chf = "listen";
    else chf = hashHour("chubby_n", hour) % 4 === 0 ? "mine" : "listen";
  } else {
    chf = stablePick(hashHour("chubby_d", hour), ["mine", "command"]);
  }
  pos.chubby = facilityAnchor(chf, hashHour("chubby", hour), "chubby");

  if (act === "prologue" || act === "act1") {
    pos.jin = facilityAnchor("command", hashHour("jin_early", hour), "jin");
  } else if (act === "act2") {
    const goCave = caveUnlocked && hour % 3 === 0;
    pos.jin = facilityAnchor(goCave ? "shore_cave" : "command", hashHour("jin_mid", hour), "jin");
  } else if (act === "act3" || act === "finale") {
    const groveOk = completed.has("01-06");
    const roll = hashHour("jin_late", hour) % 5;
    let jf = "command";
    if (roll === 1) jf = "shore_cave";
    else if (groveOk && roll >= 3) jf = "purify_grove";
    pos.jin = facilityAnchor(jf, hashHour("jin_fin", hour), "jin");
  } else {
    pos.jin = facilityAnchor("command", hashHour("jin_def", hour), "jin");
  }

  pos.elizabeth = facilityAnchor("comm", hashHour("elizabeth", hour), "elizabeth");
  pos.klein = facilityAnchor("sunk_lab", 904577, "klein");
  // echo_7（电子界面实体）：当可见时附着在通讯阵列设施附近
  pos.echo_7 = facilityAnchor("comm", hashHour("echo_7", hour), "echo_7");

  return { pos, meta };
}

function stablePick(seed, choices) {
  return choices[seed % choices.length];
}

/** 每帧刷新：在 frame() 内于 pollInput 之后赋值 */
let npcScheduleSnapshot = { pos: {}, meta: {} };

const ECHO_FACILITY_IDS = new Set(["comm", "command", "listen", "lab"]);

function maybeEchoFacilityPing(facilityId) {
  if (!ECHO_FACILITY_IDS.has(facilityId)) return;
  const plotFlags = new Set(latestState?.session?.plot?.flags || []);
  const boost = plotFlags.has("echo_route_hint") || plotFlags.has("echo_aid_accepted");
  const p = boost ? 0.8 : 0.3;
  if (Math.random() >= p) return;
  showToast('回声-7：「……信道不稳。你在听吗？」', 4200);
}

function effectiveNpcs() {
  const srv = latestState?.overworld_npcs;
  const { pos, meta } = npcScheduleSnapshot;
  const base = NPCS.filter((n) => {
    // echo_7 仅当服务端显式返回 visible=true 时纳入地图渲染
    if (n.id === "echo_7") {
      const row = srv?.find((r) => r.id === "echo_7");
      return !!(row && row.visible === true);
    }
    return true;
  });
  const list = !srv?.length
    ? base.map((n) => ({ ...n }))
    : base.filter((n) => srv.find((r) => r.id === n.id)?.visible !== false).map((n) => {
        const r = srv.find((row) => row.id === n.id);
        if (!r) return { ...n };
        const s = (r.surface_line || n.blurb || "").trim();
        const blurb = s.length > 30 ? `${s.slice(0, 30)}…` : s;
        return { ...n, name: r.name || n.name, blurb, surface_line: r.surface_line, hidden_line: r.hidden_line };
      });

  return list.map((n) => {
    const p = pos[n.id];
    const b = npcBodies[n.id];
    const x = b?.x ?? p?.x ?? 2860;
    const y = b?.y ?? p?.y ?? 2120;
    let blurb = n.blurb;
    if (n.id === "dr_lin" && meta.dr_lin_sleep) blurb = `${blurb}（休息中 · 不便深谈）`;
    if (n.id === "karen" && incursionAlertBlurb()) blurb = `${blurb} · 正在响应岸线警报`;
    return { ...n, x, y, blurb };
  });
}

function incursionAlertBlurb() {
  const inc = Number(latestState?.session?.hidden?.INCURSION ?? 25);
  return inc >= 55;
}

/** 出生在主轴交叉口南侧空地：须在 command.core 之外（核心框约 x2912–3292 y1794–2094） */
const PLAYER = { r: ENTITY_R, speed: 340, x: 2860, y: 2120 };

/** 去掉尾部 /，避免出现 //api/... 导致服务端路径与路由不一致（404）
 *  优先级：URL 参数 ?api= > window.__GAME_API_BASE__ > 默认本地地址 */
const API_BASE = (
  new URLSearchParams(location.search).get("api") ||
  (typeof window !== "undefined" && window.__GAME_API_BASE__) ||
  "http://127.0.0.1:8787"
).replace(/\/+$/, "");
{
  const el = document.getElementById("api-url");
  if (el) el.textContent = API_BASE;
}

const objectivesCurrent = document.getElementById("objectives-current");
const objectivesUpcoming = document.getElementById("objectives-upcoming");
const sandboxDock = document.getElementById("sandbox-dock");

/** 用 URL 解析拼接，避免 //、缺斜杠、编码等问题 */
function gameApiUrl(path) {
  const base = (API_BASE || "").trim().replace(/\/+$/, "") ||
    (typeof window !== "undefined" && window.__GAME_API_BASE__) ||
    "http://127.0.0.1:8787";
  const rel = path.startsWith("/") ? path : `/${path}`;
  try {
    return new URL(rel, `${base}/`).href;
  } catch {
    return `${base}${rel}`;
  }
}

const storyBackdrop = document.getElementById("story-backdrop");
const storyTitle = document.getElementById("story-title");
const storySub = document.getElementById("story-sub");
const storyBullets = document.getElementById("story-bullets");
const storyExtras = document.getElementById("story-extras");
const storyChoices = document.getElementById("story-choices");
const storyMeta = document.getElementById("story-meta");
const storySpriteAside = document.querySelector(".story-sprite");
const storySpriteBlock = document.getElementById("story-sprite-block");
const storySpriteLabel = document.getElementById("story-sprite-label");

function setStorySpriteColumnVisible(visible) {
  if (!storySpriteAside) return;
  storySpriteAside.classList.toggle("hidden", !visible);
  storySpriteAside.setAttribute("aria-hidden", visible ? "false" : "true");
}
const storyTextbox = document.getElementById("story-textbox");
const storyPanel = document.getElementById("story-panel");
const storyAiLine = document.getElementById("story-ai-line");
const storyAdvanceHint = document.getElementById("story-advance-hint");
const storyClose = document.getElementById("story-close");

// ── 自由文本对话 UI ────────────────────────────────────────────
let chatInputContainer = null;
let chatInputField = null;
let chatSendButton = null;
let chatEmotionHint = null;
let chatHistoryDirty = false;
let chatActiveNpcId = null;
let chatActiveNarrative = null;
let chatInputPending = false; // 防止重复发送
let chatHistoryMessages = []; // 存储完整历史对话消息
let chatHistoryPanelVisible = false;

/** 递增则丢弃尚未完成的 NPC/源 逐句显示 */
let npcDialogueRevealGen = 0;
/** 取消监听的闭包（含 UI 复原） */
let dialogueRevealCleanup = null;

function cancelNpcDialogueReveal() {
  npcDialogueRevealGen++;
  if (typeof dialogueRevealCleanup === "function") {
    dialogueRevealCleanup();
    dialogueRevealCleanup = null;
  }
}

/**
 * 切成一句一句（含结尾标点）；支持换行分段；无标点时整段为一句。
 */
function segmentNpcDialogue(text) {
  if (!text?.trim()) return [];
  const s = text.replace(/\r\n/g, "\n").trim();
  const raw = s.split(/(?<=[。！？…])\s*|(?<=[；])\s*|\n+/);
  return raw.map((p) => p.trim()).filter(Boolean);
}

/**
 * 按句显示：每句替换上一句；按 Z 或点击对话框（非选项/关闭）进入下一句；最后一句后再按一次结束并 onComplete。
 */
function revealNpcDialogueSequential(el, fullText, opts = {}) {
  const onComplete = opts.onComplete;
  const myGen = ++npcDialogueRevealGen;

  function bindAdvanceUi() {
    if (storyAdvanceHint) storyAdvanceHint.classList.remove("hidden");
    storyTextbox.classList.add("story-textbox--advancing");
    storyAiLine.classList.add("story-ai-line--advance-hint");
  }

  function unbindAdvanceUi() {
    if (storyAdvanceHint) storyAdvanceHint.classList.add("hidden");
    storyTextbox.classList.remove("story-textbox--advancing");
    storyAiLine.classList.remove("story-ai-line--advance-hint");
  }

  el.textContent = "";
  const segments = segmentNpcDialogue(fullText);
  if (segments.length === 0) {
    el.textContent = fullText || "";
    if (onComplete && myGen === npcDialogueRevealGen) onComplete();
    return;
  }

  let idx = 0;
  function showLine() {
    if (myGen !== npcDialogueRevealGen) return;
    el.textContent = segments[idx];
    el.scrollTop = el.scrollHeight;
  }

  function advanceOne() {
    if (myGen !== npcDialogueRevealGen) return;
    idx++;
    if (idx >= segments.length) {
      unbindAdvanceUi();
      document.removeEventListener("keydown", onKeyDown);
      if (storyPanel) storyPanel.removeEventListener("click", onPanelClick);
      dialogueRevealCleanup = null;
      if (onComplete && myGen === npcDialogueRevealGen) onComplete();
      return;
    }
    showLine();
  }

  function onKeyDown(e) {
    if (storyBackdrop.classList.contains("hidden")) return;
    if (e.key === "z" || e.key === "Z") {
      e.preventDefault();
      advanceOne();
    }
  }

  function onPanelClick(e) {
    if (myGen !== npcDialogueRevealGen) return;
    if (e.target.closest(".story-close")) return;
    if (e.target.closest(".story-choices")) return;
    if (e.target.closest("#story-extras")) return;
    if (e.target.closest("#story-meta")) return;
    if (e.target.closest("#chat-history-panel")) return;
    advanceOne();
  }

  dialogueRevealCleanup = () => {
    unbindAdvanceUi();
    document.removeEventListener("keydown", onKeyDown);
    if (storyPanel) storyPanel.removeEventListener("click", onPanelClick);
  };

  bindAdvanceUi();
  document.addEventListener("keydown", onKeyDown);
  if (storyPanel) storyPanel.addEventListener("click", onPanelClick);
  showLine();
}

/** 台词播放中锁定选项；播完解锁（修复播完仍点不了分支的问题） */
function setStoryChoicesLocked(locked) {
  storyChoices.classList.toggle("story-choices--locked", locked);
  for (const b of storyChoices.querySelectorAll("button")) {
    b.disabled = locked;
  }
}

// ── 自由文本对话 UI ────────────────────────────────────────────

/** 创建对话输入区域 */
function setupChatUI(npcId, narrative) {
  teardownChatUI();
  chatActiveNpcId = npcId;
  chatActiveNarrative = narrative;
  chatHistoryMessages = []; // 新对话开始清空历史

  const wrap = document.createElement("div");
  wrap.id = "story-chat-input";
  wrap.style.cssText = "margin-top:12px;display:flex;flex-direction:column;gap:6px;";

  // 情绪提示行
  const hint = document.createElement("div");
  hint.id = "story-chat-emotion";
  hint.style.cssText = "font-size:11px;color:#8e9baf;min-height:1.2em;";
  hint.textContent = "";
  wrap.appendChild(hint);
  chatEmotionHint = hint;

  // 输入行
  const row = document.createElement("div");
  row.style.cssText = "display:flex;gap:6px;";

  const inp = document.createElement("input");
  inp.type = "text";
  inp.id = "story-chat-field";
  inp.placeholder = "输入你想说的话…（Enter 发送）";
  inp.style.cssText =
    "flex:1;background:#141e2b;border:1px solid #2a3a4f;color:#c8d6e5;padding:8px 10px;" +
    "font-family:inherit;font-size:14px;border-radius:4px;";
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const text = inp.value.trim();
      if (text) sendChatMessage(text);
    }
  });
  row.appendChild(inp);
  chatInputField = inp;

  const btn = document.createElement("button");
  btn.type = "button";
  btn.id = "story-chat-send";
  btn.textContent = "发送";
  btn.style.cssText =
    "background:#2a4a6f;border:1px solid #3a5a7f;color:#c8d6e5;padding:8px 14px;" +
    "cursor:pointer;font-family:inherit;font-size:14px;border-radius:4px;white-space:nowrap;";
  btn.addEventListener("click", () => {
    const text = inp.value.trim();
    if (text) sendChatMessage(text);
  });
  row.appendChild(btn);
  chatSendButton = btn;

  // 历史对话按钮
  const historyBtn = document.createElement("button");
  historyBtn.type = "button";
  historyBtn.id = "story-chat-history";
  historyBtn.textContent = "历史";
  historyBtn.style.cssText =
    "background:#1e2e3f;border:1px solid #2a3a5f;color:#8ea4ba;padding:8px 12px;" +
    "cursor:pointer;font-family:inherit;font-size:14px;border-radius:4px;white-space:nowrap;";
  historyBtn.addEventListener("click", toggleChatHistory);
  row.appendChild(historyBtn);

  wrap.appendChild(row);
  chatInputContainer = wrap;
  storyExtras.appendChild(wrap);

  // 初始聚焦
  setTimeout(() => inp.focus(), 200);
}

/** 清理对话输入区域 */
function teardownChatUI() {
  chatInputPending = false;
  if (chatInputContainer && chatInputContainer.parentNode) {
    chatInputContainer.remove();
  }
  chatInputContainer = null;
  chatInputField = null;
  chatSendButton = null;
  chatEmotionHint = null;
  chatActiveNpcId = null;
  chatActiveNarrative = null;
  chatHistoryMessages = [];
  closeChatHistory();
  // 清理浮现的选项
  const unveiled = storyExtras.querySelectorAll(".chat-unveil-choice");
  unveiled.forEach((el) => el.remove());
}

// ── 自由对话轮次约束常量（与后端 CHOICE_UNVEIL_TURNS 保持一致） ──
const CHAT_UNVEIL_TURNS = 5;

/** 更新情绪提示（仅显示偏离/情绪信息，不做轮次警告） */
function updateChatEmotion(data) {
  if (!chatEmotionHint) return;
  const parts = [];
  const offTopic = data.off_topic_count || 0;
  if (offTopic >= 3) {
    parts.push("⚠ NPC 对你的频繁偏离感到不耐烦");
  } else if (offTopic >= 2) {
    parts.push("• 话题偏离 — 注意对话方向");
  } else if (offTopic >= 1) {
    parts.push("• NPC 希望集中精神");
  }
  const shift = data.emotional_shift;
  if (shift && (shift.trust !== 0 || shift.affinity !== 0 || shift.fear !== 0)) {
    const deltas = [];
    if (shift.trust < 0) deltas.push(`信任${shift.trust > 0 ? "+" : ""}${shift.trust}`);
    if (shift.affinity < 0) deltas.push(`好感${shift.affinity > 0 ? "+" : ""}${shift.affinity}`);
    if (shift.fear > 0) deltas.push(`警惕+${shift.fear}`);
    if (deltas.length) parts.push("情绪：" + deltas.join(" "));
  }

  chatEmotionHint.textContent = parts.join("  ·  ") || "";
  if (offTopic >= 2) {
    chatEmotionHint.style.color = "#d4a04a";
  } else if (offTopic >= 1) {
    chatEmotionHint.style.color = "#a0b0c0";
  } else {
    chatEmotionHint.style.color = "#8e9baf";
  }
}

/** 检测文本中是否包含告别意图关键词 */
function detectFarewell(text) {
  if (!text) return false;
  const patterns = [
    "再见", "拜拜", "告辞", "告别", "后会有期", "下次见",
    "走了", "先走了", "该走了", "回去了", "先回去", "我走了",
    "不打扰了", "你忙吧", "你去忙", "去忙吧",
    "我先撤", "撤了", "回头见", "就此别过",
    "再会", "失陪", "先这样", "就这样吧",
    "该回去", "回去工作", "回去了",
    "下次再聊", "晚点再聊", "有空再聊",
    "我们走", "该出发", "该行动", "照顾好自己",
    "保重", "多加小心", "路上小心",
  ];
  const lower = text.toLowerCase();
  // 也匹配英文 farewell
  const enPatterns = ["goodbye", "bye", "farewell", "see you", "take care"];
  return patterns.some((p) => text.includes(p)) || enPatterns.some((p) => lower.includes(p));
}

/** 发送对话消息 */
async function sendChatMessage(playerText) {
  if (!chatActiveNpcId || chatInputPending) return;
  chatInputPending = true;

  // 隐藏对话框（NPC 说话时不显示输入区域）
  if (chatInputContainer) chatInputContainer.style.display = "none";

  // 显示玩家消息
  addChatBubble("player", playerText);
  storyAiLine.textContent = "…";

  let conversationWasClosed = false;

  try {
    const data = await fetchJSON(gameApiUrl("/api/npc/chat"), {
      method: "POST",
      body: JSON.stringify({
        npc_id: chatActiveNpcId,
        player_text: playerText,
        action: "send",
      }),
    });
    latestState = data;
    // 自由对话后立即保存到 localStorage
    persistSessionToLocalStorage();

    // ── 双向告别兜底检测：即使 AI 没返回 resolved/close_signal，若双方都说了告别语也自动关闭 ──
    const playerFarewell = detectFarewell(playerText);
    const npcFarewell = detectFarewell(data.npc_text || "");
    const mutualFarewell = playerFarewell && npcFarewell && !data.conversation_closed && !data.story_resolved;
    if (mutualFarewell) {
      data.conversation_closed = true; // 强制标记为关闭
    }

    // ── NPC 主动结束对话：立即禁用输入，不允许再发送消息 ──
    if (data.conversation_closed) {
      conversationWasClosed = true;
      if (chatInputField) {
        chatInputField.disabled = true;
        chatInputField.placeholder = "对话已结束…";
      }
      if (chatSendButton) chatSendButton.disabled = true;
    }

    // 显示 NPC 回复
    cancelNpcDialogueReveal();
    const npcText = data.npc_text || "";
    // 将 NPC 回复存入历史记录
    if (npcText) {
      chatHistoryMessages.push({ role: "npc", text: npcText, time: Date.now() });
    }
    revealNpcDialogueSequential(storyAiLine, npcText, {
      onComplete: () => {
        // 检查是否已收束到选项
        if (data.story_resolved) {
          handleChatResolved(data.story_resolved, data);
          return;
        }
        // ── NPC 主动结束对话处理 ──
        if (data.conversation_closed) {
          if (mutualFarewell) {
            // 双向告别：揭示选项让玩家推进剧情，而非直接关闭面板
            if (chatInputContainer) {
              chatInputContainer.style.display = "none"; // 永久隐藏输入区域
            }
            // 直接揭示剧情选项（不依赖轮次阈值），让玩家选择推进故事
            unveilStoryChoices(data);
          } else {
            // AI 主动结束（resolved/close_signal）：自动关闭面板
            setTimeout(() => closeStoryUI(), 1800);
          }
          return;
        }
        // ── NPC 说完，恢复对话框 ──
        if (chatInputContainer) {
          chatInputContainer.style.display = "";
          if (chatInputField) {
            chatInputField.value = "";
            chatInputField.disabled = false;
            setTimeout(() => chatInputField.focus(), 100);
          }
          if (chatSendButton) chatSendButton.disabled = false;
        }
        chatInputPending = false;
      },
    });

    // 更新情绪提示
    updateChatEmotion(data);

    // ── 选项自然浮现：到达阈值后，在对话界面显示剧情选项 ──
    if (data.unveil_choices) {
      unveilStoryChoices(data);
    }

    // 如果 AI 返回 suggested_choices，显示为快捷按钮
    if (data.suggested_choices && data.suggested_choices.length > 0 && !data.story_resolved) {
      addChatQuickChoices(data.suggested_choices);
    }
  } catch (e) {
    storyAiLine.textContent = "（通信中断，请稍后再试。）";
    // 发送失败时恢复对话框
    if (chatInputContainer) {
      chatInputContainer.style.display = "";
      if (chatInputField) {
        chatInputField.disabled = false;
        setTimeout(() => chatInputField.focus(), 100);
      }
      if (chatSendButton) chatSendButton.disabled = false;
    }
    chatInputPending = false;
  }
  renderMgmtResourcesHud(latestState?.session);
}

/** 当对话收束到选项时 */
function handleChatResolved(choiceId, data) {
  // 清理聊天 UI
  teardownChatUI();
  // 自动提交选项
  postChoice(choiceId);
  // 如果返回了 suggested_choices，也用一下其中第一条的文案效果
  if (data.suggested_choices && data.suggested_choices.length) {
    showToast(`${data.suggested_choices[0]}`, 3000);
  }
}

/** 添加玩家/NPC 对话气泡（在 story-extras 中） */
function addChatBubble(role, text) {
  // 先清理已有气泡（保留最近 8 条）
  const existing = storyExtras.querySelectorAll(".chat-bubble");
  while (existing.length >= 8) {
    existing[0].remove();
  }
  const div = document.createElement("div");
  div.className = `chat-bubble chat-bubble--${role}`;
  div.style.cssText =
    `margin:4px 0;padding:6px 10px;border-radius:6px;font-size:13px;line-height:1.5;` +
    (role === "player"
      ? "background:#1a2a3f;color:#a0c4e8;align-self:flex-end;text-align:right;border:1px solid #2a3a5f;"
      : "background:#1a222f;color:#c8d6e5;align-self:flex-start;text-align:left;border:1px solid #2a3648;");
  div.textContent = text;
  // 插入到 chat input 前面
  if (chatInputContainer) {
    storyExtras.insertBefore(div, chatInputContainer);
  } else {
    storyExtras.appendChild(div);
  }
  // 存储到历史记录
  chatHistoryMessages.push({ role, text, time: Date.now() });
}

// ── 历史对话面板 ────────────────────────────────────────────

/** 切换历史对话面板的显示/隐藏 */
function toggleChatHistory() {
  if (chatHistoryPanelVisible) {
    closeChatHistory();
  } else {
    showChatHistory();
  }
}

/** 创建并显示历史对话面板 */
function showChatHistory() {
  // 如果已存在则先关闭
  const existing = document.getElementById("chat-history-panel");
  if (existing) {
    existing.remove();
    chatHistoryPanelVisible = false;
  }

  const panel = document.createElement("div");
  panel.id = "chat-history-panel";
  panel.style.cssText =
    "position:absolute;top:3px;left:0;right:0;bottom:0;z-index:60;" +
    "background:rgba(8,13,22,0.97);display:flex;flex-direction:column;" +
    "border-radius:0 0 12px 12px;overflow:hidden;";

  // 标题栏（关闭按钮在左侧，避免与 story-close 重叠）
  const header = document.createElement("div");
  header.style.cssText =
    "display:flex;align-items:center;gap:10px;" +
    "padding:10px 14px;border-bottom:1px solid rgba(100,180,200,0.15);flex-shrink:0;";

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.textContent = "✕ 关闭";
  closeBtn.style.cssText =
    "background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);" +
    "color:#8899aa;font-size:13px;cursor:pointer;padding:4px 10px;border-radius:4px;flex-shrink:0;" +
    "font-family:inherit;";
  closeBtn.addEventListener("click", closeChatHistory);
  header.appendChild(closeBtn);

  const title = document.createElement("span");
  title.textContent = "对话历史";
  title.style.cssText = "font-size:14px;font-weight:600;color:#b8d4e0;flex:1;";
  header.appendChild(title);

  panel.appendChild(header);

  // 消息滚动区
  const scroll = document.createElement("div");
  scroll.style.cssText =
    "flex:1;overflow-y:auto;overflow-x:hidden;padding:12px 14px;" +
    "display:flex;flex-direction:column;gap:8px;";

  if (chatHistoryMessages.length === 0) {
    const empty = document.createElement("div");
    empty.textContent = "暂无对话记录";
    empty.style.cssText =
      "color:#5a7a8a;font-size:13px;text-align:center;padding:40px 0;";
    scroll.appendChild(empty);
  } else {
    for (const msg of chatHistoryMessages) {
      const bubble = document.createElement("div");
      bubble.style.cssText =
        "padding:8px 12px;border-radius:6px;font-size:13px;line-height:1.5;max-width:90%;" +
        (msg.role === "player"
          ? "background:#1a2a3f;color:#a0c4e8;align-self:flex-end;text-align:right;border:1px solid #2a3a5f;margin-left:auto;"
          : "background:#1a222f;color:#c8d6e5;align-self:flex-start;text-align:left;border:1px solid #2a3648;");
      bubble.textContent = msg.text;
      scroll.appendChild(bubble);
    }
  }

  panel.appendChild(scroll);

  // 底部提示
  const footer = document.createElement("div");
  footer.style.cssText =
    "padding:6px 14px;font-size:11px;color:#5a6a7a;text-align:center;" +
    "border-top:1px solid rgba(100,180,200,0.08);flex-shrink:0;";
  footer.textContent = `共 ${chatHistoryMessages.length} 条消息`;
  panel.appendChild(footer);

  // 挂到 story-panel 层级（z-index: 60 > story-close 的 30，确保完全覆盖）
  storyPanel.appendChild(panel);
  chatHistoryPanelVisible = true;

  // 滚动到底部
  scroll.scrollTop = scroll.scrollHeight;
}

/** 关闭历史对话面板 */
function closeChatHistory() {
  const panel = document.getElementById("chat-history-panel");
  if (panel) panel.remove();
  chatHistoryPanelVisible = false;
}

/** 添加 AI 返回的快捷选项按钮 */
function addChatQuickChoices(choices) {
  // 清理旧快捷选项
  const existing = storyExtras.querySelectorAll(".chat-quick-choice");
  existing.forEach((el) => el.remove());

  const wrap = document.createElement("div");
  wrap.className = "chat-quick-choice";
  wrap.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;margin:6px 0;";

  for (const ch of choices.slice(0, 3)) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = ch;
    b.style.cssText =
      "background:#1a2e3f;border:1px solid #3a5a7f;color:#a0c4d0;padding:4px 10px;" +
      "cursor:pointer;font-family:inherit;font-size:12px;border-radius:4px;";
    b.addEventListener("click", () => {
      if (chatInputField) {
        chatInputField.value = ch;
        sendChatMessage(ch);
      }
    });
    wrap.appendChild(b);
  }
  if (chatInputContainer) {
    storyExtras.insertBefore(wrap, chatInputContainer);
  } else {
    storyExtras.appendChild(wrap);
  }
}

/**
 * 选项自然浮现：当对话进行到一定轮次后，将剧情节点的正式选项以自然方式显示在对话界面中。
 * 玩家可以随时点击选项推进剧情，也可以继续自由对话。
 */
function unveilStoryChoices(data) {
  // 避免重复渲染
  const existing = storyExtras.querySelectorAll(".chat-unveil-choice");
  existing.forEach((el) => el.remove());

  // 从 state payload 中获取当前 narrative
  const nar = data.narrative || chatActiveNarrative;
  if (!nar || !nar.choices || nar.choices.length === 0) return;

  const wrap = document.createElement("div");
  wrap.className = "chat-unveil-choice";
  wrap.style.cssText =
    "margin:10px 0 6px;padding:8px 10px;background:#141f2b;" +
    "border:1px solid #2a3a4f;border-radius:6px;";

  for (const c of nar.choices) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = c.label_zh;
    b.style.cssText =
      "display:block;width:100%;text-align:left;margin:3px 0;padding:7px 10px;" +
      "background:#1a2e3f;border:1px solid #3a5a7f;color:#a0c4d0;" +
      "cursor:pointer;font-family:inherit;font-size:13px;border-radius:4px;";
    b.addEventListener("mouseenter", () => {
      b.style.background = "#243a4f";
      b.style.borderColor = "#5a8abf";
      b.style.color = "#c8e0f0";
    });
    b.addEventListener("mouseleave", () => {
      b.style.background = "#1a2e3f";
      b.style.borderColor = "#3a5a7f";
      b.style.color = "#a0c4d0";
    });
    b.addEventListener("click", () => {
      handleChatResolved(c.id, data);
    });
    wrap.appendChild(b);
  }

  if (chatInputContainer) {
    storyExtras.insertBefore(wrap, chatInputContainer);
  } else {
    storyExtras.appendChild(wrap);
  }
}

const storyBody = document.getElementById("story-body");

/** 左侧立绘占位色（NPC） */
const PORTRAIT_NPC = {
  karen: "#4a6fa5",
  dr_lin: "#5a9078",
  chubby: "#b8924a",
  jin: "#5a9e6e",
  echo_7: "#7a5cb8",
  klein: "#5c5e72",
  elizabeth: "#944a62",
  source: "#4a7a9e",
};
/** 设施占位色 */
const PORTRAIT_FACILITY = {
  helipad: "#6a7a90",
  command: "#4e5d74",
  comm: "#4a6b8c",
  mine: "#8a6a4a",
  lab: "#5a8a7a",
  defense: "#7a5a4a",
  listen: "#4a7a8a",
  sunk_lab: "#5c5e68",
  mine_ruins: "#6a6050",
  echo_site: "#6a4a8a",
  parliament_ruin: "#6a5048",
  shore_cave: "#4a6878",
  purify_grove: "#4a7a55",
};

let storyPortraitImgEl = null;

function ensureStoryPortraitImg() {
  if (!storyPortraitImgEl) {
    storyPortraitImgEl = document.createElement("img");
    storyPortraitImgEl.className = "story-portrait-img";
    storyPortraitImgEl.alt = "";
    storyPortraitImgEl.decoding = "async";
    storySpriteBlock.prepend(storyPortraitImgEl);
  }
  return storyPortraitImgEl;
}

/** @param {"npc"|"facility"} kind */
function setStoryPortrait(kind, kindId, labelText) {
  storyPortraitKind = kind;
  storyPortraitId = kindId;
  storyPortraitLabel = labelText || "";
  storySpriteLabel.textContent = storyPortraitLabel;
  const fallback = PORTRAIT_NPC[kindId] || PORTRAIT_FACILITY[kindId] || "#3d4f66";
  const imgEl = ensureStoryPortraitImg();
  let src = "";
  if (kind === "npc") {
    const path = PORTRAIT_SPRITE_PATH[kindId];
    // 按需加载立绘
    if (path && !portraitSpriteImages.has(kindId)) loadPortraitSprite(kindId);
    const cached = portraitSpriteImages.get(kindId);
    if (path && cached?.complete && cached.naturalWidth > 0) {
      src = new URL(path, tileAssetBaseUrl()).href;
    }
  } else if (kind === "facility") {
    // 按需加载设施贴图
    if (!facilitySpriteImages.has(kindId)) loadFacilitySprite(kindId);
    const cached = facilitySpriteImages.get(kindId);
    const path = cached ? `./assets/facilities/${kindId}.png` : "";
    if (path && cached?.complete && cached.naturalWidth > 0) {
      src = new URL(path, tileAssetBaseUrl()).href;
    }
  }
  if (src) {
    storySpriteBlock.style.background = "rgba(12, 18, 28, 0.92)";
    imgEl.src = src;
    imgEl.hidden = false;
    storySpriteLabel.textContent = storyPortraitLabel.replace(/\n（[^）]+）$/, "");
  } else {
    imgEl.hidden = true;
    imgEl.removeAttribute("src");
    storySpriteBlock.style.background = fallback;
  }
}

function setPortraitPlaceholder(kindId, labelText) {
  const kind = PORTRAIT_NPC[kindId] ? "npc" : "facility";
  setStoryPortrait(kind, kindId, labelText);
}

function syncStoryChoicesLayout() {
  storyTextbox.classList.toggle("story-textbox--choices", storyChoices.children.length > 0);
}

async function fetchJSON(url, options = {}) {
  /** GET/HEAD 不写 Content-Type，避免浏览器发 CORS 预检；（旧版服务端 do_OPTIONS 曾缺 send_response 时预检会失败）。 */
  const method = String(options.method || "GET").toUpperCase();
  const headers =
    method === "GET" || method === "HEAD"
      ? { ...(options.headers || {}) }
      : { "Content-Type": "application/json", ...(options.headers || {}) };
  let r;
  try {
    r = await fetch(url, {
      ...options,
      headers,
      // 不发送 Referer 头，避免某些 PaaS 边缘代理（如 Railway）因跨域 Referer 返回 403
      referrerPolicy: "no-referrer",
    });
  } catch (e) {
    const msg = e?.message || String(e);
    const isNetErr = msg.includes("Failed to fetch") || msg.includes("NetworkError");
    throw new Error(
      isNetErr
        ? `无法连接游戏服务器 (${API_BASE}) · 请确认后端 API 已启动；或通过地址栏 ?api=你的服务器地址 指定接口`
        : msg,
    );
  }
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(text || r.statusText);
  }
  if (!r.ok) {
    let hint = data.reason_zh || data.error || text || r.statusText;
    if (!data.reason_zh && data.normalized_path != null) {
      hint += ` | normalized_path=${data.normalized_path} raw_path=${data.raw_path || ""}`;
    }
    if (!data.reason_zh && Array.isArray(data.post_routes) && data.post_routes.length) {
      hint += ` | post_routes=${data.post_routes.join(",")}`;
    }
    // 403 附加提示：通常是边缘代理/安全策略拦截
    if (r.status === 403) {
      hint += ` | 提示：403 通常由部署平台（Railway/Netlify）的边缘安全策略导致，请检查平台日志和 CORS 设置`;
    }
    throw new Error(`${hint}（${r.status} · ${url}）`);
  }
  return data;
}

/** 调时：优先专用路由；若服务端仍为旧版（404）则回退到 /api/narrative/action。 */
async function postAdvanceClockMinutes(minutes) {
  const payload = JSON.stringify({ minutes });
  try {
    return await fetchJSON(gameApiUrl("/api/sim/advance_clock"), {
      method: "POST",
      body: payload,
    });
  } catch (e) {
    const m = String(e.message || e);
    if (/404/.test(m) && (m.includes("advance_clock") || m.includes("not_found"))) {
      return await fetchJSON(gameApiUrl("/api/narrative/action"), {
        method: "POST",
        body: JSON.stringify({ kind: "advance_clock", minutes }),
      });
    }
    throw e;
  }
}

/** 购灯：优先专用路由；旧版 API 可经 narrative/action 命中（须已更新 web_api）。 */
async function postPurchaseFloodlight() {
  try {
    return await fetchJSON(gameApiUrl("/api/sim/purchase_floodlight"), {
      method: "POST",
      body: "{}",
    });
  } catch (e) {
    const m = String(e.message || e);
    if (/404/.test(m) && (m.includes("purchase_floodlight") || m.includes("not_found"))) {
      return await fetchJSON(gameApiUrl("/api/narrative/action"), {
        method: "POST",
        body: JSON.stringify({ kind: "purchase_floodlight" }),
      });
    }
    throw e;
  }
}

/** 最近一次 `/api/state` 拉取失败原因（横幅展示，便于分辨未启动/CORS/HTML 误判等） */
let explorerSyncLastError = "";

function escBannerText(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** 剧情 API 离线提示（仅用静态服务器打开 explorer 时需要另起 python -m game） */
function syncExplorerApiBanner(online) {
  let el = document.getElementById("explorer-api-banner");
  if (!el) {
    el = document.createElement("div");
    el.id = "explorer-api-banner";
    el.className = "explorer-api-banner hidden";
    el.setAttribute("role", "alert");
    document.body.appendChild(el);
  }
  if (online) {
    explorerSyncLastError = "";
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  const esc = escBannerText(API_BASE);
  const errLine = explorerSyncLastError
    ? `<p class="explorer-api-banner__detail">本次错误：<span class="explorer-api-banner__err">${escBannerText(explorerSyncLastError)}</span></p>`
    : "";
  el.innerHTML = `<strong class="explorer-api-banner__title">无法同步剧情状态</strong>
    <p class="explorer-api-banner__body">当前请求的游戏 API 地址为 <kbd>${esc}</kbd>。
    ${esc.includes("127.0.0.1") || esc.includes("localhost")
      ? `请在<strong>另一个终端</strong>运行 <kbd>python -m game</kbd>，然后刷新本页。`
      : `请确认远程服务器地址正确且已启动。可通过地址栏参数临时切换：<kbd>?api=你的API地址</kbd>`}
    端口不一致时用：<kbd>?api=http://地址:端口</kbd></p>${errLine}`;
}

function plotHasFlag(session, name) {
  const flags = session?.plot?.flags;
  return Array.isArray(flags) && flags.includes(name);
}

let lastStoryInteract = null;

async function refreshOpenStoryPanel() {
  try {
    if (lastStoryInteract && !storyBackdrop.classList.contains("hidden")) {
      const st = await fetchJSON(gameApiUrl("/api/state"));
      latestState = st;
      renderMgmtResourcesHud(st.session);
      renderMgmtLogStrip(st.management_recent);
      npcScheduleSnapshot = scheduledNpcWorldPositions(st);
      syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
      if (lastStoryInteract.kind === "npc") {
        const chk = await fetchJSON(gameApiUrl("/api/npc/check"), {
          method: "POST",
          body: JSON.stringify({ npc_id: lastStoryInteract.id }),
        });
        renderNpcPanel(st, chk, lastStoryInteract, { skipOpening: true });
      } else {
        const chk = await fetchJSON(gameApiUrl("/api/facility/check"), {
          method: "POST",
          body: JSON.stringify({ facility_id: lastStoryInteract.id }),
        });
        renderFacilityPanel(st, chk, lastStoryInteract);
      }
      syncStoryChoicesLayout();
    }
  } catch (e) {
    showErrorToast(e);
  }
  await refreshTopBar();
}

let workshopMapEl = null;
let workshopUiSnap = null;
let workshopBuildType = null;
let workshopMoveFrom = null;
let workshopSelected = null;
let workshopPollTimer = null;
let workshopEntryFrom = "west_shaft";
let workshopHoverCell = null;

const WORKSHOP_DEFAULT_STOP_CAPS = {
  ore: 50,
  alloy: 80,
  components: 40,
  parts: 100,
  medical_pack: 30,
};

const WORKSHOP_RES_ZH = {
  ore: "矿石",
  alloy: "合金",
  components: "电子元件",
  source_crystal: "源能结晶",
  parts: "零件",
  medical_pack: "医疗包",
};

/** 建造/升级消耗的基地资源中文名（与 hidden_state.BaseResources 一致） */
const WORKSHOP_BASE_RES_ZH = {
  energy: "能源",
  parts: "零件",
  food: "食物",
  medical: "医疗",
  intel: "情报",
};

/** 乐观 UI 模块：工坊操作先本地修改 + 即时渲染，再后台同步服务器。
 *  出错时自动回滚到操作前备份。 */
const OptimisticWorkshop = {
  _backup: null,

  /** 深拷贝当前 snapshot 作为回滚备份 */
  save() {
    this._backup = JSON.parse(JSON.stringify(workshopUiSnap));
  },

  /** 回滚到备份，清空备份 */
  rollback() {
    if (this._backup) {
      workshopUiSnap = this._backup;
      this._backup = null;
    }
  },

  /** 丢弃备份（成功时调用） */
  clear() {
    this._backup = null;
  },

  // ─── 网格 Cell 工具 ───

  /** 清空某个 anchor 下所有格子 */
  _clearCells(snap, ax, ay) {
    const grid = snap?.grid;
    if (!grid) return;
    for (let gy = 0; gy < grid.length; gy++) {
      const row = grid[gy];
      if (!row) continue;
      for (let gx = 0; gx < row.length; gx++) {
        const c = row[gx];
        if (c && c.anchor_x === ax && c.anchor_y === ay) row[gx] = null;
      }
    }
  },

  /** 按设备模板填充 w×h 格子 */
  _fillCells(snap, entry, ax, ay) {
    const grid = snap?.grid;
    if (!grid) return;
    const w = entry.w || 1;
    const h = entry.h || 1;
    for (let dy = 0; dy < h; dy++) {
      const row = grid[ay + dy];
      if (!row) continue;
      for (let dx = 0; dx < w; dx++) {
        const gx = ax + dx;
        if (gx >= row.length) continue;
        row[gx] = {
          is_anchor: dx === 0 && dy === 0,
          anchor_x: ax,
          anchor_y: ay,
          type: entry.type,
          label_zh: entry.label_zh,
          level: 1,
          active: true,
          enabled: true,
          assigned_npc: null,
          recipe: null,
          progress_pct: 0,
          status_zh: "运行中",
          status_code: "running",
        };
      }
    }
  },

  /** 创建默认设备对象 */
  _newDevice(entry, ax, ay) {
    return {
      type: entry.type,
      label_zh: entry.label_zh,
      anchor_x: ax,
      anchor_y: ay,
      w: entry.w || 1,
      h: entry.h || 1,
      level: 1,
      enabled: true,
      active: true,
      assigned_npc: null,
      npc_id: null,
      recipe: null,
      recipe_zh: null,
      progress_pct: 0,
      status_zh: "运行中",
      status_code: "running",
      can_upgrade: false,
    };
  },

  /** 查找设备对象 */
  _findDev(snap, ax, ay) {
    return snap?.devices?.find((d) => d.anchor_x === ax && d.anchor_y === ay) || null;
  },

  /** 同步更新格子里的设备属性 (anchor cells) */
  _patchGridCells(snap, ax, ay, patch) {
    const grid = snap?.grid;
    if (!grid) return;
    for (let gy = 0; gy < grid.length; gy++) {
      const row = grid[gy];
      if (!row) continue;
      for (let gx = 0; gx < row.length; gx++) {
        const c = row[gx];
        if (c && c.anchor_x === ax && c.anchor_y === ay) {
          Object.assign(c, patch);
        }
      }
    }
  },

  // ─── 操作：建造 ───
  build(snap, x, y, deviceType) {
    const entry = workshopCatalogEntry(snap, deviceType);
    if (!entry || !snap) return;
    this._fillCells(snap, entry, x, y);
    if (!snap.devices) snap.devices = [];
    snap.devices.push(this._newDevice(entry, x, y));
  },

  // ─── 操作：拆除 ───
  demolish(snap, x, y) {
    if (!snap) return;
    this._clearCells(snap, x, y);
    if (snap.devices) snap.devices = snap.devices.filter((d) => d.anchor_x !== x || d.anchor_y !== y);
  },

  // ─── 操作：移动 ───
  move(snap, fromX, fromY, toX, toY) {
    if (!snap) return;
    const dev = this._findDev(snap, fromX, fromY);
    if (!dev) return;
    // 收集旧格子数据用于重新填充
    const oldCells = [];
    const grid = snap.grid;
    if (grid) {
      for (let gy = 0; gy < grid.length; gy++) {
        const row = grid[gy];
        if (!row) continue;
        for (let gx = 0; gx < row.length; gx++) {
          const c = row[gx];
          if (c && c.anchor_x === fromX && c.anchor_y === fromY) {
            oldCells.push({ dx: gx - fromX, dy: gy - fromY, cell: { ...c } });
          }
        }
      }
    }
    this._clearCells(snap, fromX, fromY);
    for (const oc of oldCells) {
      const nx = toX + oc.dx;
      const ny = toY + oc.dy;
      const row = snap.grid?.[ny];
      if (row && nx < row.length && nx >= 0) {
        row[nx] = { ...oc.cell, anchor_x: toX, anchor_y: toY };
      }
    }
    dev.anchor_x = toX;
    dev.anchor_y = toY;
  },

  // ─── 操作：启用/暂停 ───
  toggle(snap, x, y) {
    const dev = this._findDev(snap, x, y);
    if (!dev) return;
    dev.enabled = !dev.enabled;
    dev.status_zh = dev.enabled ? "运行中" : "已暂停";
    dev.status_code = dev.enabled ? "running" : "off";
    this._patchGridCells(snap, x, y, {
      enabled: dev.enabled,
      status_zh: dev.status_zh,
      status_code: dev.status_code,
    });
  },

  // ─── 操作：分配 NPC ───
  assignNpc(snap, x, y, npcId) {
    const dev = this._findDev(snap, x, y);
    if (!dev) return;
    const npc = (snap.npc_roster || []).concat(snap.npc_fatigue || []).find((n) => n.id === npcId) || null;
    dev.npc_id = npcId || null;
    dev.npc_label_zh = npc?.label_zh || null;
    dev.npc_efficiency_pct = npcId ? 100 : null;
    this._patchGridCells(snap, x, y, {
      npc_id: dev.npc_id,
      npc_label_zh: dev.npc_label_zh,
    });
  },

  // ─── 操作：切换配方 ───
  setRecipe(snap, x, y, recipe) {
    const dev = this._findDev(snap, x, y);
    if (!dev || dev.type !== "printer") return;
    dev.recipe = recipe;
    dev.recipe_zh = workshopPrinterRecipeLabel(recipe);
  },

  // ─── 操作：升级 ───
  upgrade(snap, x, y) {
    const dev = this._findDev(snap, x, y);
    if (!dev) return;
    dev.level = (dev.level || 1) + 1;
    this._patchGridCells(snap, x, y, { level: dev.level });
  },

  // ─── 操作：委任 ───
  delegate(snap, enabled) {
    if (!snap) return;
    snap.delegation_on = !!enabled;
    snap.delegation_action_zh = enabled ? "委任自动分配已开启" : "委任已关闭";
  },

  // ─── 操作：导入源矿 ───
  importOre(snap, amount) {
    if (!snap) return;
    snap.source_ore_buffer = (snap.source_ore_buffer || 0) + (amount || 1);
  },

  // ─── 操作：设置产能上限 ───
  setCaps(snap, caps, enabled) {
    if (!snap) return;
    if (caps) snap.stop_caps = { ...snap.stop_caps, ...caps };
    if (enabled != null) snap.stop_caps_enabled = !!enabled;
  },

  // ─── 操作：NPC 休息 ───
  restNpc(snap, npcId) {
    if (!snap) return;
    // 取消所有设备上该 NPC 的分配
    if (snap.devices) {
      for (const dev of snap.devices) {
        if (dev.npc_id === npcId) {
          dev.npc_id = null;
          dev.npc_label_zh = null;
          dev.npc_efficiency_pct = null;
        }
      }
    }
    // 清除疲劳
    if (snap.npc_fatigue) {
      const entry = snap.npc_fatigue.find((r) => r.id === npcId);
      if (entry) {
        entry.needs_rest = false;
        entry.fatigue_pct = 0;
      }
    }
    // 更新格子
    const grid = snap.grid;
    if (grid) {
      for (let gy = 0; gy < grid.length; gy++) {
        const row = grid[gy];
        if (!row) continue;
        for (let gx = 0; gx < row.length; gx++) {
          const c = row[gx];
          if (c && c.npc_id === npcId) {
            c.npc_id = null;
            c.npc_label_zh = null;
          }
        }
      }
    }
    snap.delegation_on = false;
    snap.delegation_action_zh = "NPC 休息中，委任已暂停";
  },
};


function explorerIconHref(key) {
  const rel = EXPLORER_ICON_PATH[key];
  if (!rel) return "";
  return new URL(rel, tileAssetBaseUrl()).href;
}

function explorerIconReady(key) {
  const img = explorerIconImages.get(key);
  return !!(img?.complete && img.naturalWidth > 0);
}

function startExplorerIconLoad() {
  const entries = Object.entries(EXPLORER_ICON_PATH);
  // 分批加载，每批 4 个，间隔 80ms，避免同时抢占所有连接池
  const BATCH = 4;
  const DELAY = 80;
  for (let i = 0; i < entries.length; i++) {
    const [key, rel] = entries[i];
    const batchOffset = Math.floor(i / BATCH) * DELAY;
    setTimeout(() => {
      const img = new Image();
      explorerIconImages.set(key, img);
      wireExplorerAsset(img, rel, `icon_${key}`, () => {
        initObjectivesTabIcons();
        const strip = document.getElementById("resource-strip");
        if (strip && latestState?.session) renderMgmtResourcesHud(latestState.session);
      });
    }, batchOffset);
  }
}

function workshopDeviceIconMarkup(type) {
  if (explorerIconReady(type)) {
    const href = explorerIconHref(type);
    return `<img class="workshop-cell-icon workshop-cell-icon--img" src="${href}" alt="" decoding="async" />`;
  }
  return `<span class="workshop-cell-icon">${WORKSHOP_DEVICE_ICON[type] || "?"}</span>`;
}

function explorerIconImgHtml(key, className, size = 20) {
  if (!explorerIconReady(key)) return "";
  const href = explorerIconHref(key);
  return `<img class="${className}" src="${href}" width="${size}" height="${size}" alt="" decoding="async" />`;
}

function initObjectivesTabIcons() {
  document.querySelectorAll(".objectives-tab").forEach((btn) => {
    const tab = btn.dataset.tab;
    const iconKey = OBJECTIVES_TAB_ICON_KEY[tab];
    if (!iconKey || btn.dataset.iconBound === "1") return;
    const label = btn.textContent.trim();
    const img = explorerIconImgHtml(iconKey, "objectives-tab__icon", 18);
    if (img) {
      btn.innerHTML = `${img}<span class="objectives-tab__label">${label}</span>`;
      btn.dataset.iconBound = "1";
    }
  });
}

const WORKSHOP_TUTORIAL_LS = "epoch_workshop_tutorial_done_v20260524";
let workshopTutorialStep = 0;
let workshopTutorialActive = false;

function buildWorkshopTutorialSteps(snap) {
  const steps = [
    {
      id: "intro",
      center: true,
      title: "欢迎来到基地核心 · 自动化设施",
      body: "基地核心已整合自动化产线：启动配装含采矿机与冶炼厂，再放置 3D 打印机即可产零件。",
    },
  ];
  if (!snap?.built) {
    steps.push({
      id: "construct",
      target: ".workshop-scene-gate .workshop-construct-btn, .workshop-scene-gate .workshop-discover-btn",
      title: "第一步：启用工坊",
      body: snap?.blueprint_known
        ? "点击「开始改造工坊」。首次进入会调拨启动物资；改造后免费获得采矿机与仓储柜。"
        : "先「查看蓝图」，再完成改造。系统会自动补足起步资源。",
    });
  }
  if (snap?.built) {
    steps.push(
      {
        id: "resources",
        target: ".workshop-scene-resources",
        title: "看清两种资源",
        body: "工坊仓库存矿石/合金/零件；顶栏「基地 件」才是建造用的零件。打印机产物需点「运回零件」。",
      },
      {
        id: "grid",
        target: ".workshop-scene-grid",
        title: "10×10 生产网格",
        body: "点击设备查看详情；右侧选设备后，绿色格子可放置。原料经相邻仓储自动传递。",
      },
      {
        id: "build",
        target: ".workshop-build-list",
        title: "建造清单",
        body: "推荐链条：采矿机 → 冶炼厂 → 3D 打印机。能源不足时在能源区建发电站（1 矿石/周期 → 基地能源）；医疗包链需组装厂产元件。",
      },
      {
        id: "starter",
        target: ".workshop-grid-cell--type-miner, .workshop-grid-cell--type-storage",
        title: "起步配装",
        body: "已赠送采矿机与仓储柜。确保采矿机旁有仓储，矿石才会入库。",
        optional: true,
      },
      {
        id: "tasks",
        target: ".workshop-scene-tasks",
        title: "随机生产指标",
        body: "左侧显示所需物资与奖励（未知显示 ???），备齐后点交付。",
      },
      {
        id: "export",
        target: ".workshop-scene-toolbar",
        title: "运回基地与委任",
        body: "底部可将零件/医疗包运回基地；勾选委任可让 NPC 以 70% 效率自动建造与排班。",
      },
    );
  }
  steps.push({
    id: "done",
    center: true,
    title: "引导完成",
    body: "随时点顶部「教程」重温。祝运营顺利！",
    done: true,
  });
  return steps;
}

function workshopTutorialSteps(snap) {
  return buildWorkshopTutorialSteps(snap).filter((s) => {
    if (!s.optional) return true;
    if (s.id === "starter") {
      return !!workshopMapEl?.querySelector(".workshop-grid-cell--type-miner");
    }
    return true;
  });
}

function ensureWorkshopTutorialOverlay() {
  const root = ensureWorkshopMap();
  let overlay = root.querySelector(".workshop-tutorial");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.className = "workshop-tutorial hidden";
  overlay.setAttribute("aria-hidden", "true");
  overlay.innerHTML = `
    <div class="workshop-tutorial-hole" aria-hidden="true"></div>
    <div class="workshop-tutorial-card" role="dialog" aria-modal="true" aria-labelledby="workshop-tutorial-title">
      <p class="workshop-tutorial-progress"></p>
      <h3 id="workshop-tutorial-title" class="workshop-tutorial-title"></h3>
      <p class="workshop-tutorial-body"></p>
      <div class="workshop-tutorial-actions">
        <button type="button" class="workshop-btn workshop-btn--ghost workshop-tutorial-skip">跳过</button>
        <button type="button" class="workshop-btn workshop-btn--primary workshop-tutorial-next">下一步</button>
      </div>
    </div>`;
  overlay.querySelector(".workshop-tutorial-skip")?.addEventListener("click", () => closeWorkshopTutorial(true));
  overlay.querySelector(".workshop-tutorial-next")?.addEventListener("click", () => advanceWorkshopTutorial());
  root.appendChild(overlay);
  return overlay;
}

function ensureWorkshopTutorialButton() {
  const root = workshopMapEl || ensureWorkshopMap();
  if (root.querySelector(".workshop-tutorial-open")) return;
  const topbar = root.querySelector(".workshop-map-topbar");
  const back = topbar?.querySelector(".workshop-map-back");
  if (!topbar || !back) return;
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "workshop-btn workshop-btn--ghost workshop-btn--sm workshop-tutorial-open";
  btn.textContent = "玩法教程";
  btn.addEventListener("click", () => openWorkshopTutorial(true));
  back.insertAdjacentElement("afterend", btn);
}

function positionWorkshopTutorialHighlight(step) {
  const overlay = ensureWorkshopTutorialOverlay();
  const hole = overlay.querySelector(".workshop-tutorial-hole");
  const card = overlay.querySelector(".workshop-tutorial-card");
  if (!hole || !card) return;
  hole.style.display = "none";
  card.classList.remove("workshop-tutorial-card--anchor");
  let target = null;
  if (step?.target && !step.center) {
    target = workshopMapEl?.querySelector(step.target);
  }
  if (target) {
    const pad = 8;
    const r = target.getBoundingClientRect();
    hole.style.display = "block";
    hole.style.left = `${Math.max(4, r.left - pad)}px`;
    hole.style.top = `${Math.max(4, r.top - pad)}px`;
    hole.style.width = `${r.width + pad * 2}px`;
    hole.style.height = `${r.height + pad * 2}px`;
    card.classList.add("workshop-tutorial-card--anchor");
    const cardRect = card.getBoundingClientRect();
    let left = r.left;
    let top = r.bottom + 14;
    if (top + cardRect.height > window.innerHeight - 12) top = r.top - cardRect.height - 14;
    if (left + 320 > window.innerWidth - 12) left = window.innerWidth - 332;
    card.style.left = `${Math.max(12, left)}px`;
    card.style.top = `${Math.max(12, top)}px`;
    target.classList.add("workshop-tutorial-target");
  } else {
    card.style.left = "50%";
    card.style.top = "50%";
    card.style.transform = "translate(-50%, -50%)";
  }
}

function clearWorkshopTutorialTargets() {
  workshopMapEl?.querySelectorAll(".workshop-tutorial-target").forEach((el) => {
    el.classList.remove("workshop-tutorial-target");
  });
}

function renderWorkshopTutorialStep() {
  if (!workshopTutorialActive || !workshopUiSnap) return;
  const steps = workshopTutorialSteps(workshopUiSnap);
  if (workshopTutorialStep >= steps.length) {
    closeWorkshopTutorial(true);
    return;
  }
  const step = steps[workshopTutorialStep];
  const overlay = ensureWorkshopTutorialOverlay();
  clearWorkshopTutorialTargets();
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  overlay.querySelector(".workshop-tutorial-progress").textContent = `${workshopTutorialStep + 1} / ${steps.length}`;
  overlay.querySelector(".workshop-tutorial-title").textContent = step.title;
  overlay.querySelector(".workshop-tutorial-body").textContent = step.body;
  const nextBtn = overlay.querySelector(".workshop-tutorial-next");
  if (nextBtn) nextBtn.textContent = step.done ? "完成" : "下一步";
  const card = overlay.querySelector(".workshop-tutorial-card");
  if (card) card.style.transform = step.center ? "translate(-50%, -50%)" : "";
  positionWorkshopTutorialHighlight(step);
}

function refreshWorkshopTutorialLayout() {
  if (!workshopTutorialActive) return;
  renderWorkshopTutorialStep();
}

function openWorkshopTutorial(force = false) {
  if (!workshopUiSnap) return;
  if (!force) {
    try {
      if (localStorage.getItem(WORKSHOP_TUTORIAL_LS)) return;
    } catch {
      /* ignore */
    }
  }
  workshopTutorialStep = 0;
  workshopTutorialActive = true;
  ensureWorkshopTutorialButton();
  renderWorkshopTutorialStep();
}

function closeWorkshopTutorial(markDone = false) {
  workshopTutorialActive = false;
  clearWorkshopTutorialTargets();
  const overlay = workshopMapEl?.querySelector(".workshop-tutorial");
  overlay?.classList.add("hidden");
  overlay?.setAttribute("aria-hidden", "true");
  if (markDone) {
    try {
      localStorage.setItem(WORKSHOP_TUTORIAL_LS, "1");
    } catch {
      /* ignore */
    }
  }
}

function advanceWorkshopTutorial() {
  const steps = workshopTutorialSteps(workshopUiSnap);
  const step = steps[workshopTutorialStep];
  if (step?.done) {
    closeWorkshopTutorial(true);
    return;
  }
  workshopTutorialStep += 1;
  if (workshopTutorialStep >= steps.length) closeWorkshopTutorial(true);
  else renderWorkshopTutorialStep();
}

function maybeStartWorkshopTutorial(snap) {
  if (!snap) return;
  try {
    if (localStorage.getItem(WORKSHOP_TUTORIAL_LS)) return;
  } catch {
    /* ignore */
  }
  workshopUiSnap = snap;
  openWorkshopTutorial(false);
}

function isWorkshopTutorialOpen() {
  return workshopTutorialActive && !workshopMapEl?.querySelector(".workshop-tutorial")?.classList.contains("hidden");
}

function isWorkshopOpen() {
  return !!(workshopMapEl && !workshopMapEl.classList.contains("hidden"));
}

function repairWorkshopOverlayState() {
  const el = document.getElementById("workshop-map-scene");
  if (!el) {
    workshopMapEl = null;
    document.body.classList.remove("scene-workshop");
    document.getElementById("game")?.removeAttribute("aria-hidden");
    return;
  }
  workshopMapEl = el;
  const open = !el.classList.contains("hidden");
  document.body.classList.toggle("scene-workshop", open);
  if (!open) document.getElementById("game")?.removeAttribute("aria-hidden");
}

function ensureMainGameSceneVisible() {
  repairWorkshopOverlayState();
}

function bootWorkshopUiState() {
  const existing = document.getElementById("workshop-map-scene");
  if (existing) {
    existing.classList.add("hidden");
    existing.setAttribute("aria-hidden", "true");
    workshopMapEl = existing;
  }
  repairWorkshopOverlayState();
}

function isWestShaftSimOpen() {
  return isWorkshopOpen();
}

function workshopEntryLabel(fromId) {
  return "基地核心 · 自动化设施";
}

function enterWorkshopMapScene(fromId = "west_shaft") {
  workshopEntryFrom = fromId || "west_shaft";
  document.title = "源纪元 · 基地核心";
  const canvasEl = document.getElementById("game");
  if (canvasEl) canvasEl.setAttribute("aria-hidden", "true");
  const root = ensureWorkshopMap();
  root.classList.remove("hidden");
  root.setAttribute("aria-hidden", "false");
  document.body.classList.add("scene-workshop");
  root.focus({ preventScroll: true });
  const loc = root.querySelector(".workshop-map-loc-sub");
  if (loc) loc.textContent = workshopEntryLabel(workshopEntryFrom);
}

function exitWorkshopMapScene() {
  const wasOpen = isWorkshopOpen();
  if (wasOpen) {
    fetchJSON(gameApiUrl("/api/sim/workshop/leave"), { method: "POST", body: "{}" }).catch(() => {});
  }
  closeWorkshopTutorial(false);
  document.body.classList.remove("scene-workshop");
  document.title = "源纪元 · 岸线侵入 — 基地大地图探索";
  document.getElementById("game")?.removeAttribute("aria-hidden");
  if (workshopMapEl) {
    workshopMapEl.classList.add("hidden");
    workshopMapEl.setAttribute("aria-hidden", "true");
  }
  workshopBuildType = null;
  workshopMoveFrom = null;
  workshopSelected = null;
  if (workshopPollTimer != null) {
    clearInterval(workshopPollTimer);
    workshopPollTimer = null;
  }
  return wasOpen;
}

function closeWorkshopScene() {
  return exitWorkshopMapScene();
}

function closeWestShaftSimScene() {
  return exitWorkshopMapScene();
}

function migrateWorkshopMapLayout(root) {
  if (root.querySelector(".workshop-map-layout")) return;
  const body = root.querySelector(".workshop-scene-body");
  if (!body) return;
  const pick = (sel) => {
    const el = root.querySelector(sel);
    if (el) el.remove();
    return el;
  };
  const resources = pick(".workshop-scene-resources");
  const hint = pick(".workshop-scene-hint");
  const tasks = pick(".workshop-scene-tasks");
  const log = pick(".workshop-scene-log");
  const gridWrap = pick(".workshop-scene-grid-wrap");
  const sidebar = pick(".workshop-scene-sidebar");
  const deleg = pick(".workshop-delegation-status");
  const toolbar = pick(".workshop-scene-toolbar");
  const footer = root.querySelector(".workshop-map-footer");
  footer?.remove();
  root.querySelector(".workshop-map-main")?.remove();
  root.querySelector(".workshop-map-floor")?.remove();
  const hud = root.querySelector(".workshop-map-hud");
  hud?.remove();
  const topbar = document.createElement("header");
  topbar.className = "workshop-map-topbar";
  topbar.innerHTML = `
    <button type="button" class="workshop-map-back workshop-btn workshop-btn--ghost">← 返回大地图</button>
    <button type="button" class="workshop-btn workshop-btn--ghost workshop-btn--sm workshop-tutorial-open">玩法教程</button>
    <div class="workshop-map-location">
      <span class="workshop-map-loc-sub">西脉浅巷 · 地下层</span>
      <h1 id="workshop-scene-title" class="workshop-scene-title">基地核心</h1>
    </div>`;
  topbar.querySelector(".workshop-map-back")?.addEventListener("click", () => closeWorkshopScene());
  topbar.querySelector(".workshop-tutorial-open")?.addEventListener("click", () => openWorkshopTutorial(true));
  const layout = document.createElement("main");
  layout.className = "workshop-map-layout";
  const left = document.createElement("aside");
  left.className = "workshop-map-left";
  for (const el of [resources, hint, tasks, log, deleg].filter(Boolean)) left.appendChild(el);
  const center = document.createElement("section");
  center.className = "workshop-map-center";
  if (gridWrap) center.appendChild(gridWrap);
  const right = document.createElement("aside");
  right.className = "workshop-map-right workshop-scene-sidebar";
  if (sidebar) {
    while (sidebar.firstChild) right.appendChild(sidebar.firstChild);
  }
  if (toolbar) {
    const actions = document.createElement("div");
    actions.className = "workshop-map-actions";
    actions.appendChild(toolbar);
    right.appendChild(actions);
  }
  layout.append(left, center, right);
  body.prepend(topbar);
  body.appendChild(layout);
}

function ensureWorkshopMap() {
  if (workshopMapEl) {
    const wrap = workshopMapEl.querySelector(".workshop-scene-grid-wrap");
    if (wrap && !wrap.querySelector(".workshop-grid-stage")) {
      const stage = document.createElement("div");
      stage.className = "workshop-grid-stage";
      for (const sel of [".workshop-zone-labels", ".workshop-logistics-svg", ".workshop-scene-grid"]) {
        const node = wrap.querySelector(sel);
        if (node) stage.appendChild(node);
      }
      wrap.replaceChildren(stage);
    }
    migrateWorkshopMapLayout(workshopMapEl);
    ensureWorkshopGridStructure(workshopMapEl);
    if (!workshopMapEl.querySelector(".workshop-interaction-bar")) {
      const center = workshopMapEl.querySelector(".workshop-map-center");
      const wrap2 = center?.querySelector(".workshop-scene-grid-wrap");
      if (center && wrap2) {
        const bar = document.createElement("div");
        bar.className = "workshop-interaction-bar";
        bar.innerHTML = `<span class="workshop-interaction-mode">浏览模式</span>
          <button type="button" class="workshop-btn workshop-btn--sm workshop-btn--ghost workshop-cancel-build hidden">取消建造</button>`;
        center.insertBefore(bar, wrap2);
      }
    }
    bindWorkshopMapInteraction(workshopMapEl);
    ensureWorkshopTutorialButton();
    return workshopMapEl;
  }
  const root = document.createElement("div");
  root.id = "workshop-map-scene";
  root.className = "workshop-map hidden";
  root.setAttribute("aria-hidden", "true");
  root.innerHTML = `
    <div class="workshop-map-viewport">
      <div class="workshop-scene-gate hidden"></div>
      <div class="workshop-scene-body hidden">
        <header class="workshop-map-topbar">
          <button type="button" class="workshop-map-back workshop-btn workshop-btn--ghost">← 返回</button>
          <div class="workshop-map-location">
            <h1 id="workshop-scene-title" class="workshop-scene-title">基地核心</h1>
          </div>
          <button type="button" class="workshop-btn workshop-btn--ghost workshop-btn--sm workshop-tutorial-open">教程</button>
        </header>
        <main class="workshop-map-layout">
          <aside class="workshop-map-left">
            <div class="workshop-scene-resources"></div>
            <div class="workshop-scene-tasks"></div>
          </aside>
          <section class="workshop-map-center" aria-label="工坊生产层地图">
            <div class="workshop-interaction-bar hidden">
              <span class="workshop-interaction-mode"></span>
              <button type="button" class="workshop-btn workshop-btn--sm workshop-btn--ghost workshop-cancel-build hidden">取消</button>
            </div>
            <div class="workshop-scene-grid-wrap">
              <div class="workshop-grid-stage">
                <div class="workshop-zone-labels" aria-hidden="true"></div>
                <svg class="workshop-logistics-svg" aria-hidden="true" preserveAspectRatio="none"></svg>
                <div class="workshop-scene-grid" aria-label="10×10 工坊网格"></div>
              </div>
            </div>
          </section>
          <aside class="workshop-map-right workshop-scene-sidebar">
            <p class="workshop-build-head">建造 · 消耗基地资源</p>
            <div class="workshop-build-list" aria-label="建造清单"></div>
            <div class="workshop-device-detail hidden">
              <div class="workshop-device-detail-body"></div>
            </div>
            <div class="workshop-scene-trade hidden">
              <div class="workshop-trade-list"></div>
            </div>
            <div class="workshop-scene-fatigue hidden">
              <div class="workshop-fatigue-list"></div>
            </div>
            <div class="workshop-scene-caps">
              <label class="workshop-caps-enable-label"><input type="checkbox" class="workshop-caps-enable-cb" /> 达上限停产</label>
              <p class="workshop-caps-hint">停线阈值：0=不限；矿石默认 50。设成 1 会导致只产 1 个就停。</p>
              <div class="workshop-caps-list"></div>
            </div>
            <div class="workshop-map-actions">
              <div class="workshop-scene-toolbar">
                <label class="workshop-delegate-label"><input type="checkbox" class="workshop-delegate-cb" /> 委任</label>
                <button type="button" class="workshop-btn workshop-btn--ghost workshop-import-ore">导入源矿</button>
                <button type="button" class="workshop-btn workshop-btn--ghost workshop-export-parts">运回零件</button>
                <button type="button" class="workshop-btn workshop-btn--ghost workshop-export-med">运回医疗</button>
              </div>
            </div>
          </aside>
        </main>
      </div>
    </div>`;
  root.querySelector(".workshop-map-back")?.addEventListener("click", () => closeWorkshopScene());
  root.querySelector(".workshop-tutorial-open")?.addEventListener("click", () => openWorkshopTutorial(true));
  root.querySelector(".workshop-delegate-cb")?.addEventListener("change", (ev) => {
    postWorkshopDelegate(ev.target.checked);
  });
  root.querySelector(".workshop-import-ore")?.addEventListener("click", () => postWorkshopImportOre(1));
  root.querySelector(".workshop-export-parts")?.addEventListener("click", () => postWorkshopExport("parts", 999));
  root.querySelector(".workshop-export-med")?.addEventListener("click", () => postWorkshopExport("medical_pack", 999));
  root.setAttribute("tabindex", "0");
  document.body.appendChild(root);
  workshopMapEl = root;
  bindWorkshopMapInteraction(root);
  return root;
}


function workshopSnapFromData(data) {
  return data?.workshop || data?.underground_workshop || data?.west_shaft || data?.west_shaft_sim;
}

function setWorkshopLoading(on) {
  if (workshopMapEl) {
    workshopMapEl.classList.toggle("workshop-map--loading", on);
  }
}

async function syncWorkshopFromResponse(data, opts = {}) {
  setWorkshopLoading(false);
  latestState = data;
  // 工坊操作后立即保存到 localStorage
  persistSessionToLocalStorage();
  renderMgmtResourcesHud(data.session);
  renderMgmtLogStrip(data.management_recent);
  const snap = workshopSnapFromData(data);
  if (!snap) return;
  workshopUiSnap = snap;
  if (!isWorkshopOpen()) return;
  if (opts.soft) {
    updateWorkshopLiveData(snap, opts);
  } else {
    renderWorkshopScene(snap);
  }
}

function workshopCatalogEntry(snap, type) {
  return (snap?.build_catalog || []).find((d) => d.type === type) || null;
}

function workshopCanPlaceAt(snap, x, y, entry, opts = {}) {
  if (!entry || !snap?.grid) return false;
  const gridSize = snap.grid_size || 10;
  const w = entry.w || 1;
  const h = entry.h || 1;
  if (x < 0 || y < 0 || x + w > gridSize || y + h > gridSize) return false;
  const ignore = opts.ignoreAnchor || null;
  for (let dy = 0; dy < h; dy++) {
    for (let dx = 0; dx < w; dx++) {
      const cell = snap.grid[y + dy]?.[x + dx];
      if (!cell) continue;
      if (ignore && cell.anchor_x === ignore.x && cell.anchor_y === ignore.y) continue;
      return false;
    }
  }
  return true;
}

function workshopMoveDeviceEntry(snap, anchor) {
  if (!anchor || !snap?.devices) return null;
  const dev =
    snap.devices.find((d) => d.anchor_x === anchor.x && d.anchor_y === anchor.y) || null;
  if (!dev) return null;
  return { type: dev.type, label_zh: dev.label_zh, w: dev.w || 1, h: dev.h || 1 };
}

function workshopCanMoveTo(snap, fromAnchor, toX, toY) {
  const entry = workshopMoveDeviceEntry(snap, fromAnchor);
  if (!entry) return false;
  return workshopCanPlaceAt(snap, toX, toY, entry, { ignoreAnchor: fromAnchor });
}

function workshopCancelMoveMode() {
  workshopMoveFrom = null;
}

function workshopCanAffordBuild(snap, entry) {
  if (!entry?.build || !snap?.base_resources) return false;
  const br = snap.base_resources;
  return Object.entries(entry.build).every(([k, v]) => (br[k] ?? 0) >= Number(v));
}

function workshopAffordReason(snap, entry) {
  const br = snap?.base_resources || {};
  const resZh = { ...WORKSHOP_BASE_RES_ZH, ...WORKSHOP_RES_ZH };
  const parts = [];
  for (const [k, v] of Object.entries(entry?.build || {})) {
    const need = Number(v);
    const have = Number(br[k] ?? 0);
    if (have < need) parts.push(`${resZh[k] || k} ${have}/${need}`);
  }
  return parts.join(" · ");
}

function workshopBuildCostParts(build) {
  const order = ["energy", "parts", "food", "medical", "intel"];
  const c = build || {};
  const seen = new Set();
  const rows = [];
  for (const k of order) {
    if (k in c) {
      seen.add(k);
      const need = Number(c[k]);
      if (need > 0) rows.push({ key: k, label: WORKSHOP_BASE_RES_ZH[k] || k, need });
    }
  }
  for (const [k, v] of Object.entries(c)) {
    if (seen.has(k)) continue;
    const need = Number(v);
    if (need > 0) rows.push({ key: k, label: WORKSHOP_BASE_RES_ZH[k] || WORKSHOP_RES_ZH[k] || k, need });
  }
  return rows;
}

function workshopBuildCostText(build) {
  const rows = workshopBuildCostParts(build);
  return rows.length ? rows.map((r) => `${r.label}×${r.need}`).join(" · ") : "—";
}

function workshopBuildCostHtml(build, snap) {
  const br = snap?.base_resources || {};
  const rows = workshopBuildCostParts(build);
  if (!rows.length) return `<small class="workshop-build-cost">—</small>`;
  const spans = rows
    .map((r) => {
      const have = Number(br[r.key] ?? 0);
      const lack = have < r.need;
      return `<span class="workshop-build-res${lack ? " workshop-build-res--lack" : ""}">${r.label}×${r.need}</span>`;
    })
    .join('<span class="workshop-build-sep"> · </span>');
  return `<small class="workshop-build-cost">${spans}</small>`;
}

function workshopCanAffordUpgrade(snap, dev) {
  if (dev?.can_afford_upgrade === false) return false;
  if (dev?.can_afford_upgrade === true) return true;
  const cost = dev?.upgrade_cost || {};
  const br = snap?.base_resources || {};
  return Object.entries(cost).every(([k, v]) => (br[k] ?? 0) >= Number(v));
}

function workshopUpgradeAffordReason(snap, dev) {
  const br = snap?.base_resources || {};
  const resZh = { energy: "能源", parts: "零件", ...WORKSHOP_RES_ZH };
  const parts = [];
  for (const [k, v] of Object.entries(dev?.upgrade_cost || {})) {
    const need = Number(v);
    const have = Number(br[k] ?? 0);
    if (have < need) parts.push(`${resZh[k] || k} ${have}/${need}`);
  }
  return parts.join(" · ");
}

function renderWorkshopResourcesHtml(snap) {
  const wh = snap.warehouse || {};
  const br = snap.base_resources || {};
  const whKeys = ["ore", "alloy", "components", "parts", "medical_pack"];
  const whLine = whKeys.map((k) => `${WORKSHOP_RES_ZH[k] || k}${wh[k] ?? 0}`).join(" ");
  const extraWh = Object.entries(wh)
    .filter(([k, v]) => !whKeys.includes(k) && Number(v) > 0)
    .map(([k, v]) => `${WORKSHOP_RES_ZH[k] || k}${v}`)
    .join(" ");
  const whDisplay = extraWh ? `${whLine} ${extraWh}` : whLine;
  return `<div class="workshop-res-block workshop-res-block--compact">
    <span>仓 ${whDisplay} · ${snap.storage_used}/${snap.storage_cap}</span>
    <span>基地 能${br.energy ?? 0} 件${br.parts ?? 0} · 源矿缓冲${snap.source_ore_buffer ?? 0}</span>
  </div>`;
}

function ensureWorkshopGridStructure(root) {
  let wrap = root.querySelector(".workshop-scene-grid-wrap");
  const center = root.querySelector(".workshop-map-center");
  if (!wrap && center) {
    wrap = document.createElement("div");
    wrap.className = "workshop-scene-grid-wrap";
    center.appendChild(wrap);
  }
  if (!wrap) return null;

  let stage = wrap.querySelector(".workshop-grid-stage");
  if (!stage) {
    stage = document.createElement("div");
    stage.className = "workshop-grid-stage";
    wrap.replaceChildren(stage);
  }

  if (!stage.querySelector(".workshop-zone-labels")) {
    const zoneWrap = document.createElement("div");
    zoneWrap.className = "workshop-zone-labels";
    zoneWrap.setAttribute("aria-hidden", "true");
    stage.appendChild(zoneWrap);
  }
  if (!stage.querySelector(".workshop-logistics-svg")) {
    const svgEl = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svgEl.classList.add("workshop-logistics-svg");
    svgEl.setAttribute("aria-hidden", "true");
    svgEl.setAttribute("preserveAspectRatio", "none");
    stage.appendChild(svgEl);
  }
  if (!stage.querySelector(".workshop-scene-grid")) {
    const gridEl = document.createElement("div");
    gridEl.className = "workshop-scene-grid";
    gridEl.setAttribute("aria-label", "10×10 工坊网格");
    stage.appendChild(gridEl);
  }

  return {
    stage,
    zoneWrap: stage.querySelector(".workshop-zone-labels"),
    svgEl: stage.querySelector(".workshop-logistics-svg"),
    gridEl: stage.querySelector(".workshop-scene-grid"),
  };
}

function workshopCellAt(snap, x, y) {
  return snap?.grid?.[y]?.[x] ?? null;
}

function workshopAnchorOf(cell) {
  if (!cell) return null;
  if (cell.is_anchor) return { x: cell.anchor_x, y: cell.anchor_y };
  if (cell.anchor_x != null && cell.anchor_y != null) return { x: cell.anchor_x, y: cell.anchor_y };
  return null;
}

function handleWorkshopEscapeKey() {
  if (isWorkshopTutorialOpen()) {
    closeWorkshopTutorial(true);
    return true;
  }
  if (!isWorkshopOpen()) return false;
  if (workshopBuildType) {
    workshopBuildType = null;
    renderWorkshopScene(workshopUiSnap);
    showToast("已取消建造模式。", 1800);
    return true;
  }
  if (workshopMoveFrom) {
    workshopCancelMoveMode();
    renderWorkshopScene(workshopUiSnap);
    showToast("已取消移动。", 1800);
    return true;
  }
  if (workshopSelected) {
    workshopSelected = null;
    renderWorkshopScene(workshopUiSnap);
    return true;
  }
  return false;
}

function workshopSelectedDevice(snap) {
  if (!workshopSelected || !snap?.devices) return null;
  return (
    snap.devices.find((d) => d.anchor_x === workshopSelected.x && d.anchor_y === workshopSelected.y) || null
  );
}

function workshopPrinterRecipeLabel(recipe) {
  return recipe === "medical" ? "医疗包" : "零件";
}

function workshopDeviceDetailStatsHtml(dev) {
  if (!dev) return "";
  const parts = [];
  if (dev.type === "printer" && dev.recipe_zh) {
    parts.push(`<span class="workshop-detail-recipe">当前配方 ${dev.recipe_zh}</span>`);
  }
  if (dev.rate_zh) parts.push(`<span class="workshop-detail-rate">产出 ${dev.rate_zh}</span>`);
  if (dev.status_zh) {
    const sc = dev.status_code || "running";
    parts.push(`<span class="workshop-detail-status workshop-detail-status--${sc}">${dev.status_zh}</span>`);
  }
  if (dev.status_code !== "storage" && Number(dev.cycle_s) > 0) {
    parts.push(`<span class="workshop-detail-cycle">周期 ${dev.progress_pct ?? 0}%</span>`);
  }
  if (dev.npc_label_zh) {
    const eff =
      dev.npc_efficiency_pct != null && dev.npc_efficiency_pct < 100 ? ` · 效率 ${dev.npc_efficiency_pct}%` : "";
    parts.push(`<span class="workshop-detail-npc">岗位 ${dev.npc_label_zh}${eff}</span>`);
  }
  if (!parts.length) return "";
  return `<p class="workshop-device-detail-stats">${parts.join("")}</p>`;
}

function refreshWorkshopSelectionHighlight() {
  const root = workshopMapEl;
  if (!root) return;
  root.querySelectorAll(".workshop-grid-cell--selected").forEach((el) => el.classList.remove("workshop-grid-cell--selected"));
  if (!workshopSelected) return;
  const btn = root.querySelector(
    `.workshop-scene-grid .workshop-grid-cell[data-x="${workshopSelected.x}"][data-y="${workshopSelected.y}"]`,
  );
  btn?.classList.add("workshop-grid-cell--selected");
}

function workshopApplyCellStatusClasses(btn, cell) {
  const statusPrefix = "workshop-grid-cell--status-";
  const sc = cell?.status_code || "running";
  btn.classList.toggle("workshop-grid-cell--off", !!cell && !cell.enabled);
  [...btn.classList].forEach((c) => {
    if (c.startsWith(statusPrefix)) btn.classList.remove(c);
  });
  btn.classList.toggle("workshop-grid-cell--running", !!cell && cell.enabled && sc === "running");
  if (sc !== "running" && sc !== "storage") btn.classList.add(`${statusPrefix}${sc}`);
}

function patchWorkshopGridFromSnap(snap) {
  const root = workshopMapEl;
  if (!root || workshopBuildType || workshopMoveFrom) return;
  const gridSize = snap.grid_size || 10;
  const grid = snap.grid || [];
  for (let y = 0; y < gridSize; y++) {
    for (let x = 0; x < gridSize; x++) {
      const btn = root.querySelector(`.workshop-scene-grid .workshop-grid-cell[data-x="${x}"][data-y="${y}"]`);
      const cell = grid[y]?.[x];
      if (!btn || !cell?.is_anchor) continue;
      workshopApplyCellStatusClasses(btn, cell);
      const pct = cell.progress_pct ?? 0;
      btn.style.setProperty("--progress-pct", `${pct}%`);
      const prog = btn.querySelector(".workshop-cell-progress");
      if (prog) prog.style.width = `${pct}%`;
      btn.title = `${cell.status_zh || ""} — 双击切换启停`;
    }
  }
  refreshWorkshopSelectionHighlight();
}

function updateWorkshopDeviceDetailStats(snap, dev) {
  const detailBody = workshopMapEl?.querySelector(".workshop-device-detail-body");
  if (!detailBody || !dev) return;
  const titleEl = detailBody.querySelector(".workshop-device-detail-title");
  if (titleEl) titleEl.innerHTML = `<strong>${dev.label_zh}</strong> L${dev.level}`;
  const html = workshopDeviceDetailStatsHtml(dev);
  const existing = detailBody.querySelector(".workshop-device-detail-stats");
  if (html) {
    if (existing) existing.outerHTML = html;
    else if (titleEl) titleEl.insertAdjacentHTML("afterend", html);
  } else {
    existing?.remove();
  }
}

function renderWorkshopDeviceDetail(snap, dev, opts = {}) {
  const root = workshopMapEl;
  const detailWrap = root?.querySelector(".workshop-device-detail");
  const detailBody = root?.querySelector(".workshop-device-detail-body");
  if (!detailWrap || !detailBody || !dev) return;
  detailWrap.classList.remove("hidden");
  detailBody.replaceChildren();
  const title = document.createElement("p");
  title.className = "workshop-device-detail-title";
  title.innerHTML = `<strong>${dev.label_zh}</strong> L${dev.level}`;
  detailBody.appendChild(title);
  const statsHtml = workshopDeviceDetailStatsHtml(dev);
  if (statsHtml) detailBody.insertAdjacentHTML("beforeend", statsHtml);
  const actions = document.createElement("div");
  actions.className = "workshop-detail-actions";
  const mk = (label, fn, primary = false) => {
    const bb = document.createElement("button");
    bb.type = "button";
    bb.className = `workshop-btn workshop-btn--sm${primary ? " workshop-btn--primary" : ""}`;
    bb.textContent = label;
    bb.disabled = !!snap.abandoned;
    bb.addEventListener("click", fn);
    return bb;
  };
  actions.appendChild(mk(dev.enabled ? "暂停" : "启用", () => postWorkshopToggle(dev.anchor_x, dev.anchor_y), true));
  actions.appendChild(
    mk("移动", () => {
      workshopBuildType = null;
      workshopMoveFrom = { x: dev.anchor_x, y: dev.anchor_y };
      workshopSelected = { x: dev.anchor_x, y: dev.anchor_y };
      renderWorkshopScene(workshopUiSnap);
      showToast(`移动 ${dev.label_zh}：点击绿色高亮格放置（Esc 取消）`, 3200);
    }),
  );
  if (dev.can_upgrade) {
    const upAfford = workshopCanAffordUpgrade(snap, dev);
    const upCost = dev.upgrade_cost || {};
    const upLabel =
      upCost.energy != null || upCost.parts != null ? `升级 ${upCost.energy ?? 0}/${upCost.parts ?? 0}` : "升级";
    const upBtn = mk(upLabel, () => {
      if (!workshopCanAffordUpgrade(workshopUiSnap, dev)) {
        showToast(`基地资源不足：${workshopUpgradeAffordReason(workshopUiSnap, dev)}`, 3600);
        return;
      }
      postWorkshopUpgrade(dev.anchor_x, dev.anchor_y);
    });
    upBtn.disabled = !!snap.abandoned || !upAfford;
    if (!upAfford) upBtn.title = `基地资源不足：${workshopUpgradeAffordReason(snap, dev)}`;
    actions.appendChild(upBtn);
  }
  actions.appendChild(mk("拆除", () => postWorkshopDemolish(dev.anchor_x, dev.anchor_y)));
  if (dev.type === "printer") {
    actions.appendChild(
      mk(`切换为${workshopPrinterRecipeLabel(dev.recipe === "medical" ? "default" : "medical")}`, () => {
        const cur = workshopSelectedDevice(workshopUiSnap);
        if (!cur || cur.type !== "printer") return;
        const next = cur.recipe === "medical" ? "default" : "medical";
        postWorkshopSetRecipe(cur.anchor_x, cur.anchor_y, next);
      }),
    );
  }
  detailBody.appendChild(actions);
  const sel = document.createElement("select");
  sel.className = "workshop-npc-select";
  sel.disabled = !!snap.abandoned;
  sel.innerHTML = `<option value="">— 未分配 —</option>${(snap.npc_roster || [])
    .map((n) => {
      const count = n.device_count || 0;
      const label = count > 0 ? `${n.label_zh}（${count}/2台）` : n.label_zh;
      return `<option value="${n.id}"${n.id === dev.npc_id ? " selected" : ""}>${label}</option>`;
    })
    .join("")}`;
  sel.addEventListener("change", () => postWorkshopAssignNpc(dev.anchor_x, dev.anchor_y, sel.value));
  detailBody.appendChild(sel);
  if (opts.scroll) detailWrap.scrollIntoView({ block: "nearest", behavior: "smooth" });
  renderWorkshopCellInspector(workshopCellAt(snap, dev.anchor_x, dev.anchor_y), snap);
}

function refreshWorkshopDeviceDetailPanel(snap, opts = {}) {
  const dev = workshopSelectedDevice(snap);
  const detailWrap = workshopMapEl?.querySelector(".workshop-device-detail");
  const detailBody = workshopMapEl?.querySelector(".workshop-device-detail-body");
  if (!detailWrap || !detailBody) return;
  if (!workshopSelected) {
    detailWrap.classList.add("hidden");
    return;
  }
  if (dev) {
    const needFull = opts.full || dev.type === "printer";
    if (needFull) renderWorkshopDeviceDetail(snap, dev, opts);
    else updateWorkshopDeviceDetailStats(snap, dev);
  } else {
    renderWorkshopEmptyCellDetail(detailWrap, detailBody, snap, workshopSelected.x, workshopSelected.y);
    renderWorkshopCellInspector(null, snap);
  }
}

function updateWorkshopLiveData(snap, opts = {}) {
  workshopUiSnap = snap;
  const root = workshopMapEl;
  if (!root || root.classList.contains("hidden")) return;

  const resEl = root.querySelector(".workshop-scene-resources");
  if (resEl) resEl.innerHTML = renderWorkshopResourcesHtml(snap);

  patchWorkshopGridFromSnap(snap);
  renderWorkshopInteractionBar(snap);
  renderWorkshopTasksPanel(snap);
  refreshWorkshopDeviceDetailPanel(snap, opts);

  // 同步委任 checkbox 状态（实时刷新时保持 checkbox 与后端一致）
  const delCb = root.querySelector(".workshop-delegate-cb");
  if (delCb && delCb.checked !== !!snap.delegation_on) delCb.checked = !!snap.delegation_on;
  const delegStatus = root.querySelector(".workshop-delegation-status");
  if (delegStatus && snap.delegation_action_zh) {
    delegStatus.textContent = snap.delegation_action_zh;
  }

  // 疲劳面板实时刷新（休息完成后即时更新 UI）
  const fatigueWrap = root.querySelector(".workshop-scene-fatigue");
  const fatigueList = root.querySelector(".workshop-fatigue-list");
  if (fatigueWrap && fatigueList) {
    const tired = (snap.npc_fatigue || []).filter((row) => row.needs_rest);
    if (tired.length) {
      fatigueWrap.classList.remove("hidden");
      fatigueList.replaceChildren();
      for (const row of tired) {
        const line = document.createElement("div");
        line.className = "workshop-fatigue-row";
        line.innerHTML = `<span>${row.label_zh}</span>`;
        const rb = document.createElement("button");
        rb.type = "button";
        rb.className = "workshop-btn workshop-btn--sm";
        rb.textContent = "休息";
        rb.addEventListener("click", () => postWorkshopRestNpc(row.id));
        line.appendChild(rb);
        fatigueList.appendChild(line);
      }
    } else {
      fatigueWrap.classList.add("hidden");
    }
  }
}

function renderWorkshopInteractionBar(snap) {
  const root = workshopMapEl;
  if (!root) return;
  const bar = root.querySelector(".workshop-interaction-bar");
  const modeEl = root.querySelector(".workshop-interaction-mode");
  const cancelBtn = root.querySelector(".workshop-cancel-build");
  if (!bar || !modeEl) return;
  if (workshopBuildType) {
    const entry = workshopCatalogEntry(snap, workshopBuildType);
    bar.classList.remove("hidden");
    modeEl.textContent = entry?.label_zh || workshopBuildType;
    cancelBtn?.classList.remove("hidden");
    if (cancelBtn) cancelBtn.textContent = "取消建造";
  } else if (workshopMoveFrom) {
    const moveDev = workshopMoveDeviceEntry(snap, workshopMoveFrom);
    bar.classList.remove("hidden");
    modeEl.textContent = moveDev ? `移动 ${moveDev.label_zh}` : "移动设备";
    cancelBtn?.classList.remove("hidden");
    if (cancelBtn) cancelBtn.textContent = "取消移动";
  } else if (workshopSelected) {
    const cell = workshopCellAt(snap, workshopSelected.x, workshopSelected.y);
    bar.classList.remove("hidden");
    modeEl.textContent = cell?.label_zh || `格 ${workshopSelected.x},${workshopSelected.y}`;
    cancelBtn?.classList.add("hidden");
  } else {
    bar.classList.add("hidden");
    cancelBtn?.classList.add("hidden");
  }
}

function renderWorkshopCellInspector(_cell, _snap) {
  /* 左栏设备预览已移除，详情集中在右侧 */
}

function renderWorkshopEmptyCellDetail(detailWrap, detailBody, snap, x, y) {
  // 不再弹出快捷建造面板；用户从右上角建造目录中选择设备后直接点击空格放置
  detailWrap.classList.add("hidden");
}

function bindWorkshopMapInteraction(root) {
  if (root.dataset.interactionBound === "1") return;
  root.dataset.interactionBound = "1";

  root.addEventListener("click", (ev) => {
    if (!isWorkshopOpen()) return;
    if (ev.target.closest(".workshop-cancel-build")) {
      workshopBuildType = null;
      workshopCancelMoveMode();
      renderWorkshopScene(workshopUiSnap);
      return;
    }
    const btn = ev.target.closest(".workshop-grid-cell");
    if (!btn || btn.disabled) return;
    const gridEl = root.querySelector(".workshop-scene-grid");
    if (!gridEl?.contains(btn)) return;
    const x = parseInt(btn.dataset.x, 10);
    const y = parseInt(btn.dataset.y, 10);
    if (Number.isNaN(x) || Number.isNaN(y)) return;
    const cell = workshopCellAt(workshopUiSnap, x, y);
    onWorkshopCellClick(x, y, cell);
  });

  root.addEventListener("mouseover", (ev) => {
    if (!isWorkshopOpen()) return;
    const btn = ev.target.closest(".workshop-grid-cell");
    const gridEl = root.querySelector(".workshop-scene-grid");
    if (!btn || !gridEl?.contains(btn)) return;
    const x = parseInt(btn.dataset.x, 10);
    const y = parseInt(btn.dataset.y, 10);
    if (Number.isNaN(x) || Number.isNaN(y)) return;
    workshopHoverCell = { x, y };
    const cell = workshopCellAt(workshopUiSnap, x, y);
    renderWorkshopCellInspector(cell, workshopUiSnap);
  });

  root.addEventListener("dblclick", (ev) => {
    if (!isWorkshopOpen()) return;
    const btn = ev.target.closest(".workshop-grid-cell");
    if (!btn || btn.disabled) return;
    const gridEl = root.querySelector(".workshop-scene-grid");
    if (!gridEl?.contains(btn)) return;
    const x = parseInt(btn.dataset.x, 10);
    const y = parseInt(btn.dataset.y, 10);
    const cell = workshopCellAt(workshopUiSnap, x, y);
    const anchor = workshopAnchorOf(cell);
    if (anchor && cell?.is_anchor) postWorkshopToggle(anchor.x, anchor.y);
  });

  root.addEventListener("keydown", (ev) => {
    if (!isWorkshopOpen()) return;
    if (ev.key === "Escape") {
      if (handleWorkshopEscapeKey()) ev.preventDefault();
      return;
    }
    if (ev.key === "b" || ev.key === "B") {
      if (workshopBuildType) {
        workshopBuildType = null;
        renderWorkshopScene(workshopUiSnap);
        ev.preventDefault();
      }
    }
  });
}

function workshopNormalizeNeedItems(task) {
  if (Array.isArray(task?.need_items) && task.need_items.length) {
    return task.need_items;
  }
  const need = task?.need;
  if (need && typeof need === "object") {
    return Object.entries(need).map(([k, v]) => ({
      key: k,
      label_zh: WORKSHOP_RES_ZH[k] || k,
      have: 0,
      need: Number(v) || 0,
      met: false,
      pct: 0,
    }));
  }
  return [];
}

function renderWorkshopTasksPanel(snap) {
  const tasksEl = workshopMapEl?.querySelector(".workshop-scene-tasks");
  if (!tasksEl) return;
  const tasks = (snap?.tasks || []).filter((t) => !t.done);
  tasksEl.replaceChildren();

  if (!tasks.length) return;

  const activeWrap = document.createElement("div");
  activeWrap.className = "workshop-tasks-active";

  const statusRank = { ready: 0, progress: 1, pending: 2 };
  const statusShort = { ready: "可交", progress: "进行", pending: "待产" };
  const sorted = [...tasks].sort((a, b) => {
    const ra = statusRank[a.status || "pending"] ?? 9;
    const rb = statusRank[b.status || "pending"] ?? 9;
    return ra - rb;
  });

  for (const t of sorted) {
    const card = document.createElement("article");
    const st = t.status || (t.can_deliver ? "ready" : "pending");
    card.className = `workshop-task-card workshop-task-card--${st}${t.can_deliver ? " workshop-task-card--highlight" : ""}`;
    card.dataset.taskId = t.id || "";

    const head = document.createElement("div");
    head.className = "workshop-task-card-head";
    const statusEl = document.createElement("span");
    statusEl.className = `workshop-task-status workshop-task-status--${st}`;
    statusEl.textContent = statusShort[st] || t.status_zh || "—";
    head.appendChild(statusEl);
    card.appendChild(head);

    const needItems = workshopNormalizeNeedItems(t);
    const materials = document.createElement("div");
    materials.className = "workshop-task-materials";
    if (needItems.length) {
      for (const item of needItems) {
        const line = document.createElement("div");
        line.className = `workshop-task-material-line${item.met ? " workshop-task-material-line--met" : ""}`;
        line.innerHTML = `<span class="workshop-task-material-name">${item.label_zh || item.key || "物资"}</span>
          <span class="workshop-task-material-qty">${item.have ?? 0} / ${item.need ?? 0}</span>`;
        materials.appendChild(line);
      }
    } else if (t.need_display_zh || t.progress_zh) {
      const line = document.createElement("div");
      line.className = "workshop-task-material-line";
      line.textContent = t.need_display_zh || t.progress_zh;
      materials.appendChild(line);
    } else {
      const line = document.createElement("div");
      line.className = "workshop-task-material-line workshop-task-material-line--empty";
      line.textContent = "暂无物资要求";
      materials.appendChild(line);
    }
    card.appendChild(materials);

    if (t.reward_items?.length || t.reward_zh) {
      const rewards = document.createElement("div");
      rewards.className = "workshop-task-rewards";
      rewards.setAttribute("aria-label", "奖励");
      for (const item of t.reward_items || []) {
        const chip = document.createElement("span");
        chip.className = `workshop-task-reward-chip${item.hidden ? " workshop-task-reward-chip--hidden" : ""}`;
        chip.textContent = item.display_zh || (item.hidden ? "???" : `${item.label_zh}×${item.amount}`);
        rewards.appendChild(chip);
      }
      if (!rewards.children.length && t.reward_zh) {
        const chip = document.createElement("span");
        chip.className = "workshop-task-reward-chip";
        chip.textContent = t.reward_zh;
        rewards.appendChild(chip);
      }
      card.appendChild(rewards);
    }

    if (t.can_deliver && !snap.abandoned) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "workshop-btn workshop-btn--primary workshop-btn--sm workshop-task-deliver";
      b.textContent = "交付";
      b.addEventListener("click", () => postWorkshopDeliverTask(t.id));
      card.appendChild(b);
    }

    activeWrap.appendChild(card);
  }

  tasksEl.appendChild(activeWrap);
}

function renderWorkshopScene(snap) {
  if (!snap) return;
  workshopUiSnap = snap;
  const root = ensureWorkshopMap();
  const titleEl = root.querySelector(".workshop-scene-title");
  if (titleEl) titleEl.textContent = snap.name_zh || "基地核心";
  const leadEl = root.querySelector(".workshop-scene-lead");
  if (leadEl) leadEl.textContent = snap.lead_zh || "";

  // 同步委任 checkbox 状态与委任日志
  const delCb = root.querySelector(".workshop-delegate-cb");
  if (delCb) delCb.checked = !!snap.delegation_on;
  const delegStatus = root.querySelector(".workshop-delegation-status");
  if (delegStatus) delegStatus.textContent = snap.delegation_action_zh || "";

  const gate = root.querySelector(".workshop-scene-gate");
  const body = root.querySelector(".workshop-scene-body");
  if (!gate || !body) {
    showToast("工坊界面结构异常，请刷新页面。", 4200);
    exitWorkshopMapScene();
    return;
  }

  if (!snap.built) {
    gate.classList.remove("hidden");
    body.classList.add("hidden");
    const cost = snap.build_cost || { energy: 30, parts: 15 };
    const br = snap.base_resources || {};
    const canAffordSite =
      (br.energy ?? 0) >= (cost.energy ?? 0) && (br.parts ?? 0) >= (cost.parts ?? 0);
    let gateHtml = "";
    if (!snap.blueprint_known && !snap.blueprint_available) {
      gateHtml = `<p class="workshop-gate-msg">尚未获得自动化设施蓝图。推进第一幕并完成基地相关节点后，小胖会提示基地核心中的改造空间。</p>`;
    } else if (!snap.blueprint_known) {
      gateHtml = `<p class="workshop-gate-msg">蓝图已就绪：小胖说此处可改造成自动化产线。</p>
        <button type="button" class="workshop-btn workshop-btn--primary workshop-discover-btn">查看蓝图</button>`;
    } else {
      gateHtml = `<p class="workshop-gate-msg">一次性改造消耗：能源 ${cost.energy} + 零件 ${cost.parts}。改造后永久开放 10×10 分区生产网格。</p>
        <p class="workshop-gate-msg">首次进入调拨基地资源至 能源 ${(snap.entry_resource_floor || {}).energy ?? 100} · 零件 ${(snap.entry_resource_floor || {}).parts ?? 55}（仅首次）。</p>
        <p class="workshop-gate-msg">改造消耗 能源 ${cost.energy} + 零件 ${cost.parts}；完成后免费配装采矿机、冶炼厂、仓储柜。再建 3D 打印机（能源 30 + 零件 15），能源不足可建发电站（能源 20 + 零件 10）。</p>
        <p class="workshop-gate-msg">当前基地：能源 ${br.energy ?? 0} · 零件 ${br.parts ?? 0}${canAffordSite ? "" : "（不足，无法改造）"}</p>
        <button type="button" class="workshop-btn workshop-btn--primary workshop-construct-btn"${canAffordSite ? "" : " disabled"}>开始改造设施</button>`;
    }
    gate.innerHTML = gateHtml;
    gate.querySelector(".workshop-discover-btn")?.addEventListener("click", () => openWorkshopScene());
    gate.querySelector(".workshop-construct-btn")?.addEventListener("click", () => postWorkshopConstruct());
    return;
  }

  gate.classList.add("hidden");
  body.classList.remove("hidden");

  body.querySelector(".workshop-abandoned-banner")?.remove();
  const leftPanel = root.querySelector(".workshop-map-left");
  if (snap.abandoned) {
    body.classList.add("workshop-scene-body--abandoned");
    const rehab = document.createElement("div");
    rehab.className = "workshop-abandoned-banner";
    const rc = snap.rehab_cost || { energy: 50, parts: 30 };
    rehab.innerHTML = `<p>自动化设施因长期能源枯竭已停摆（已连续 ${snap.energy_deficit_days ?? 0} 日赤字）。</p>
      <button type="button" class="workshop-btn workshop-btn--primary workshop-rehab-btn">重启设施（能源 ${rc.energy} + 零件 ${rc.parts}）</button>`;
    rehab.querySelector(".workshop-rehab-btn")?.addEventListener("click", () => postWorkshopRehabilitate());
    leftPanel?.prepend(rehab);
  } else {
    body.classList.remove("workshop-scene-body--abandoned");
  }

  const resEl = root.querySelector(".workshop-scene-resources");
  if (resEl) resEl.innerHTML = renderWorkshopResourcesHtml(snap);

  renderWorkshopTasksPanel(snap);

  const gridSize = snap.grid_size || 10;
  const gridParts = ensureWorkshopGridStructure(root);
  const stageEl = gridParts?.stage;
  const gridEl = gridParts?.gridEl;
  const zoneWrap = gridParts?.zoneWrap;
  const svgEl = gridParts?.svgEl;
  if (!gridEl || !zoneWrap || !svgEl) {
    showToast("设施网格加载失败，已返回大地图。", 4200);
    exitWorkshopMapScene();
    return;
  }
  if (stageEl) stageEl.style.setProperty("--workshop-grid-size", String(gridSize));
  gridEl.style.setProperty("--workshop-grid-size", String(gridSize));
  gridEl.replaceChildren();

  zoneWrap.replaceChildren();
  for (const z of snap.zones || []) {
    const el = document.createElement("div");
    el.className = `workshop-zone-label workshop-zone-label--${z.id} workshop-zone-label--silent`;
    el.style.setProperty("--zx0", String(z.x0));
    el.style.setProperty("--zy0", String(z.y0));
    el.style.setProperty("--zx1", String(z.x1));
    el.style.setProperty("--zy1", String(z.y1));
    el.style.setProperty("--grid-size", String(gridSize));
    zoneWrap.appendChild(el);
  }

  const buildEntry = workshopBuildType ? workshopCatalogEntry(snap, workshopBuildType) : null;
  const moveEntry = workshopMoveFrom ? workshopMoveDeviceEntry(snap, workshopMoveFrom) : null;

  const grid = snap.grid || [];
  for (let y = 0; y < gridSize; y++) {
    for (let x = 0; x < gridSize; x++) {
      const cell = grid[y]?.[x];
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "workshop-grid-cell";
      btn.dataset.x = String(x);
      btn.dataset.y = String(y);
      const isMoveSource =
        workshopMoveFrom &&
        cell &&
        cell.anchor_x === workshopMoveFrom.x &&
        cell.anchor_y === workshopMoveFrom.y;
      if (cell) {
        if (!cell.is_anchor) {
          btn.classList.add("workshop-grid-cell--ext");
          if (isMoveSource) btn.classList.add("workshop-grid-cell--move-source");
          btn.title = isMoveSource ? `${cell.label_zh}（待移动）` : `${cell.label_zh}（占用）— 点击选中设备`;
        } else {
          btn.classList.add("workshop-grid-cell--device");
          btn.classList.add(`workshop-grid-cell--type-${cell.type}`);
          if (isMoveSource) btn.classList.add("workshop-grid-cell--move-source");
          workshopApplyCellStatusClasses(btn, cell);
          const pct = cell.progress_pct ?? 0;
          btn.style.setProperty("--progress-pct", `${pct}%`);
          btn.title = isMoveSource
            ? `${cell.label_zh} — 点击目标格移动（Esc 取消）`
            : (cell.status_zh || "") + " — 双击切换启停";
          btn.innerHTML = `${workshopDeviceIconMarkup(cell.type)}
            <span class="workshop-cell-progress" style="width:${pct}%"></span>`;
        }
      } else if (workshopMoveFrom && moveEntry) {
        if (workshopCanMoveTo(snap, workshopMoveFrom, x, y)) {
          btn.classList.add("workshop-grid-cell--build-valid");
          btn.textContent = "→";
          btn.title = `移动至此处（${moveEntry.label_zh}）`;
        } else {
          btn.classList.add("workshop-grid-cell--build-invalid");
          btn.disabled = true;
          btn.title = "此格无法放置（越界或占用）";
        }
      } else if (workshopBuildType && buildEntry) {
        const canAfford = workshopCanAffordBuild(snap, buildEntry);
        if (workshopCanPlaceAt(snap, x, y, buildEntry) && canAfford) {
          btn.classList.add("workshop-grid-cell--build-valid");
          btn.textContent = "+";
          btn.title = `可放置 ${buildEntry.label_zh}`;
        } else if (workshopCanPlaceAt(snap, x, y, buildEntry) && !canAfford) {
          btn.classList.add("workshop-grid-cell--build-invalid");
          btn.title = `资源不足：${workshopAffordReason(snap, buildEntry)}`;
        } else {
          btn.classList.add("workshop-grid-cell--build-invalid");
          btn.disabled = true;
          btn.title = "此格无法放置（越界或占用）";
        }
      } else {
        btn.classList.add("workshop-grid-cell--empty");
        btn.title = "空格 — 点击建造或查看";
      }
      if (workshopSelected && workshopSelected.x === x && workshopSelected.y === y) {
        btn.classList.add("workshop-grid-cell--selected");
      }
      if (workshopHoverCell && workshopHoverCell.x === x && workshopHoverCell.y === y) {
        btn.classList.add("workshop-grid-cell--hover");
      }
      gridEl.appendChild(btn);
    }
  }

  const links = snap.logistics_links || [];
  if (links.length) {
    svgEl.classList.remove("hidden");
    svgEl.setAttribute("viewBox", `0 0 ${gridSize} ${gridSize}`);
    svgEl.setAttribute("pointer-events", "none");
    svgEl.replaceChildren();
    for (const ln of links) {
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(ln.x0 + 0.5));
      line.setAttribute("y1", String(ln.y0 + 0.5));
      line.setAttribute("x2", String(ln.x1 + 0.5));
      line.setAttribute("y2", String(ln.y1 + 0.5));
      line.setAttribute("class", `workshop-logistics-line workshop-logistics-line--${ln.kind || "storage"}`);
      svgEl.appendChild(line);
    }
  } else {
    svgEl.classList.add("hidden");
    svgEl.replaceChildren();
  }

  const buildList = root.querySelector(".workshop-build-list");
  if (buildList && !root.querySelector(".workshop-build-head")) {
    const buildHead = document.createElement("p");
    buildHead.className = "workshop-build-head";
    buildHead.textContent = "建造 · 消耗基地资源";
    buildList.before(buildHead);
  }
  buildList.replaceChildren();
  for (const d of snap.build_catalog || []) {
    const afford = workshopCanAffordBuild(snap, d);
    const b = document.createElement("button");
    b.type = "button";
    b.disabled = !!snap.abandoned || !afford;
    b.className = `workshop-build-item${workshopBuildType === d.type ? " workshop-build-item--active" : ""}${!afford ? " workshop-build-item--blocked" : ""}`;
    const buildIcon = explorerIconImgHtml(d.type, "workshop-build-item__icon", 22);
    b.innerHTML = `${buildIcon}<strong>${d.label_zh}</strong>${workshopBuildCostHtml(d.build, snap)}`;
    b.title = `建造 ${d.label_zh}：${d.build_cost_zh || workshopBuildCostText(d.build)}（基地资源）`;
    if (!afford) b.title = `资源不足：${workshopAffordReason(snap, d)}`;
    b.addEventListener("click", () => {
      if (!afford) {
        showToast(`资源不足：${workshopAffordReason(snap, d)}`, 3600);
        return;
      }
      workshopBuildType = workshopBuildType === d.type ? null : d.type;
      workshopCancelMoveMode();
      workshopSelected = null;
      renderWorkshopScene(workshopUiSnap);
      if (workshopBuildType) showToast(`放置 ${d.label_zh}`, 2200);
    });
    buildList.appendChild(b);
  }

  refreshWorkshopDeviceDetailPanel(snap, { full: true });

  renderWorkshopInteractionBar(snap);

  const capsWrap = root.querySelector(".workshop-scene-caps");
  const capsList = root.querySelector(".workshop-caps-list");
  const capsEnable = root.querySelector(".workshop-caps-enable-cb");
  capsEnable.checked = snap.stop_caps_enabled !== false;
  capsList.replaceChildren();
  const capKeys = ["parts", "medical_pack", "alloy", "ore", "components"];
  for (const k of capKeys) {
    const row = document.createElement("label");
    row.className = "workshop-cap-row";
    const raw = (snap.stop_caps || {})[k];
    const val = raw != null ? Number(raw) : (WORKSHOP_DEFAULT_STOP_CAPS[k] ?? 0);
    row.innerHTML = `<span>${WORKSHOP_RES_ZH[k] || k}</span><input type="number" min="0" max="9999" data-cap-key="${k}" value="${val}" class="workshop-cap-input" title="0 表示该资源不限产" />`;
    capsList.appendChild(row);
  }
  capsEnable.onchange = () => postWorkshopSetCaps(null, capsEnable.checked);
  capsList.querySelectorAll(".workshop-cap-input").forEach((inp) => {
    inp.onchange = () => {
      const caps = {};
      capsList.querySelectorAll(".workshop-cap-input").forEach((el) => {
        caps[el.dataset.capKey] = parseInt(el.value, 10) || 0;
      });
      postWorkshopSetCaps(caps, capsEnable.checked);
    };
  });

  const tradeWrap = root.querySelector(".workshop-scene-trade");
  const tradeList = root.querySelector(".workshop-trade-list");
  if (snap.comm_trade_available && (snap.trade_offers || []).length) {
    tradeWrap.classList.remove("hidden");
    tradeList.replaceChildren();
    for (const t of snap.trade_offers) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "workshop-btn workshop-btn--ghost workshop-btn--sm";
      b.disabled = snap.abandoned || !t.available;
      b.textContent = t.label_zh;
      b.addEventListener("click", () => postWorkshopTrade(t.id));
      tradeList.appendChild(b);
    }
  } else {
    tradeWrap.classList.add("hidden");
  }

  const fatigueWrap = root.querySelector(".workshop-scene-fatigue");
  const fatigueList = root.querySelector(".workshop-fatigue-list");
  const tired = (snap.npc_fatigue || []).filter((row) => row.needs_rest);
  if (tired.length) {
    fatigueWrap.classList.remove("hidden");
    fatigueList.replaceChildren();
    for (const row of tired) {
      const line = document.createElement("div");
      line.className = "workshop-fatigue-row";
      line.innerHTML = `<span>${row.label_zh}</span>`;
      const rb = document.createElement("button");
      rb.type = "button";
      rb.className = "workshop-btn workshop-btn--sm";
      rb.textContent = "休息";
      rb.addEventListener("click", () => postWorkshopRestNpc(row.id));
      line.appendChild(rb);
      fatigueList.appendChild(line);
    }
  } else {
    fatigueWrap.classList.add("hidden");
  }

  refreshWorkshopTutorialLayout();
}

function onWorkshopCellClick(x, y, cell) {
  if (snapGuardAbandoned()) return;
  if (workshopMoveFrom) {
    if (workshopCanMoveTo(workshopUiSnap, workshopMoveFrom, x, y)) {
      postWorkshopMove(workshopMoveFrom.x, workshopMoveFrom.y, x, y);
      return;
    }
    const anchor = workshopAnchorOf(cell);
    if (anchor && anchor.x === workshopMoveFrom.x && anchor.y === workshopMoveFrom.y) {
      showToast("请点击绿色高亮格作为新位置。", 2400);
      return;
    }
    showToast("此格无法放置设备。", 2400);
    return;
  }
  if (workshopBuildType) {
    const entry = workshopCatalogEntry(workshopUiSnap, workshopBuildType);
    if (!entry) {
      showToast("未知设备类型。", 2400);
      return;
    }
    if (!workshopCanAffordBuild(workshopUiSnap, entry)) {
      showToast(`资源不足：${workshopAffordReason(workshopUiSnap, entry)}`, 3600);
      return;
    }
    if (cell || !workshopCanPlaceAt(workshopUiSnap, x, y, entry)) {
      showToast("此格无法放置设备。", 2400);
      return;
    }
    postWorkshopBuild(x, y, workshopBuildType);
    return;
  }
  const anchor = workshopAnchorOf(cell);
  if (anchor) workshopSelected = { x: anchor.x, y: anchor.y };
  else workshopSelected = { x, y };
  refreshWorkshopSelectionHighlight();
  refreshWorkshopDeviceDetailPanel(workshopUiSnap, { full: true, scroll: true });
  renderWorkshopInteractionBar(workshopUiSnap);
}

function snapGuardAbandoned() {
  if (workshopUiSnap?.abandoned) {
    showToast("工坊已停摆，请先在左侧重启。", 2800);
    return true;
  }
  return false;
}

async function openWorkshopScene(fromId = "west_shaft") {
  setWorkshopLoading(true);
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/enter"), { method: "POST", body: "{}" });
    latestState = data;
    renderMgmtResourcesHud(data.session);
    renderMgmtLogStrip(data.management_recent);
    workshopUiSnap = workshopSnapFromData(data);
    enterWorkshopMapScene(fromId);
    if (workshopUiSnap) renderWorkshopScene(workshopUiSnap);
    maybeStartWorkshopTutorial(workshopUiSnap);
    if (workshopPollTimer != null) clearInterval(workshopPollTimer);
    workshopPollTimer = setInterval(async () => {
      if (!isWorkshopOpen()) {
        clearInterval(workshopPollTimer);
        workshopPollTimer = null;
        return;
      }
      try {
        await syncWorkshopFromResponse(
          await fetchJSON(gameApiUrl("/api/sim/workshop/enter"), { method: "POST", body: "{}" }),
          { soft: true },
        );
      } catch {
        /* ignore poll errors */
      }
    }, 5000);

  } catch (e) {
    showErrorToast(e);
  }
}

async function openWestShaftSimScene(fromId) {
  return openWorkshopScene(fromId);
}

async function postWorkshopConstruct() {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/construct"), { method: "POST", body: "{}" });
    OptimisticWorkshop.clear();
    await syncWorkshopFromResponse(data);
    if (workshopTutorialActive) {
      workshopUiSnap = workshopSnapFromData(data);
      const steps = workshopTutorialSteps(workshopUiSnap);
      const idx = steps.findIndex((s) => s.id === "resources");
      if (idx >= 0) workshopTutorialStep = idx;
      renderWorkshopScene(workshopUiSnap);
      renderWorkshopTutorialStep();
    }
    showToast("基地核心自动化设施改造完成。", 3200);
  } catch (e) {
    OptimisticWorkshop.rollback();
    renderWorkshopScene(workshopUiSnap);
    showErrorToast(e);
    try {
      const st = await fetchJSON(gameApiUrl("/api/state"));
      await syncWorkshopFromResponse(st);
    } catch {
      /* ignore refresh failure */
    }
  }
}

async function postWorkshopBuild(x, y, deviceType) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.build(workshopUiSnap, x, y, deviceType);
  workshopBuildType = null;
  workshopSelected = { x, y };
  renderWorkshopScene(workshopUiSnap);
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/build"), {
      method: "POST",
      body: JSON.stringify({ x, y, device_type: deviceType }),
    });
    OptimisticWorkshop.clear();
    await syncWorkshopFromResponse(data);
    showToast("设备已建造。", 2400);
  } catch (e) {
    OptimisticWorkshop.rollback();
    renderWorkshopScene(workshopUiSnap);
    showErrorToast(e);
    try {
      const st = await fetchJSON(gameApiUrl("/api/state"));
      await syncWorkshopFromResponse(st);
    } catch {
      /* ignore refresh failure */
    }
  }
}

async function postWorkshopUpgrade(x, y) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.upgrade(workshopUiSnap, x, y);
  patchWorkshopGridFromSnap(workshopUiSnap);
  refreshWorkshopDeviceDetailPanel(workshopUiSnap, { full: true });
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/upgrade"), {
        method: "POST",
        body: JSON.stringify({ x, y }),
      }),
      { soft: true, full: true },
    );
    OptimisticWorkshop.clear();
  } catch (e) {
    OptimisticWorkshop.rollback();
    patchWorkshopGridFromSnap(workshopUiSnap);
    refreshWorkshopDeviceDetailPanel(workshopUiSnap, { full: true });
    showErrorToast(e);
  }
}

async function postWorkshopDemolish(x, y) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.demolish(workshopUiSnap, x, y);
  workshopSelected = null;
  workshopCancelMoveMode();
  renderWorkshopScene(workshopUiSnap);
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/demolish"), {
        method: "POST",
        body: JSON.stringify({ x, y }),
      }),
    );
    OptimisticWorkshop.clear();
  } catch (e) {
    OptimisticWorkshop.rollback();
    renderWorkshopScene(workshopUiSnap);
    showErrorToast(e);
  }
}

async function postWorkshopMove(fromX, fromY, toX, toY) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.move(workshopUiSnap, fromX, fromY, toX, toY);
  workshopCancelMoveMode();
  workshopSelected = { x: toX, y: toY };
  renderWorkshopScene(workshopUiSnap);
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/move"), {
      method: "POST",
      body: JSON.stringify({ from_x: fromX, from_y: fromY, to_x: toX, to_y: toY }),
    });
    OptimisticWorkshop.clear();
    await syncWorkshopFromResponse(data);
    showToast("设备已移动。", 2400);
  } catch (e) {
    OptimisticWorkshop.rollback();
    renderWorkshopScene(workshopUiSnap);
    showErrorToast(e);
    try {
      const st = await fetchJSON(gameApiUrl("/api/state"));
      await syncWorkshopFromResponse(st);
    } catch {
      /* ignore refresh failure */
    }
  }
}

async function postWorkshopToggle(x, y) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.toggle(workshopUiSnap, x, y);
  updateWorkshopLiveData(workshopUiSnap, { soft: true, full: true });
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/toggle"), {
        method: "POST",
        body: JSON.stringify({ x, y }),
      }),
      { soft: true, full: true },
    );
    OptimisticWorkshop.clear();
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true, full: true });
    showErrorToast(e);
  }
}

async function postWorkshopAssignNpc(x, y, npcId) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.assignNpc(workshopUiSnap, x, y, npcId);
  updateWorkshopLiveData(workshopUiSnap, { soft: true });
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/assign_npc"), {
        method: "POST",
        body: JSON.stringify({ x, y, npc_id: npcId }),
      }),
      { soft: true },
    );
    OptimisticWorkshop.clear();
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopSetRecipe(x, y, recipe) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.setRecipe(workshopUiSnap, x, y, recipe);
  updateWorkshopLiveData(workshopUiSnap, { soft: true });
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/set_recipe"), {
      method: "POST",
      body: JSON.stringify({ x, y, recipe }),
    });
    OptimisticWorkshop.clear();
    await syncWorkshopFromResponse(data, { soft: true, full: true });
    const dev = workshopSelectedDevice(workshopUiSnap);
    if (dev?.type === "printer") {
      showToast(`3D 打印机已切换为${dev.recipe_zh || workshopPrinterRecipeLabel(dev.recipe)}。`, 2600);
    }
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopDelegate(enabled) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.delegate(workshopUiSnap, enabled);
  updateWorkshopLiveData(workshopUiSnap, { soft: true });
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/delegate"), {
        method: "POST",
        body: JSON.stringify({ enabled }),
      }),
      { soft: true },
    );
    OptimisticWorkshop.clear();
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopImportOre(amount) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.importOre(workshopUiSnap, amount);
  updateWorkshopLiveData(workshopUiSnap, { soft: true });
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/import_source_ore"), {
        method: "POST",
        body: JSON.stringify({ amount }),
      }),
      { soft: true },
    );
    OptimisticWorkshop.clear();
    showToast("源矿已导入工坊缓冲。", 2400);
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopExport(resource, amount) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/export"), {
      method: "POST",
      body: JSON.stringify({ resource, amount }),
    });
    OptimisticWorkshop.clear();
    await syncWorkshopFromResponse(data, { soft: true });
    const result = data.export_result || {};
    const exported = Object.entries(result).map(([k, v]) => {
      const label = { parts: "零件", medical: "医疗包" }[k] || k;
      return `${label} ×${v}`;
    }).join("、");
    showToast(exported ? `${exported} 已运回基地。` : "物资已运回基地。", 2400);
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopSetCaps(caps, enabled) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  OptimisticWorkshop.setCaps(workshopUiSnap, caps, enabled);
  updateWorkshopLiveData(workshopUiSnap, { soft: true });
  try {
    const body = {};
    if (caps) body.caps = caps;
    if (enabled != null) body.enabled = enabled;
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/set_caps"), {
        method: "POST",
        body: JSON.stringify(body),
      }),
      { soft: true },
    );
    OptimisticWorkshop.clear();
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopDeliverTask(taskId) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/deliver_task"), {
      method: "POST",
      body: JSON.stringify({ task_id: taskId }),
    });
    OptimisticWorkshop.clear();
    await syncWorkshopFromResponse(data, { soft: true });
    const delivery = data.delivery_result || {};
    let msg = "生产指标已交付。";
    if (delivery.reward_zh) msg += ` 获得 ${delivery.reward_zh}`;
    if (delivery.reveal_zh) msg += ` ${delivery.reveal_zh}`;
    showToast(msg, delivery.reveal_zh ? 5200 : 3600);
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopTrade(tradeId) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/workshop/trade"), {
      method: "POST",
      body: JSON.stringify({ trade_id: tradeId }),
    });
    OptimisticWorkshop.clear();
    await syncWorkshopFromResponse(data, { soft: true });
    showToast("通讯阵列交易完成。", 2600);
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopRestNpc(npcId) {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  const npcLabel = (workshopUiSnap?.npc_fatigue || []).find((r) => r.id === npcId)?.label_zh || npcId;
  OptimisticWorkshop.restNpc(workshopUiSnap, npcId);
  updateWorkshopLiveData(workshopUiSnap, { soft: true });
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/rest_npc"), {
        method: "POST",
        body: JSON.stringify({ npc_id: npcId }),
      }),
      { soft: true },
    );
    OptimisticWorkshop.clear();
    showToast(`${npcLabel}已安排休息，疲劳清零。设备已撤下，委任自动分配已暂停。`, 3200);
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

async function postWorkshopRehabilitate() {
  OptimisticWorkshop.save();
  setWorkshopLoading(true);
  try {
    await syncWorkshopFromResponse(
      await fetchJSON(gameApiUrl("/api/sim/workshop/rehabilitate"), { method: "POST", body: "{}" }),
    );
    OptimisticWorkshop.clear();
    showToast("基地核心自动化设施已重新启动。", 3200);
  } catch (e) {
    OptimisticWorkshop.rollback();
    updateWorkshopLiveData(workshopUiSnap, { soft: true });
    showErrorToast(e);
  }
}

/** 基地日 +1：推进世界天数，结算远征归国与资源生产 */
async function postAdvanceWorldDay() {
  try {
    const data = await fetchJSON(gameApiUrl("/api/sim/advance_world_day"), { method: "POST", body: "{}" });
    const wd = data?.world_day_after ?? data?.sandbox?.world_day ?? data?.narrative?.world_day ?? "?";
    // 检查是否自动恢复到了剧情节拍
    const newPhase = data?.sandbox?.story_phase || data?.session?.story_phase || "";
    if (String(newPhase).trim() !== "Sandbox") {
      showToast(`休整结束——已推进至第 ${wd} 日，回归剧情节拍。`, 4200);
    } else {
      showToast(`基地日推进至第 ${wd} 日${data?.expeditions_settled ? " · 远征归国已结算" : ""}`, 3200);
    }
    // 刷新全局状态
    latestState = data;
    renderObjectivesPanel(data);
    renderMgmtResourcesHud(data.session);
    renderMgmtLogStrip(data.management_recent);
    renderSandboxDock(data);
    npcScheduleSnapshot = scheduledNpcWorldPositions(data);
    syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
    await refreshTopBar();
  } catch (e) {
    showErrorToast(e);
  }
}

async function postDecryptDatastick(via) {
  await fetchJSON(gameApiUrl("/api/narrative/action"), {
    method: "POST",
    body: JSON.stringify({ kind: "decrypt_datastick", via }),
  });
  showToast("加密数据棒解密流程已完成，可推进至下一段剧情。", 3400);
  await refreshOpenStoryPanel();
}

/** 开发者模式：左下角 DEV 按钮 + 一键跳转面板（无需 ?debug=1） */
let devPanelVisible = false;

async function postDebugJumpNode(nodeId, resetCompleted = true) {
  const data = await fetchJSON(gameApiUrl("/api/debug/jump_node"), {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId, reset_completed: resetCompleted }),
  });
  showToast(`已跳转节点 → ${data.jumped_to || nodeId}`, 3400);
  latestState = data;
  await refreshOpenStoryPanel();
}

function initDevPanel() {
  // ── DEV 切换按钮 ──
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "dev-panel-toggle";
  toggle.textContent = "DEV";
  toggle.title = "开发者模式 · 剧情节点跳转";
  toggle.setAttribute("aria-label", "切换开发者面板");

  // ── 面板 ──
  const panel = document.createElement("aside");
  panel.className = "dev-panel";
  panel.setAttribute("aria-label", "开发者：剧情节点跳转");

  // 面板头部
  const header = document.createElement("div");
  header.className = "dev-panel__header";
  const panelTitle = document.createElement("span");
  panelTitle.className = "dev-panel__title";
  panelTitle.textContent = "🛠 开发者模式";
  const currentBadge = document.createElement("span");
  currentBadge.className = "dev-panel__current";
  currentBadge.id = "dev-panel-current-node";
  currentBadge.textContent = "当前：—";
  header.appendChild(panelTitle);
  header.appendChild(currentBadge);
  panel.appendChild(header);

  // 节点选择行
  const selectRow = document.createElement("div");
  selectRow.className = "dev-panel__select-row";
  const select = document.createElement("select");
  select.className = "dev-panel__select";
  select.id = "dev-node-select";
  select.setAttribute("aria-label", "选择剧情节点");

  // 加载中占位
  const loadingOpt = document.createElement("option");
  loadingOpt.value = "";
  loadingOpt.textContent = "加载节点列表中…";
  select.appendChild(loadingOpt);

  const jumpBtn = document.createElement("button");
  jumpBtn.type = "button";
  jumpBtn.className = "dev-panel__btn";
  jumpBtn.textContent = "跳转";
  jumpBtn.title = "跳转到所选节点";

  selectRow.appendChild(select);
  selectRow.appendChild(jumpBtn);
  panel.appendChild(selectRow);

  // 选项行
  const optRow = document.createElement("div");
  optRow.className = "dev-panel__row";
  const chkLabel = document.createElement("label");
  chkLabel.className = "dev-panel__chk";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = true;
  cb.id = "dev-reset-completed";
  chkLabel.appendChild(cb);
  chkLabel.appendChild(document.createTextNode("清空已完成列表"));
  optRow.appendChild(chkLabel);
  panel.appendChild(optRow);

  // 操作按钮行
  const btnRow = document.createElement("div");
  btnRow.className = "dev-panel__row";

  const refreshNodesBtn = document.createElement("button");
  refreshNodesBtn.type = "button";
  refreshNodesBtn.className = "dev-panel__btn";
  refreshNodesBtn.textContent = "刷新列表";
  refreshNodesBtn.title = "重新加载节点列表并更新当前节点";

  const resetBtn = document.createElement("button");
  resetBtn.type = "button";
  resetBtn.className = "dev-panel__btn dev-panel__btn--danger";
  resetBtn.textContent = "重置存档";
  resetBtn.title = "清除所有存档数据并刷新";

  btnRow.appendChild(refreshNodesBtn);
  btnRow.appendChild(resetBtn);
  panel.appendChild(btnRow);

  // 提示
  const hint = document.createElement("p");
  hint.className = "dev-panel__hint";
  hint.id = "dev-panel-hint";
  hint.textContent = "服务端需 GAME_DEBUG_API=1 才能使用跳转功能。";
  panel.appendChild(hint);

  // ── 切换逻辑 ──
  toggle.addEventListener("click", () => {
    devPanelVisible = !devPanelVisible;
    if (devPanelVisible) {
      panel.classList.add("visible");
      toggle.classList.add("active");
      loadDebugNodes(select, hint);
      updateDevCurrentNode(currentBadge);
    } else {
      panel.classList.remove("visible");
      toggle.classList.remove("active");
    }
  });

  // 跳转按钮
  jumpBtn.addEventListener("click", async () => {
    const nid = select.value;
    if (!nid) return;
    try {
      await postDebugJumpNode(nid, cb.checked);
      updateDevCurrentNode(currentBadge);
    } catch (e) {
      showErrorToast(e, 5200);
    }
  });

  // 下拉框选中时也触发跳转（双击或Enter）
  select.addEventListener("dblclick", async () => {
    const nid = select.value;
    if (!nid) return;
    try {
      await postDebugJumpNode(nid, cb.checked);
      updateDevCurrentNode(currentBadge);
    } catch (e) {
      showErrorToast(e, 5200);
    }
  });

  // 刷新按钮
  refreshNodesBtn.addEventListener("click", () => {
    loadDebugNodes(select, hint);
    updateDevCurrentNode(currentBadge);
  });

  // 重置按钮
  resetBtn.addEventListener("click", () => clearSaveAndReset());

  document.body.appendChild(toggle);
  document.body.appendChild(panel);

  // 不再无条件预加载 debug 节点列表（生产环境 GAME_DEBUG_API=0 会导致 403）。
  // 用户点击 DEV 按钮时才会按需加载。

  // 定时更新当前节点显示
  setInterval(() => {
    if (devPanelVisible) {
      updateDevCurrentNode(currentBadge);
    }
  }, 5000);
}

/** 从 /api/debug/story_graph 加载节点并填充 select */
async function loadDebugNodes(select, hintEl) {
  try {
    const data = await fetchJSON(gameApiUrl("/api/debug/story_graph"));
    if (!data.ok) {
      hintEl.textContent = "⚠ 服务端未启用 GAME_DEBUG_API，跳转将返回 403。";
      hintEl.className = "dev-panel__hint dev-panel__hint--warn";
      return;
    }
    hintEl.textContent = `共 ${data.nodes.length} 个剧情节点，按幕分组。选中后点击「跳转」或双击选项。`;
    hintEl.className = "dev-panel__hint";

    // 按 act 分组
    const actOrder = ["prologue", "act1", "act2", "act3", "finale"];
    const actLabels = {
      prologue: "序幕",
      act1: "第一幕",
      act2: "第二幕",
      act3: "第三幕",
      finale: "终章",
    };
    const groups = {};
    for (const act of actOrder) {
      groups[act] = [];
    }
    groups["_other"] = [];
    for (const n of data.nodes) {
      if (groups[n.act]) {
        groups[n.act].push(n);
      } else {
        groups["_other"].push(n);
      }
    }

    // 构造 select options
    select.innerHTML = "";
    const noneOpt = document.createElement("option");
    noneOpt.value = "";
    noneOpt.textContent = "— 选择节点跳转 —";
    noneOpt.disabled = true;
    select.appendChild(noneOpt);

    // 当前节点标记
    const currentId = data.current_node_id;

    for (const act of [...actOrder, "_other"]) {
      const nodes = groups[act] || [];
      if (nodes.length === 0) continue;
      const grp = document.createElement("optgroup");
      grp.label = actLabels[act] || act;
      for (const n of nodes) {
        const opt = document.createElement("option");
        opt.value = n.node_id;
        const marker = n.node_id === currentId ? "★ " : "";
        opt.textContent = `${marker}${n.node_id}　${n.title_zh}`;
        if (n.node_id === currentId) {
          opt.style.fontWeight = "bold";
          opt.style.color = "#7eb8da";
        }
        grp.appendChild(opt);
      }
      select.appendChild(grp);
    }
  } catch (e) {
    hintEl.textContent = "⚠ 无法连接服务端加载节点列表。";
    hintEl.className = "dev-panel__hint dev-panel__hint--warn";
  }
}

/** 更新当前节点徽章 */
function updateDevCurrentNode(badgeEl) {
  if (!latestState || !latestState.narrative) return;
  const n = latestState.narrative;
  badgeEl.textContent = `当前：${n.node_id}《${n.title_zh}》`;
}

/** 地址栏加 ?debug=1 时显示（向后兼容旧版，已废弃——请直接点击左下角 DEV 按钮） */
function initDebugJumpBar() {
  // 旧版 ?debug=1 不再渲染，统一使用 DEV 按钮
  // 但保持函数存在以免报错
}

/**
 * 背景音乐控制
 * - 浏览器要求用户交互后才能播放音频，因此监听首次点击/按键来启动 BGM
 * - 右下角 ♪ 按钮可随时开关
 * - 状态持久化到 localStorage
 */
const BGM_LS_KEY = "epoch_explorer_bgm_enabled_v1";
let bgmAudio = null;
let bgmToggleBtn = null;
let bgmUserEnabled = true; // 默认开启
let bgmInteractionPrimed = false;

// 用新的 dev panel 替换旧的 debug jump bar 初始化
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { initDevPanel(); initBgm(); });
} else {
  initDevPanel();
  initBgm();
}

function initBgm() {
  bgmAudio = document.getElementById("bgm");
  bgmToggleBtn = document.getElementById("bgm-toggle");
  if (!bgmAudio || !bgmToggleBtn) return;

  // 读取用户偏好
  try {
    const saved = localStorage.getItem(BGM_LS_KEY);
    if (saved === "0") bgmUserEnabled = false;
  } catch { /* ignore */ }

  // 音量柔和
  bgmAudio.volume = 0.35;

  // 更新按钮外观
  syncBgmToggleUI();

  // 按钮点击：开关
  bgmToggleBtn.addEventListener("click", (ev) => {
    ev.stopPropagation();
    bgmUserEnabled = !bgmUserEnabled;
    try { localStorage.setItem(BGM_LS_KEY, bgmUserEnabled ? "1" : "0"); } catch { /* ignore */ }
    bgmInteractionPrimed = true;
    applyBgmPlayState();
    syncBgmToggleUI();
  });

  // 首次用户交互（任意点击/按键）启动 BGM
  const prime = () => {
    if (bgmInteractionPrimed) return;
    bgmInteractionPrimed = true;
    applyBgmPlayState();
  };
  document.addEventListener("click", prime, { once: false });
  document.addEventListener("keydown", prime, { once: false });
  document.addEventListener("touchstart", prime, { once: false, passive: true });

  // 同时尝试自动播放（部分桌面浏览器允许静音自动播放，然后用户在交互后取消静音也没用，所以只能等交互）
  // 如果浏览器策略允许（如用户之前已互动过其他标签页），则直接播放
  bgmAudio.play().then(() => {
    if (!bgmUserEnabled) {
      bgmAudio.pause();
    }
    bgmInteractionPrimed = true;
    syncBgmToggleUI();
  }).catch(() => {
    // 自动播放被阻止，等待用户交互
  });
}

function applyBgmPlayState() {
  if (!bgmAudio) return;
  if (bgmUserEnabled) {
    bgmAudio.play().catch(() => {});
  } else {
    bgmAudio.pause();
  }
}

function syncBgmToggleUI() {
  if (!bgmToggleBtn || !bgmAudio) return;
  const playing = !bgmAudio.paused;
  if (playing) {
    bgmToggleBtn.classList.add("bgm-toggle--playing");
    bgmToggleBtn.innerHTML = "♫";
    bgmToggleBtn.setAttribute("aria-label", "关闭背景音乐");
  } else {
    bgmToggleBtn.classList.remove("bgm-toggle--playing");
    bgmToggleBtn.innerHTML = "♪";
    bgmToggleBtn.setAttribute("aria-label", "开启背景音乐");
  }
}

function showToast(msg, ms = 2800) {
  toast = msg;
  toastUntil = performance.now() + ms;
}

/** 用户友好的错误提示，不暴露技术细节 */
function showErrorToast(e, ms = 4200) {
  const msg = e?.message || String(e || "");
  const friendly =
    msg.includes("fetch") || msg.includes("Network") || msg.includes("Failed") ?
      "网络连接异常，请检查服务是否正常运行。" :
    msg.includes("403") ?
      "操作未授权（当前服务未启用调试模式）。" :
    msg.includes("404") ?
      "请求的资源不存在，请刷新页面后重试。" :
    msg.includes("500") ?
      "服务器处理出错，请稍后重试。" :
    msg.includes("JSON") ?
      "数据解析异常，请刷新页面后重试。" :
      "操作失败，请稍后重试。";
  console.warn("[用户提示]", friendly, "→ 原始错误:", msg);
  showToast(friendly, ms);
}

/** Canvas HUD：圆角矩形（需浏览器支持 path.roundRect） */
function hudRoundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, rr);
}

function openStoryUI() {
  storyBackdrop.classList.remove("hidden");
  storyBackdrop.setAttribute("aria-hidden", "false");
}

function closeStoryUI() {
  cancelNpcDialogueReveal();
  // 结束自由对话
  if (chatActiveNpcId) {
    fetchJSON(gameApiUrl("/api/npc/chat"), {
      method: "POST",
      body: JSON.stringify({ npc_id: chatActiveNpcId, action: "end" }),
    }).catch(() => {});
  }
  teardownChatUI();
  closeChatHistory();
  storyBackdrop.classList.add("hidden");
  storyBackdrop.setAttribute("aria-hidden", "true");
  storyBody.classList.remove("story-body--npc-dialogue");
  storyExtras.innerHTML = "";
  storyChoices.innerHTML = "";
  storyMeta.innerHTML = "";
  storyTextbox.classList.remove("story-textbox--choices");
  storyTextbox.classList.remove("story-textbox--advancing");
  storyAiLine.classList.remove("story-ai-line--advance-hint");
  if (storyAdvanceHint) storyAdvanceHint.classList.add("hidden");
  storyPortraitKind = "";
  storyPortraitId = "";
  storyPortraitLabel = "";
  storySpriteBlock.style.background = "#3d4f66";
  storySpriteLabel.textContent = "";
  if (storyPortraitImgEl) {
    storyPortraitImgEl.hidden = true;
    storyPortraitImgEl.removeAttribute("src");
  }
  setStorySpriteColumnVisible(true);
  storyAiLine.textContent = "";
  setStoryChoicesLocked(false);
}

function renderBullets(lines) {
  storyBullets.innerHTML = "";
  for (const line of lines || []) {
    const li = document.createElement("li");
    li.textContent = line;
    storyBullets.appendChild(li);
  }
}

async function postChoice(choiceId) {
  const data = await fetchJSON(gameApiUrl("/api/choice"), {
    method: "POST",
    body: JSON.stringify({ choice_id: choiceId }),
  });
  showToast("已选择，剧情推进中…");
  closeStoryUI();
  await refreshTopBar();
}

async function postAdvance() {
  const data = await fetchJSON(gameApiUrl("/api/advance"), { method: "POST", body: "{}" });
  showToast("已推进至下一阶段。");
  closeStoryUI();
  await refreshTopBar();
}

function lockTypeLabelZh(lockType) {
  const m = { story: "剧情锁", info: "信息锁", ability: "能力锁", resource: "资源锁", time: "时机锁", none: "" };
  return m[lockType] || lockType || "";
}

function renderDossierPanel(state) {
  const el = document.getElementById("objectives-dossier");
  if (!el) return;
  el.replaceChildren();
  const pre = document.createElement("p");
  pre.className = "objectives-note";
  pre.textContent =
    "记忆碎片：展示 NPC 信任、由系统汇总的印象语，以及最近写入的长期记忆摘录；随对话与经营累积。";
  el.appendChild(pre);
  const rows = state?.overworld_npcs || [];
  let any = false;
  for (const r of rows) {
    if (!r.visible) continue;
    any = true;
    const card = document.createElement("div");
    card.className = "dossier-card";
    const head = document.createElement("div");
    head.className = "dossier-card__head";
    const roam = r.roaming_location_zh ? ` · 现址≈${r.roaming_location_zh}` : "";
    head.textContent = `${r.name || r.id} · 信任 ${r.trust ?? "?"}${roam}`;
    card.appendChild(head);
    if (r.impression_zh) {
      const imp = document.createElement("div");
      imp.className = "dossier-card__imp";
      imp.textContent = r.impression_zh;
      card.appendChild(imp);
    }
    const frag = r.memory_fragments_zh || [];
    if (frag.length) {
      const ul = document.createElement("ul");
      ul.className = "dossier-frags";
      for (const line of frag) {
        const li = document.createElement("li");
        li.textContent = String(line);
        ul.appendChild(li);
      }
      card.appendChild(ul);
    } else {
      const empty = document.createElement("div");
      empty.className = "dossier-empty";
      empty.textContent = "（长期记忆尚空；与角色对话或关键经营后会写入摘录）";
      card.appendChild(empty);
    }
    el.appendChild(card);
  }
  if (!any) {
    const p = document.createElement("p");
    p.className = "objectives-note";
    p.textContent = "当前无大地图可见角色；推进剧情后将显示档案条目。";
    el.appendChild(p);
  }
}

function renderExploreLocks(state) {
  const el = document.getElementById("objectives-explore");
  if (!el) return;
  el.replaceChildren();
  const sess = state?.session || {};
  const wc = state?.world_clock || {};
  const clockZh = wc.display_zh || "—";
  const plotFlags = new Set(sess.plot?.flags || []);
  const needLight = !plotFlags.has("floodlight_equipped") && !plotFlags.has("mine_deep_lit");

  const intro = document.createElement("p");
  intro.className = "objectives-note";
  intro.textContent =
    "世界时间与门禁：海岸线洞穴于游戏内 21:00–次日 5:00 开放；废弃矿场深层需 500 能源购工业探照灯，或通过经营「加大开采深度」等解锁照明。";
  el.appendChild(intro);

  const row = document.createElement("div");
  row.className = "explore-clock-bar";

  const lab = document.createElement("span");
  lab.className = "explore-clock-label";
  lab.textContent = `当前 ${clockZh}`;
  row.appendChild(lab);

  async function bumpClock(mins) {
    try {
      const j = await postAdvanceClockMinutes(mins);
      if (!j?.ok) return;
      const st = await fetchJSON(gameApiUrl("/api/state"));
      latestState = st;
      // 时间推进后立即保存到 localStorage
      persistSessionToLocalStorage();
      renderObjectivesPanel(st);
      renderMgmtResourcesHud(st.session);
      renderMgmtLogStrip(st.management_recent);
      renderSandboxDock(st);
      npcScheduleSnapshot = scheduledNpcWorldPositions(st);
      syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
      showToast(`时间推进 ${mins} 分钟`, 3200);
    } catch (e) {
      showErrorToast(e, 5200);
    }
  }

  function mkBtn(label, mins) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "sandbox-dock__btn";
    b.textContent = label;
    b.addEventListener("click", () => bumpClock(mins));
    return b;
  }

  row.appendChild(mkBtn("+30分", 30));
  row.appendChild(mkBtn("+2时", 120));
  row.appendChild(mkBtn("+6时", 360));
  el.appendChild(row);

  if (needLight) {
    const wrap = document.createElement("div");
    wrap.className = "explore-floodlight";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "sandbox-dock__btn sandbox-dock__btn--primary";
    b.textContent = "购置工业探照灯（−500 能源）";
    b.addEventListener("click", async () => {
      try {
        const j = await postPurchaseFloodlight();
        if (!j?.ok) return;
        const st = await fetchJSON(gameApiUrl("/api/state"));
        latestState = st;
        renderObjectivesPanel(st);
        renderMgmtResourcesHud(st.session);
        renderMgmtLogStrip(st.management_recent);
        renderSandboxDock(st);
        npcScheduleSnapshot = scheduledNpcWorldPositions(st);
        syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
        showToast("探照灯已到位：废弃矿场深层可进。", 4800);
      } catch (e) {
        showErrorToast(e, 6200);
      }
    });
    wrap.appendChild(b);
    el.appendChild(wrap);
  }
}

function renderMgmtResourcesHud(session) {
  const el = document.getElementById("resource-strip");
  if (!el) return;
  if (!session?.resources) {
    el.className = "resource-strip resource-strip--empty";
    el.textContent = "基地资源：等待会话同步…";
    return;
  }
  const r = session.resources;
  const morale = session.morale ?? 75;
  // 士气颜色
  let moraleColor = "#4caf50";
  if (morale < 40) moraleColor = "#f44336";
  else if (morale < 60) moraleColor = "#ff9800";
  el.className = "resource-strip";
  const chip = (resKey, label, val) => {
    const ik = RESOURCE_STRIP_ICON_KEY[resKey];
    const icon = ik ? explorerIconImgHtml(ik, "resource-strip__icon", 18) : "";
    return `<div class="resource-strip__chip" role="listitem">${icon}<span class="resource-strip__k">${label}</span><span class="resource-strip__v">${val}</span></div>`;
  };
  el.innerHTML = `
    <span class="resource-strip__title">基地资源</span>
    <div class="resource-strip__chips" role="list">
      ${chip("energy", "能源", r.energy)}
      ${chip("food", "补给", r.food)}
      ${chip("medical", "医疗", r.medical)}
      ${chip("intel", "情报", r.intel)}
      ${chip("parts", "零件", r.parts ?? 0)}
    </div>
    <div class="resource-strip__morale" title="基地士气">
      <span class="resource-strip__k">士气</span>
      <span class="resource-strip__morale-bar" style="background:${moraleColor}22">
        <span class="resource-strip__morale-fill" style="width:${morale}%;background:${moraleColor}"></span>
      </span>
      <span class="resource-strip__v" style="color:${moraleColor}">${morale}</span>
    </div>`;
}

function renderSandboxDock(state) {
  if (!sandboxDock) return;
  const sess = state?.session || {};
  const sb = state?.sandbox || {};
  const phaseRaw = sess.story_phase || sb.story_phase || "StoryBeat";
  const phase = String(phaseRaw).trim();
  const sandboxOpsUnlocked = sb.sandbox_ops_unlocked === true;

  // 静默玩法教程入口已移除（内容已整合到基地核心）
  const dockTopTools = document.querySelector(".objectives-panel__top-tools");
  if (dockTopTools) dockTopTools.classList.add("hidden");

  sandboxDock.classList.remove("hidden");
  sandboxDock.classList.remove("sandbox-dock--operating", "sandbox-dock--beat");
  sandboxDock.classList.toggle("sandbox-dock--operating", phase === "Sandbox");
  sandboxDock.classList.toggle("sandbox-dock--beat", phase !== "Sandbox");
  sandboxDock.replaceChildren();

  // 状态行：相位徽标 + 基础日
  const row = document.createElement("div");
  row.className = "sandbox-dock__title-row";
  const wd = Number(sess.world_day ?? sb.world_day ?? 1);
  const autoResume = (phase === "Sandbox") && Boolean(sb.sandbox_auto_resume);
  const badge = document.createElement("span");
  badge.className = `sandbox-dock__badge ${phase === "Sandbox" ? "sandbox-dock__badge--sandbox" : "sandbox-dock__badge--beat"}`;
  badge.textContent = phase === "Sandbox" ? (autoResume ? "休整期" : "静默运营") : "剧情节拍";
  row.appendChild(badge);

  const meta = document.createElement("span");
  meta.className = "sandbox-dock__meta";
  meta.textContent = `第 ${wd} 日`;
  row.appendChild(meta);
  sandboxDock.appendChild(row);

  // 切换按钮
  const actions = document.createElement("div");
  actions.className = "sandbox-dock__actions";

  async function syncAfterSim(fn) {
    try {
      const fnRet = await fn();
      const st = await fetchJSON(gameApiUrl("/api/state"));
      latestState = st;
      renderObjectivesPanel(st);
      renderMgmtResourcesHud(st.session);
      renderMgmtLogStrip(st.management_recent);
      renderSandboxDock(st);
      npcScheduleSnapshot = scheduledNpcWorldPositions(st);
      syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
      return { fnRet, st };
    } catch (e) {
      showErrorToast(e, 5200);
      return undefined;
    }
  }

  // Sandbox 中始终显示「基地日 +1」
  if (phase === "Sandbox") {
    // 剩余天数提示（自动休整期显示）
    const rem = sb.sandbox_min_remaining_days;
    if (autoResume && rem !== undefined && rem !== null) {
      const remEl = document.createElement("div");
      remEl.className = "sandbox-dock__remain";
      remEl.textContent = rem > 0 ? `仍需运营 ${rem} 个基地日方可推进主线。` : "休整期已满，再推进一日将自动回归主线。";
      actions.appendChild(remEl);
    }
    // 基地日 +1 按钮
    const bDay = document.createElement("button");
    bDay.type = "button";
    bDay.className = "sandbox-dock__btn sandbox-dock__btn--primary sandbox-dock__btn--fat";
    bDay.textContent = "基地日 +1";
    bDay.title = "推进一个世界日：结算远征归国与资源生产。";
    bDay.addEventListener("click", () => postAdvanceWorldDay());
    actions.appendChild(bDay);
  }

  if (phase !== "Sandbox") {
    if (!sandboxOpsUnlocked) {
      const lock = document.createElement("div");
      lock.className = "sandbox-dock__locked-hint";
      lock.textContent = "静默尚未解锁，请推进主线。";
      actions.appendChild(lock);
    } else {
      const bEnter = document.createElement("button");
      bEnter.type = "button";
      bEnter.className = "sandbox-dock__btn sandbox-dock__btn--primary sandbox-dock__btn--fat";
      bEnter.textContent = "进入静默";
      bEnter.title = "完成每个章节/幕后会自动进入休整期；也可随时手动进入。";
      bEnter.addEventListener("click", () =>
        syncAfterSim(async () => {
          await fetchJSON(gameApiUrl("/api/sim/enter_sandbox"), {
            method: "POST",
            body: JSON.stringify({}),
          });
          showToast("已进入静默运营 · 经营操作请前往基地核心。", 4200);
        }),
      );
      actions.appendChild(bEnter);
    }
  } else if (!autoResume) {
    // 仅手动静默期显示退出按钮；自动休整期不显示，沉浸式自然过渡
    const bExit = document.createElement("button");
    bExit.type = "button";
    bExit.className = "sandbox-dock__btn sandbox-dock__btn--fat";
    bExit.textContent = "结束静默";
    bExit.addEventListener("click", () =>
      syncAfterSim(async () => {
        await fetchJSON(gameApiUrl("/api/sim/exit_sandbox"), {
          method: "POST",
          body: JSON.stringify({ force: false }),
        });
        showToast("已恢复剧情节拍。", 4200);
      }),
    );
    actions.appendChild(bExit);
  }
  sandboxDock.appendChild(actions);
}

function renderMgmtLogStrip(recent) {
  const el = document.getElementById("objectives-mgmt-log");
  if (!el) return;
  el.replaceChildren();
  if (!recent || recent.length === 0) {
    const p = document.createElement("p");
    p.className = "objectives-note";
    p.textContent = "尚无刻录的经营决议。";
    el.appendChild(p);
    return;
  }
  for (const row of recent) {
    const d = document.createElement("div");
    d.className = "objectives-mgmt-row";
    d.textContent = row.label_zh || row.tag || "";
    el.appendChild(d);
  }
}

function renderObjectivesPanel(state) {
  if (!objectivesCurrent || !objectivesUpcoming) return;
  objectivesCurrent.replaceChildren();
  objectivesUpcoming.replaceChildren();
  renderExploreLocks(state);
  renderDossierPanel(state);
  if (!state?.narrative) return;

  const nar = state.narrative;
  const tag = document.createElement("div");
  tag.className = "objectives-node-tag";
  tag.textContent = `${nar.node_id} · ${nar.title_zh}`;
  objectivesCurrent.appendChild(tag);

  const ul = document.createElement("ul");
  ul.className = "objectives-list";
  const deliver = nar.objectives_player_zh || [];
  if (deliver.length === 0) {
    const li = document.createElement("li");
    li.textContent = "（本节点暂无结构化目标条目）";
    ul.appendChild(li);
  } else {
    for (const t of deliver) {
      const li = document.createElement("li");
      li.textContent = t;
      ul.appendChild(li);
    }
  }
  objectivesCurrent.appendChild(ul);

  // 若当前节点需要走访设施确认选择，在目标列表下方给出指引
  const hints = nar.facility_hints || {};
  const choiceFacilities = [];
  for (const [fid, h] of Object.entries(hints)) {
    if (h?.upgrade_choice_id && fid !== "command") {
      const fac = FACILITIES.find((f) => f.id === fid);
      if (fac) choiceFacilities.push(fac.name);
    }
  }
  if (choiceFacilities.length > 0) {
    const cmdName = (FACILITIES.find((f) => f.id === "command") || {}).name || "指挥中心";
    const guide = document.createElement("p");
    guide.className = "objectives-note";
    guide.style.cssText = "color:#c8e0f0;margin-top:6px;";
    const list = choiceFacilities.join("」、「");
    guide.textContent = `👉 前往「${list}」确认优先升级此项，也可在「${cmdName}」阅览全部选项。`;
    objectivesCurrent.appendChild(guide);
  }

  const blurb = nar.objectives_upcoming_blurb_zh;
  if (blurb) {
    const bp = document.createElement("p");
    bp.className = "objectives-note";
    bp.textContent = blurb;
    objectivesUpcoming.appendChild(bp);
    return;
  }

  const note = document.createElement("p");
  note.className = "objectives-note";
  if (nar.node_id === "FIN-02") {
    note.textContent = "做出最终选择以进入对应结局。";
  } else if (nar.node_id === "FIN-03") {
    note.textContent = "结局演出节点。";
  } else if (choiceFacilities.length > 0) {
    note.textContent = "前往大地图上高亮的设施确认优先方向，或在指挥中心做出决策。";
  } else if ((nar.choices && nar.choices.length > 0) || (nar.fin_endings && nar.fin_endings.length > 0)) {
    note.textContent = "不同选项会通往不同剧情；做出选择后继续。";
  } else {
    note.textContent = "推进当前节点后将显示下一剧情目标。";
  }
  objectivesUpcoming.appendChild(note);
}

const MEMORY_FLASH_02_02_ACK = "memory_flash_02_02_ack";

const MEMORY_FLASH_022_FALLBACK = [
  "……滴答。白光与噪声绞在一起，像有人把岸线塞进颅骨里搅动。",
  "束带、电极、远处宣读编号的嗓音——你想挣脱，身体却只记得服从。",
  "强光炸裂。你猛地吸气，基地的通风声回来了。",
];

function removeMemoryFlashOverlay() {
  document.getElementById("memory-flash-overlay")?.remove();
}

/**
 * 02-02：全屏记忆闪回演出；看完后 POST theater_ack 才允许 advance。
 */
function tryShowMemoryFlash022(state) {
  const nar = state?.narrative;
  const sess = state?.session;
  if (!nar || nar.node_id !== "02-02") return;
  if (plotHasFlag(sess, MEMORY_FLASH_02_02_ACK)) return;
  if (document.getElementById("memory-flash-overlay")) return;

  const raw = nar.memory_flash_lines_zh;
  let lines =
    Array.isArray(raw) && raw.length > 0
      ? raw.map((x) => String(x ?? "").trim()).filter(Boolean)
      : [...MEMORY_FLASH_022_FALLBACK];
  if (!lines.length) lines = [...MEMORY_FLASH_022_FALLBACK];

  const overlay = document.createElement("div");
  overlay.id = "memory-flash-overlay";
  overlay.className = "memory-flash-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "memory-flash-title");

  const panel = document.createElement("div");
  panel.className = "memory-flash-panel";

  const scroll = document.createElement("div");
  scroll.className = "memory-flash-scroll";

  const title = document.createElement("h2");
  title.id = "memory-flash-title";
  title.className = "memory-flash-title";
  title.textContent = `${nar.title_zh || "记忆闪回"}`;

  const sub = document.createElement("p");
  sub.className = "memory-flash-sub";
  sub.textContent = "侵入式感官片段 · 点击按钮逐段推进";

  const body = document.createElement("p");
  body.className = "memory-flash-body";

  const footer = document.createElement("div");
  footer.className = "memory-flash-panel-footer";

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "memory-flash-btn memory-flash-btn--primary";

  let idx = 0;
  let finishing = false;

  async function finishFlash() {
    if (finishing) return;
    finishing = true;
    btn.disabled = true;
    try {
      const st = await fetchJSON(gameApiUrl("/api/state"));
      const nid = String(st?.narrative?.node_id || "").trim();
      if (plotHasFlag(st.session, MEMORY_FLASH_02_02_ACK)) {
        removeMemoryFlashOverlay();
        showToast("演出已确认。", 2200);
        await refreshTopBar();
        return;
      }
      if (nid !== "02-02") {
        throw new Error(`剧场确认失败：服务器当前节点为「${nid || "?"}」，请刷新页面后再试。`);
      }
      await fetchJSON(gameApiUrl("/api/narrative/action"), {
        method: "POST",
        body: JSON.stringify({ kind: "theater_ack", node_id: nid }),
      });
      removeMemoryFlashOverlay();
      showToast("意识回落基地当下。", 2600);
      await refreshTopBar();
    } catch (e) {
      showErrorToast(e, 6200);
    } finally {
      finishing = false;
      btn.disabled = false;
    }
  }

  function syncUi() {
    body.textContent = lines[idx] || "";
    if (idx < lines.length - 1) {
      btn.textContent = `下一瞬（${idx + 1}/${lines.length}）`;
    } else {
      btn.textContent = "惊醒 · 回到当下";
    }
  }

  btn.addEventListener("click", async () => {
    if (idx < lines.length - 1) {
      idx += 1;
      syncUi();
      scroll.scrollTop = 0;
      return;
    }
    await finishFlash();
  });

  scroll.appendChild(title);
  scroll.appendChild(sub);
  scroll.appendChild(body);
  footer.appendChild(btn);
  panel.appendChild(scroll);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);

  overlay.tabIndex = -1;
  overlay.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") ev.preventDefault();
  });
  overlay.focus();

  syncUi();

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      overlay.classList.add("memory-flash-overlay--visible");
    });
  });
}

/** localStorage：用户点「知道了」后不再自动弹出；手动按钮可随时重开 */
const SANDBOX_PLAYBOOK_INTRO_LS = "epoch_explorer_playbook_intro_v202605";
/** sessionStorage：同一会话内轮询刷新只自动弹出一次 */
const SANDBOX_PLAYBOOK_SESSION_OFFER = "epoch_explorer_playbook_session_offer_v202605";

function sandboxPlaybookEligibleForAutoOffer(data) {
  if (!data) return false;
  const sess = data.session || {};
  const sb = data.sandbox || {};
  if (sb.sandbox_ops_unlocked !== true) return false;
  const phase = String(sess.story_phase || sb.story_phase || "").trim();
  if (phase !== "Sandbox") return false;
  const cat = sb.resource_activity_catalog;
  return Array.isArray(cat) && cat.length > 0;
}

function isMemoryFlashOverlayVisible() {
  return !!document.getElementById("memory-flash-overlay");
}

function sandboxPlaybookBackdropEl() {
  return document.getElementById("sandbox-playbook-backdrop");
}

function closeSandboxPlaybook() {
  const backdrop = sandboxPlaybookBackdropEl();
  if (!backdrop || backdrop.classList.contains("hidden")) return;
  backdrop.classList.add("hidden");
  backdrop.setAttribute("aria-hidden", "true");
  document.getElementById("sandbox-playbook-open")?.setAttribute("aria-expanded", "false");
  document.getElementById("sandbox-playbook-open")?.focus({ preventScroll: true });
}

/** 挂载教程浮层 DOM 与事件（仅一次） */
function ensureSandboxPlaybookMounted() {
  if (sandboxPlaybookBackdropEl()) return;

  const backdrop = document.createElement("div");
  backdrop.id = "sandbox-playbook-backdrop";
  backdrop.className = "sandbox-playbook-backdrop hidden";
  backdrop.setAttribute("aria-hidden", "true");

  const panel = document.createElement("div");
  panel.className = "sandbox-playbook-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-labelledby", "sandbox-playbook-title");

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "sandbox-playbook-close";
  closeBtn.setAttribute("aria-label", "关闭");
  closeBtn.textContent = "×";

  const scroll = document.createElement("div");
  scroll.className = "sandbox-playbook-scroll";

  scroll.innerHTML = `
    <h2 id="sandbox-playbook-title" class="sandbox-playbook-title">静默玩法速览</h2>
    <p class="sandbox-playbook-lead">
      你从「剧情节拍」切换到<strong class="sandbox-playbook-strong-mint">静默运营</strong>后，大地图侧的<strong>时间与资源</strong>会跟着「基地日」走：远征归国、简报与静默内的 AI 对话额度，都和「基地日 +1」同一条主轴对齐。
    </p>
    <section class="sandbox-playbook-section" aria-labelledby="sandbox-playbook-s1">
      <h3 id="sandbox-playbook-s1">1. 「基地日 +1」与运营简报</h3>
      <p>
        点侧栏<code class="sandbox-playbook-code">基地日推进 +1</code>会推进一日的静默结转：在外的远征会先按归国规则结算，
        再滚动基地资源与简报行。简报块在静默条下方展开，可作为「这轮静默发生了什么」的阅读入口。
      </p>
    </section>
    <section class="sandbox-playbook-section" aria-labelledby="sandbox-playbook-s2">
      <h3 id="sandbox-playbook-s2">2. 地图资源行动</h3>
      <p>
        静默条内可选用<strong>地图资源类型</strong>并执行行动；是否与剧情/探索进度挂钩会在提示里写明（门禁、补给或情报不足时会拦截）。
      </p>
      <ul>
        <li>资源与士气变化会反映在左上「基地资源」条。</li>
        <li>「探索」分页仍用于查看大区探索状态；静默行动与野区交互是另一条经营向入口。</li>
      </ul>
    </section>
    <section class="sandbox-playbook-section" aria-labelledby="sandbox-playbook-s3">
      <h3 id="sandbox-playbook-s3">3. 野外远征</h3>
      <p>
        仅静默期内可派出远征：出发前会<strong>预付能源与补给</strong>，进度条归零的一日会在<strong>后续的基地日结转</strong>里统一归国入账。
      </p>
    </section>
    <section class="sandbox-playbook-section" aria-labelledby="sandbox-playbook-s4">
      <h3 id="sandbox-playbook-s4">4. 设施科技与决算卡</h3>
      <p>
        静默条底部的<strong>科技摘要</strong>汇总各设施可用的升级/决算方向（是否出现仍受剧情门禁约束）。
      </p>
      <ul>
        <li><strong>决算卡（走近设施）</strong>仍是主要立项方式：需要你<strong>走过去点开设施面板</strong>才能选具体条目。</li>
        <li>「决算」分页可回看最近落地记录；有<strong>待命决算</strong>时，静默结束时会尝试写入剧情侧后果。</li>
      </ul>
    </section>
    <section class="sandbox-playbook-section" aria-labelledby="sandbox-playbook-s5">
      <h3 id="sandbox-playbook-s5">5. 小提示</h3>
      <ul>
        <li>若在剧情闪回演出中（全屏记忆片段），会自动让路，不会在演出进行时抢占焦点。</li>
        <li>随时可点此处的「静默玩法教程」重温本页。</li>
      </ul>
    </section>
  `;

  const footer = document.createElement("div");
  footer.className = "sandbox-playbook-footer";
  const gotIt = document.createElement("button");
  gotIt.type = "button";
  gotIt.id = "sandbox-playbook-gotit";
  gotIt.className = "sandbox-playbook-gotit";
  gotIt.textContent = "知道了，不再自动弹出";
  footer.appendChild(gotIt);

  panel.appendChild(closeBtn);
  panel.appendChild(scroll);
  panel.appendChild(footer);
  backdrop.appendChild(panel);
  document.body.appendChild(backdrop);

  closeBtn.addEventListener("click", () => closeSandboxPlaybook());
  gotIt.addEventListener("click", () => {
    try {
      localStorage.setItem(SANDBOX_PLAYBOOK_INTRO_LS, "1");
    } catch {
      /* ignore quota / privacy mode */
    }
    closeSandboxPlaybook();
  });

  backdrop.addEventListener("click", (ev) => {
    if (ev.target === backdrop) closeSandboxPlaybook();
  });
}

/** 与同一会话内「自动弹出一次」共用同一标记；仅在已处于可自动弹出条件时写入，避免在剧情节拍先手点教程后进静默反而不弹窗。 */
function rememberSandboxPlaybookAutoSessionIfEligible(state) {
  if (!sandboxPlaybookEligibleForAutoOffer(state)) return;
  try {
    sessionStorage.setItem(SANDBOX_PLAYBOOK_SESSION_OFFER, "1");
  } catch {
    /* ignore */
  }
}

function openSandboxPlaybook() {
  ensureSandboxPlaybookMounted();
  const backdrop = sandboxPlaybookBackdropEl();
  if (!backdrop) return;
  backdrop.classList.remove("hidden");
  backdrop.setAttribute("aria-hidden", "false");
  document.getElementById("sandbox-playbook-open")?.setAttribute("aria-expanded", "true");
  backdrop.tabIndex = -1;
  backdrop.focus({ preventScroll: true });
}

function maybeOfferSandboxPlaybookIntro(data) {
  if (!sandboxPlaybookEligibleForAutoOffer(data)) return;
  if (isMemoryFlashOverlayVisible()) return;
  const pb = sandboxPlaybookBackdropEl();
  if (pb && !pb.classList.contains("hidden")) return;
  try {
    if (localStorage.getItem(SANDBOX_PLAYBOOK_INTRO_LS)) return;
  } catch {
    /* ignore */
  }
  try {
    if (sessionStorage.getItem(SANDBOX_PLAYBOOK_SESSION_OFFER)) return;
  } catch {
    /* ignore */
  }
  rememberSandboxPlaybookAutoSessionIfEligible(data);
  openSandboxPlaybook();
}

/** localStorage 存档键名 */
const LS_SAVE_KEY = "epoch_incursion_save_v1";

/** 将当前后端会话持久化到 localStorage */
function persistSessionToLocalStorage() {
  if (!latestState?.session) return;
  try {
    localStorage.setItem(LS_SAVE_KEY, JSON.stringify(latestState.session));
  } catch (e) {
    // localStorage 满或不可用，静默失败
  }
}

/** 清除存档：重置后端会话 + 清除 localStorage */
async function clearSaveAndReset() {
  try {
    // 先清除 localStorage
    localStorage.removeItem(LS_SAVE_KEY);
    // 重置后端会话
    const data = await fetchJSON(gameApiUrl("/api/session/reset"), {
      method: "POST",
      body: "{}",
    });
    latestState = data;
    // 重置恢复标记，以便下次可以重新尝试恢复（但 localStorage 已清空，不会恢复任何内容）
    _lsRestoreAttempted = true;
    renderObjectivesPanel(data);
    renderMgmtResourcesHud(data.session);
    renderMgmtLogStrip(data.management_recent);
    renderSandboxDock(data);
    showToast("存档已清除，游戏已重置。", 3200);
  } catch (e) {
    showToast("清除存档失败，请重试。", 4200);
  }
}

/** 从 localStorage 恢复存档到后端（仅在首次成功拉取 state 后调用一次） */
let _lsRestoreAttempted = false;
async function restoreSessionFromLocalStorage() {
  if (_lsRestoreAttempted) return null;
  _lsRestoreAttempted = true;
  try {
    const raw = localStorage.getItem(LS_SAVE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw);
    if (!session || typeof session !== "object") return null;
    const resp = await fetchJSON(gameApiUrl("/api/session/load"), {
      method: "POST",
      body: JSON.stringify({ session }),
    });
    return resp;
  } catch (e) {
    // 恢复失败，继续使用新会话
    return null;
  }
}

async function refreshTopBar() {
  try {
    const data = await fetchJSON(gameApiUrl("/api/state"));
    latestState = data;
    // 首次成功获取 state 后，尝试从 localStorage 恢复存档
    const restored = await restoreSessionFromLocalStorage();
    // 如果恢复了存档，使用恢复后的 state；否则用刚拉取的 state
    if (restored?.session) {
      latestState = restored;
    }
    // 每次 state 更新后自动持久化到 localStorage
    persistSessionToLocalStorage();
    syncExplorerApiBanner(true);
    renderObjectivesPanel(latestState);
    renderMgmtResourcesHud(latestState.session);
    renderMgmtLogStrip(latestState.management_recent);
    renderSandboxDock(latestState);
    tryShowMemoryFlash022(latestState);
    maybeOfferSandboxPlaybookIntro(latestState);
  } catch (e) {
    latestState = null;
    explorerSyncLastError = e?.message || String(e);
    syncExplorerApiBanner(false);
    renderObjectivesPanel(null);
    renderMgmtResourcesHud(null);
    renderMgmtLogStrip([]);
    document.querySelector(".objectives-panel__top-tools")?.classList.add("hidden");
    if (sandboxDock) {
      sandboxDock.classList.add("hidden");
      sandboxDock.replaceChildren();
    }
  }
}

function addChoiceButtons(narrative) {
  const navBlocked = !!narrative.story_navigation_blocked_zh;

  if (narrative.node_id === "FIN-02" && narrative.fin_endings?.length) {
    for (const e of narrative.fin_endings) {
      const wrapper = document.createElement("div");
      wrapper.className = "ending-choice-wrapper";
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = e.label_zh;
      b.disabled = navBlocked;
      if (navBlocked) b.title = narrative.story_navigation_blocked_zh || "";
      b.addEventListener("click", () => postChoice(e.id));
      wrapper.appendChild(b);
      if (e.description_zh) {
        const desc = document.createElement("p");
        desc.className = "ending-choice-desc";
        desc.textContent = e.description_zh;
        wrapper.appendChild(desc);
      }
      storyChoices.appendChild(wrapper);
    }
    return;
  }
  for (const c of narrative.choices || []) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = c.label_zh;
    b.disabled = navBlocked;
    if (navBlocked) b.title = narrative.story_navigation_blocked_zh || "";
    b.addEventListener("click", () => postChoice(c.id));
    storyChoices.appendChild(b);
  }
  if (narrative.can_advance_default) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "secondary";
    b.textContent = "推进剧情（无选项节点）";
    b.disabled = navBlocked;
    if (navBlocked) b.title = narrative.story_navigation_blocked_zh || "";
    b.addEventListener("click", () => postAdvance());
    storyChoices.appendChild(b);
  }
}

async function postNpcLine(npcId, ambient) {
  cancelNpcDialogueReveal();
  if (storyChoices.children.length > 0) setStoryChoicesLocked(true);
  storyAiLine.textContent = "生成中…";
  const ctx =
    ambient ||
    "玩家在大地图自由探索，与角色进行简短交流。勿剧透尚未解锁的阴谋层；保持人设。";
  const data = await fetchJSON(gameApiUrl("/api/npc/generate"), {
    method: "POST",
    body: JSON.stringify({ npc_id: npcId, mode: "scene_line", context: ctx, max_tokens: 480 }),
  });
  revealNpcDialogueSequential(storyAiLine, data.text || "", {
    onComplete: () => setStoryChoicesLocked(false),
  });
}

/** 打开对话时由服务端组 prompt，自动交代现场（无需手点） */
async function postNpcOpening(npcId, storyFocus) {
  cancelNpcDialogueReveal();
  if (storyChoices.children.length > 0) setStoryChoicesLocked(true);
  storyAiLine.textContent = "角色台词生成中…";
  try {
    const data = await fetchJSON(gameApiUrl("/api/npc/opening"), {
      method: "POST",
      body: JSON.stringify({ npc_id: npcId, story_focus: storyFocus, max_tokens: 520 }),
    });
    latestState = data;
    const nar = data.narrative;
    // 记录 NPC 开场白到对话历史（仅自由对话模式）
    if (chatInputContainer && data.text) {
      chatHistoryMessages.push({ role: "npc", text: data.text, time: Date.now() });
    }
    const decryptAfterTalk =
      nar?.node_id === "02-01" &&
      npcId === "dr_lin" &&
      storyFocus &&
      data.session &&
      !plotHasFlag(data.session, "datastick_decrypt_complete");

    revealNpcDialogueSequential(storyAiLine, data.text || "", {
      onComplete: async () => {
        // 自由对话模式：显示输入框，并发送 start 到后端
        if (chatInputContainer) {
          chatInputContainer.style.display = "";
          setTimeout(() => chatInputField?.focus(), 150);
          // 告知后端对话开始
          try {
            const startResp = await fetchJSON(gameApiUrl("/api/npc/chat"), {
              method: "POST",
              body: JSON.stringify({ npc_id: npcId, player_text: "", action: "start" }),
            });
            // 如果后端返回对话被阻止（NPC 已结束对话），显示拒绝消息
            if (startResp.conversation_blocked) {
              teardownChatUI();
              storyAiLine.textContent = `"${startResp.reason_zh || '该去工作了'}"`;
              setTimeout(() => closeStoryUI(), 2500);
            }
          } catch (_) { /* 静默忽略 */ }
          updateChatEmotion({ off_topic_count: 0 });
          return;
        }

        if (!decryptAfterTalk) {
          setStoryChoicesLocked(false);
          return;
        }
        try {
          await fetchJSON(gameApiUrl("/api/narrative/action"), {
            method: "POST",
            body: JSON.stringify({ kind: "decrypt_datastick", via: "dr_lin" }),
          });
          showToast("数据棒解密已在对话中确认，可点击「推进剧情」继续。", 3800);
          const st = await fetchJSON(gameApiUrl("/api/state"));
          latestState = st;
          renderMgmtResourcesHud(st.session);
          renderMgmtLogStrip(st.management_recent);
          npcScheduleSnapshot = scheduledNpcWorldPositions(st);
          syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
          if (lastStoryInteract?.kind === "npc" && lastStoryInteract.id === npcId) {
            const chk = await fetchJSON(gameApiUrl("/api/npc/check"), {
              method: "POST",
              body: JSON.stringify({ npc_id: npcId }),
            });
            renderNpcPanel(st, chk, lastStoryInteract, { skipOpening: true });
            syncStoryChoicesLayout();
          }
          await refreshTopBar();
        } catch (e) {
          showErrorToast(e, 5200);
        } finally {
          setStoryChoicesLocked(false);
        }
      },
    });
  } catch (e) {
    npcDialogueRevealGen++;
    storyAiLine.textContent = `（生成失败：${e.message || e}）`;
    setStoryChoicesLocked(false);
  }
}

async function postSourceLine(question) {
  cancelNpcDialogueReveal();
  if (storyChoices.children.length > 0) setStoryChoicesLocked(true);
  storyAiLine.textContent = "聆听中…";
  try {
    const data = await fetchJSON(gameApiUrl("/api/source/whisper"), {
      method: "POST",
      body: JSON.stringify({ question: question || "……" }),
    });
    // 保存源低语后的状态到 localStorage
    if (data.session) {
      latestState = data;
      persistSessionToLocalStorage();
    }
    revealNpcDialogueSequential(storyAiLine, data.text || "", {
      onComplete: () => setStoryChoicesLocked(false),
    });
  } catch (e) {
    npcDialogueRevealGen++;
    storyAiLine.textContent = `（失败：${e.message || e}）`;
    setStoryChoicesLocked(false);
  }
}

async function postMgmt(tag) {
  try {
    const data = await fetchJSON(gameApiUrl("/api/management"), {
      method: "POST",
      body: JSON.stringify({ tag }),
    });
    const label = data.session?.last_decision_label_zh || tag;
    if (data.management_queued) {
      showToast(`已记入待办（退出静默后落地）：${label}`);
    } else {
      showToast(`已立项：${label}`);
    }
    await refreshTopBar();
    cancelNpcDialogueReveal();
    setStoryChoicesLocked(false);
    if (storyAiLine) storyAiLine.textContent = "";
  } catch (e) {
    showErrorToast(e, 5200);
  }
}

function fmtMgmtSignedDeltaRow(row) {
  if (!row) return null;
  const lab = row.label_zh || row.label || row.key || "";
  const d = Number(row.delta);
  const sign = d > 0 ? "+" : "";
  const dShow = Number.isFinite(d) ? d : row.delta;
  return `${lab} ${sign}${dShow} （→ ${row.after}）`;
}

function appendFacilityManagementCards(extrasEl, managementTags) {
  if (!managementTags?.length) return;
  const intro = document.createElement("p");
  intro.className = "mgmt-action-warning";
  intro.textContent = "每项决议只能立项一次；开采路线与回声援助存在互斥组合。";
  extrasEl.appendChild(intro);
  for (const m of managementTags) {
    const pv = m.preview || {};
    const blocked = !!pv.blocked;
    const card = document.createElement("article");
    card.className = `mgmt-action-card${blocked ? " mgmt-action-card--blocked" : ""}`;
    const title = document.createElement("h4");
    title.className = "mgmt-action-title";
    title.textContent = m.label_zh || m.tag;
    card.appendChild(title);
    if (pv.narrative_hint_zh) {
      const hint = document.createElement("p");
      hint.className = "objectives-note";
      hint.style.margin = "0 0 6px";
      hint.textContent = pv.narrative_hint_zh;
      card.appendChild(hint);
    }
    const rows = [];
    for (const row of pv.resources || []) {
      const line = fmtMgmtSignedDeltaRow(row);
      if (line) rows.push(line);
    }
    for (const row of pv.hidden_vars || []) {
      const line = fmtMgmtSignedDeltaRow(row);
      if (line) rows.push(line);
    }
    if (rows.length) {
      const ul = document.createElement("ul");
      ul.className = "mgmt-action-rows";
      for (const line of rows) {
        const li = document.createElement("li");
        li.textContent = line;
        ul.appendChild(li);
      }
      card.appendChild(ul);
    }
    const rx = (pv.reactors || []).slice(0, 4);
    if (rx.length) {
      const rEl = document.createElement("p");
      rEl.className = "mgmt-action-react";
      const parts = rx.map((x) => `${x.npc_id}（${x.tone_zh || x.tone || ""}）`);
      rEl.innerHTML = `<strong>可能引起：</strong>${parts.join("；")}`;
      card.appendChild(rEl);
    }
    if (blocked && pv.blocked_reason_zh) {
      const bw = document.createElement("p");
      bw.className = "objectives-note";
      bw.style.color = "#c9a86a";
      bw.textContent = pv.blocked_reason_zh;
      card.appendChild(bw);
    }
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mgmt-action-commit";
    btn.textContent = blocked ? "不可执行" : "立项执行";
    btn.disabled = blocked;
    btn.addEventListener("click", () => postMgmt(m.tag));
    card.appendChild(btn);
    extrasEl.appendChild(card);
  }
}

/**
 * 脚本化固定多轮对话（替代自由文本输入）。
 * 每轮显示 NPC 台词 → 玩家选择固定选项 → 推进至下一轮或最终选择。
 * 由 renderNpcPanel 在 nar.pre_dialogue 存在时调用。
 */
let scriptedDialogueRound = 0;
let scriptedDialogueNar = null;
let scriptedDialogueState = null;

function resetScriptedDialogue() {
  scriptedDialogueRound = 0;
  scriptedDialogueNar = null;
  scriptedDialogueState = null;
}

function renderScriptedDialogue(stateData, npc, nar) {
  scriptedDialogueNar = nar;
  scriptedDialogueState = stateData;
  scriptedDialogueRound = 0;

  // 设置 NPC 标题和立绘
  const row = (stateData.overworld_npcs || []).find((r) => r.id === npc.id);
  storyTitle.textContent = row?.name || npc.name;
  storySub.textContent = "";
  storyBullets.innerHTML = "";
  setStoryPortrait("npc", npc.id, row?.name || npc.name);

  // 展示第一轮
  advanceScriptedDialogueRound();
}

function advanceScriptedDialogueRound() {
  const rounds = scriptedDialogueNar?.pre_dialogue;
  if (!rounds || scriptedDialogueRound >= rounds.length) {
    // 所有脚本轮次结束 → 展示最终故事选项
    showFinalScriptedChoices();
    return;
  }

  const rd = rounds[scriptedDialogueRound];
  storyChoices.innerHTML = "";

  // 显示 NPC 台词气泡
  if (rd.npc_line_zh) {
    addChatBubble("npc", rd.npc_line_zh);
  }
  // 副文本（情绪/动作提示）
  if (rd.npc_subtext_zh) {
    storySub.textContent = rd.npc_subtext_zh;
  } else {
    storySub.textContent = "";
  }

  // 渲染当前轮次的玩家选项
  const opts = rd.player_options || [];
  for (const opt of opts) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = opt.label_zh;
    b.className = "scripted-dialogue-opt";
    b.addEventListener("click", () => {
      // 显示玩家台词气泡
      if (opt.player_line_zh) {
        addChatBubble("player", opt.player_line_zh);
      }
      // 推进到下一轮
      scriptedDialogueRound++;
      advanceScriptedDialogueRound();
    });
    storyChoices.appendChild(b);
  }
  syncStoryChoicesLayout();
}

function showFinalScriptedChoices() {
  storyChoices.innerHTML = "";
  storySub.textContent = "她的话说完了。接下来，轮到你做决定。";

  const nar = scriptedDialogueNar;
  if (!nar || !nar.choices) return;

  for (const c of nar.choices) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = c.label_zh;
    b.className = "scripted-dialogue-opt scripted-dialogue-opt--final";
    b.addEventListener("click", () => {
      // 提交最终选择（沿用 postChoice 逻辑）
      postChoice(c.id);
    });
    storyChoices.appendChild(b);
  }
  syncStoryChoicesLayout();
}

// 面板关闭时重置脚本对话状态（在 closeStoryUI 中调用）
const _origCloseStoryUI = closeStoryUI;
closeStoryUI = function () {
  resetScriptedDialogue();
  _origCloseStoryUI();
};

function renderNpcPanel(stateData, checkData, npc, opts = {}) {
  const skipOpening = !!opts.skipOpening;
  setStorySpriteColumnVisible(true);
  storyExtras.innerHTML = "";
  storyMeta.innerHTML = "";
  storyBody.classList.add("story-body--npc-dialogue");
  const focus = checkData.is_story_focus;
  const row = (stateData.overworld_npcs || []).find((r) => r.id === npc.id);
  storyTitle.textContent = row?.name || npc.name;
  storySub.textContent = "";
  storyBullets.innerHTML = "";
  setStoryPortrait("npc", npc.id, row?.name || npc.name);
  const nar = checkData.narrative;
  storyChoices.innerHTML = "";

  // 脚本化固定对话：pre_dialogue 存在时替代自由文本/传统模式
  const hasPreDialogue = nar.pre_dialogue && nar.pre_dialogue.length > 0;

  // 自由对话模式：story_focus 且有选项（非 FIN-02 结局选择）—— pre_dialogue 优先
  const useFreeChat =
    !hasPreDialogue &&
    focus &&
    nar.choices &&
    nar.choices.length > 0 &&
    nar.node_id !== "FIN-02";

  if (hasPreDialogue) {
    // 脚本对话模式：跳过 AI 开场白，直接展示固定对话轮次
    renderScriptedDialogue(stateData, npc, nar);
    syncStoryChoicesLayout();
    return;
  } else if (nar.node_id === "FIN-02" && nar.fin_endings?.length) {
    addChoiceButtons(nar);
  } else if (useFreeChat) {
    // 使用自由文本对话 UI（初始隐藏，开场对白完成后显示）
    setupChatUI(npc.id, nar);
    if (chatInputContainer) {
      chatInputContainer.style.display = "none";
    }
  } else {
    // 传统模式
    const hasBranch =
      (nar.fin_endings && nar.fin_endings.length > 0) ||
      (nar.choices && nar.choices.length > 0) ||
      !!nar.can_advance_default;
    if (hasBranch) addChoiceButtons(nar);
  }
  syncStoryChoicesLayout();
  if (nar.node_id === "02-01" && npc.id === "dr_lin" && focus && !plotHasFlag(stateData.session, "datastick_decrypt_complete")) {
    storySub.textContent =
      "听完开场对白后将自动记录「解密已见证」；也可手动点此以防生成失败：";
    const wrap = document.createElement("div");
    wrap.className = "objectives-note";
    wrap.style.marginTop = "8px";
    const db = document.createElement("button");
    db.type = "button";
    db.textContent = "确认：解密已完成（林博士见证）";
    db.addEventListener("click", () => postDecryptDatastick("dr_lin"));
    wrap.appendChild(db);
    storyExtras.appendChild(wrap);
  }
  // 自由对话模式下，选项区域不锁定（因为根本没有按钮）
  if (!useFreeChat && storyChoices.children.length > 0 && !skipOpening) setStoryChoicesLocked(true);
  if (!skipOpening) queueMicrotask(() => postNpcOpening(npc.id, focus));
}

function renderFacilityPanel(stateData, checkData, fac) {
  setStorySpriteColumnVisible(false);
  if (storyPortraitImgEl) {
    storyPortraitImgEl.hidden = true;
    storyPortraitImgEl.removeAttribute("src");
  }
  storyExtras.innerHTML = "";
  storyMeta.innerHTML = "";
  storyBody.classList.remove("story-body--npc-dialogue");
  const nar = stateData.narrative;

  // ── FIN-03 结局后日谈 ──
  if (nar.node_id === "FIN-03" && nar.fin03_epilogue) {
    const ep = nar.fin03_epilogue;
    storyTitle.textContent = ep.title_zh;
    storySub.textContent = "";
    storyBullets.innerHTML = "";
    storyChoices.innerHTML = "";
    storyBody.classList.add("story-body--npc-dialogue");
    storyAiLine.textContent = "";
    storyAiLine.hidden = true;

    const epWrap = document.createElement("div");
    epWrap.className = "fin03-epilogue";
    const epTitle = document.createElement("div");
    epTitle.className = "fin03-epilogue__title";
    epTitle.textContent = ep.title_zh;
    epWrap.appendChild(epTitle);

    if (ep.tone_zh) {
      const epTone = document.createElement("div");
      epTone.className = "fin03-epilogue__tone";
      epTone.textContent = "— " + ep.tone_zh + " —";
      epWrap.appendChild(epTone);
    }

    const epText = document.createElement("div");
    epText.className = "fin03-epilogue__text";
    for (const para of ep.epilogue_zh.split("\n\n")) {
      const p = document.createElement("p");
      p.textContent = para;
      epText.appendChild(p);
    }
    epWrap.appendChild(epText);

    const epClose = document.createElement("button");
    epClose.type = "button";
    epClose.className = "fin03-epilogue__close";
    epClose.textContent = "源纪元 · 岸线侵入 — 完";
    epClose.addEventListener("click", closeStoryUI);
    epWrap.appendChild(epClose);

    storyExtras.appendChild(epWrap);
    return;
  }

  storyTitle.textContent = fac.name;
  const rel = checkData.story_relevant;
  const uq = checkData.upgrade_choice_id;
  storySub.textContent = rel
    ? "此处与当前剧情节点相关。"
    : "在此查阅数值预览并立项基地决议；资源不足或互斥路线将被拒绝。";
  renderBullets(
    rel
      ? nar.objectives_player_zh || []
      : [
          `设施：${fac.name}`,
          "经营层强调取舍：能源、补给、医疗、情报与岸线威胁彼此牵连。",
          "决议确认后会记入右侧「基地决算记录」，每项通常仅能立项一次。",
        ],
  );
  storyChoices.innerHTML = "";

  // 通用：节点有 facility→choice 映射时，在当前设施展示对应单一确认按钮
  if (rel && uq) {
    const pick = (nar.choices || []).find((c) => c.id === uq);
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = pick ? `在此确认：${pick.label_zh}` : "确认决策方向";
    b.addEventListener("click", () => postChoice(uq));
    storyChoices.appendChild(b);
  }

  // 指挥中心：有剧情选项时展示全部（会议室决策视图）
  if (fac.id === "command" && rel && (nar.choices?.length > 0 || nar.fin_endings?.length > 0)) {
    if (nar.node_id === "01-02") {
      storySub.textContent = "会议室：三项升级优先（与物资会议一致）。";
    } else if (nar.node_id === "PRO-02") {
      storySub.textContent = "指挥中心：决定本次危机优先方向。";
    } else if (nar.node_id === "FIN-02") {
      storySub.textContent = "指挥部：在此做出最终选择。";
    }
    addChoiceButtons(nar);
  }

  // 02-02 记忆闪回：指挥中心作为推进入口
  if (nar.node_id === "02-02" && fac.id === "command" && rel) {
    const acked = plotHasFlag(stateData.session, "memory_flash_02_02_ack");
    storySub.textContent = acked
      ? "记忆闪回已观看，可推进至下一段剧情。"
      : "一段侵入式记忆即将重演——全屏演出结束并确认后，可在此推进剧情。";
    if (acked && nar.can_advance_default) {
      const adv = document.createElement("button");
      adv.type = "button";
      adv.textContent = "推进剧情（进入下一段）";
      adv.addEventListener("click", () => postAdvance());
      storyChoices.appendChild(adv);
    }
  }

  if (nar.node_id === "02-01" && fac.id === "lab" && rel && !plotHasFlag(stateData.session, "datastick_decrypt_complete")) {
    storySub.textContent =
      "林博士使用实验室隔离离线槽读取加密数据棒；仪表稳定后即视为解密完成（对白由剧情生成补充细节）。";
    const wrap = document.createElement("div");
    wrap.className = "objectives-note";
    wrap.style.marginBottom = "10px";
    const db = document.createElement("button");
    db.type = "button";
    db.textContent = "完成离线解密流程（数据棒）";
    db.addEventListener("click", () => postDecryptDatastick("lab"));
    wrap.appendChild(db);
    storyExtras.appendChild(wrap);
  }
  if ((nar.node_id === "PRO-04" || nar.node_id === "03-03") && fac.id === "listen" && rel) {
    const lab = document.createElement("label");
    lab.textContent = "向源发问（自由文本，符合文档「低语」规则）";
    const inp = document.createElement("input");
    inp.type = "text";
    inp.placeholder = "输入问题…";
    const sb = document.createElement("button");
    sb.type = "button";
    sb.textContent = "发送";
    sb.addEventListener("click", () => postSourceLine(inp.value));
    storyExtras.appendChild(lab);
    storyExtras.appendChild(inp);
    storyExtras.appendChild(document.createElement("br"));
    storyExtras.appendChild(sb);
  }
  if (rel && nar.can_advance_default && !uq) {
    const adv = document.createElement("button");
    adv.type = "button";
    adv.className = "secondary";
    adv.textContent = "推进剧情（直线前进）";
    adv.addEventListener("click", () => postAdvance());
    storyChoices.appendChild(adv);
  }
  const hint = nar.facility_hints?.[fac.id];
  if (hint?.management_tags?.length) {
    const hdr = document.createElement("div");
    hdr.className = "objectives-note";
    hdr.style.marginBottom = "6px";
    hdr.innerHTML = "<strong>模拟经营 · 设施决议</strong>";
    storyExtras.appendChild(hdr);
    appendFacilityManagementCards(storyExtras, hint.management_tags);
  }

  /** 须与后端 `game/facility_sim_ops.FACILITY_IDLE_DAILY_ACCRUAL` 键一致（带挂机积存领取的地图设施） */
  const SILENT_OPS_FACILITY_IDS = new Set([
    "mine",
    "mine_ruins",
    "lab",
    "comm",
    "defense",
    "listen",
    "shore_cave",
    "echo_site",
  ]);

  if (SILENT_OPS_FACILITY_IDS.has(fac.id)) {
    const simOv = checkData.sim_facility_overlay ?? stateData.facility_sim_overlays?.[fac.id];
    if (simOv === undefined) {
      const warn = document.createElement("div");
      warn.className = "facility-sim-api-stale objectives-note";
      warn.style.borderLeft = "3px solid #d4a853";
      warn.style.paddingLeft = "10px";
      warn.textContent = `工作台仍无数据：① 先打开文本自检 ${gameApiUrl(
        "/api/ping",
      )} ，应显示多行 build_tag=facility-sim-… 与 web_api_py 路径；若只有一页空白或打不开，你连的不是本仓库起的进程。② 再访问 ${gameApiUrl(
        "/api/health",
      )} ，应有 facility_sim_overlays / repo_root_guess / ping_txt。③ 在项目根目录（含 game 文件夹）执行 cd 后 python -u -m game——终端会先打印 inferred 仓库路径与 cwd 告警。④ /api/state 最外层须有 facility_sim_overlays。⑤ Explorer Ctrl+F5。`;
      storyExtras.appendChild(warn);
    } else if (simOv.workbench_supported) {
      if (!simOv.enabled && simOv.inactive_reason_zh) {
        const muted = document.createElement("p");
        muted.className = "facility-sim-muted";
        muted.textContent = simOv.inactive_reason_zh;
        storyExtras.appendChild(muted);
      }
      if (simOv.enabled) {
        const box = document.createElement("div");
        box.className = "facility-sim-banner";
        const h = document.createElement("h4");
        h.className = "facility-sim-banner-title";
        h.textContent = "静默运营 · 设施工作台";
        box.appendChild(h);
        const pIdle = document.createElement("p");
        pIdle.className = "facility-sim-idle-copy";
        pIdle.textContent = simOv.idle_claimable_zh || "";
        box.appendChild(pIdle);
        const row = document.createElement("div");
        row.className = "facility-sim-actions";
        const bClaim = document.createElement("button");
        bClaim.type = "button";
        bClaim.className = "facility-sim-btn facility-sim-btn--ghost";
        const idle = simOv.idle_claimable || {};
        const hasIdle = Object.keys(idle).length > 0;
        bClaim.textContent = hasIdle ? "领取挂机积存" : "暂无可领取积存";
        bClaim.disabled = !hasIdle;
        bClaim.addEventListener("click", async () => {
          try {
            await fetchJSON(gameApiUrl("/api/sim/facility/claim_idle"), {
              method: "POST",
              body: JSON.stringify({ facility_id: fac.id }),
            });
            showToast("积存已并入基地资源。", 2800);
            await refreshOpenStoryPanel();
          } catch (e) {
            showErrorToast(e);
          }
        });
        row.appendChild(bClaim);
        box.appendChild(row);
        storyExtras.appendChild(box);
      }
    }
  }

  syncStoryChoicesLayout();
}

async function openStoryFromInteract(t) {
  try {
    lastStoryInteract = t;

    if (t.kind === "facility" && t.id === "command") {
      // 部分剧情节点需走设施面板流程（会议室决策/记忆闪回推进），不走工坊捷径
      const st = await fetchJSON(gameApiUrl("/api/state"));
      const nid = st?.narrative?.node_id;
      if (nid !== "02-02" && nid !== "01-02" && nid !== "PRO-02" && nid !== "FIN-02" && nid !== "FIN-03") {
        await openWorkshopScene("command");
        return;
      }
      // 剧情节点：沿用已获取的状态，跳过下方重复 fetch
      latestState = st;
      renderMgmtResourcesHud(st.session);
      renderMgmtLogStrip(st.management_recent);
      npcScheduleSnapshot = scheduledNpcWorldPositions(st);
      syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
      maybeEchoFacilityPing(t.id);
      const chk = await fetchJSON(gameApiUrl("/api/facility/check"), {
        method: "POST",
        body: JSON.stringify({ facility_id: t.id }),
      });
      renderFacilityPanel(st, chk, t);
      openStoryUI();
      return;
    }
    if (t.kind === "npc" && t.id === "dr_lin" && npcScheduleSnapshot.meta?.dr_lin_sleep) {
      showToast("林博士正在休息（深夜至清晨）。请日间前往医疗实验室、指挥中心或（若已启用）地下监听站。", 4200);
      return;
    }
    const st = await fetchJSON(gameApiUrl("/api/state"));
    latestState = st;
    renderMgmtResourcesHud(st.session);
    renderMgmtLogStrip(st.management_recent);
    npcScheduleSnapshot = scheduledNpcWorldPositions(st);
    syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
    if (t.kind === "facility") maybeEchoFacilityPing(t.id);
    if (t.kind === "npc") {
      const chk = await fetchJSON(gameApiUrl("/api/npc/check"), {
        method: "POST",
        body: JSON.stringify({ npc_id: t.id }),
      });
      renderNpcPanel(st, chk, t);
    } else {
      const chk = await fetchJSON(gameApiUrl("/api/facility/check"), {
        method: "POST",
        body: JSON.stringify({ facility_id: t.id }),
      });
      renderFacilityPanel(st, chk, t);
    }
    openStoryUI();
  } catch (e) {
    showToast("剧情加载失败，请刷新页面后重试。", 4200);
  }
}

storyClose?.addEventListener("click", closeStoryUI);
storyBackdrop?.addEventListener("click", (ev) => {
  if (ev.target === storyBackdrop) closeStoryUI();
});
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    const pb = sandboxPlaybookBackdropEl();
    if (pb && !pb.classList.contains("hidden")) {
      closeSandboxPlaybook();
      return;
    }
    if (isWorkshopOpen()) {
      if (handleWorkshopEscapeKey()) return;
    }
    if (document.body.classList.contains("scene-workshop") || isWorkshopOpen()) {
      exitWorkshopMapScene();
      return;
    }
    if (!storyBackdrop.classList.contains("hidden")) closeStoryUI();
  }
});

document.getElementById("sandbox-playbook-open")?.addEventListener("click", () => {
  rememberSandboxPlaybookAutoSessionIfEligible(latestState);
  openSandboxPlaybook();
});

setInterval(refreshTopBar, 8000);
refreshTopBar();
// dev 面板由 DOMContentLoaded → initDevPanel() 初始化

const keys = new Set();
let lastTs = 0;
let camX = PLAYER.x;
let camY = PLAYER.y;
let toast = "";
let toastUntil = 0;
let mouseCanvasX = 0;
let mouseCanvasY = 0;
let lastAccessToastAt = 0;
let lastOffroadToastAt = 0;

const canvas = document.getElementById("game");
const mini = document.getElementById("minimap");
let ctx = null;
let mctx = null;

function showExplorerBootError(msg) {
  let el = document.getElementById("explorer-boot-error");
  if (!el) {
    el = document.createElement("div");
    el.id = "explorer-boot-error";
    el.className = "explorer-api-banner";
    el.setAttribute("role", "alert");
    document.body.appendChild(el);
  }
  el.classList.remove("hidden");
  el.textContent = msg;
}

if (!canvas || !mini) {
  showExplorerBootError("页面结构不完整：找不到 #game 或 #minimap 画布，请确认从 web/explorer/index.html 打开。");
} else {
  ctx = canvas.getContext("2d");
  mctx = mini.getContext("2d");
  if (!ctx || !mctx) {
    showExplorerBootError("无法初始化 2D 画布，请尝试更换浏览器或关闭硬件加速后重试。");
  }
}

const wsizeEl = document.getElementById("wsize");
wsizeEl && (wsizeEl.textContent = `${WORLD.w}×${WORLD.h}`);

function resize() {
  if (!canvas || !ctx) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cw = Math.max(1, canvas.clientWidth);
  const ch = Math.max(1, canvas.clientHeight);
  canvas.width = Math.floor(cw * dpr);
  canvas.height = Math.floor(ch * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  refreshWorkshopTutorialLayout();
}
window.addEventListener("resize", resize);
if (canvas && ctx) resize();
bootWorkshopUiState();

/** 初始化任务面板标签切换 */
function initObjectivesTabs() {
  const tabs = document.querySelectorAll(".objectives-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const tabName = tab.dataset.tab;
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".objectives-tab-content").forEach((content) => {
        content.classList.toggle("active", content.dataset.content === tabName);
      });
    });
  });
}
initObjectivesTabs();
initObjectivesTabIcons();

/**
 * 镜头焦点落在主画布上的坐标（CSS 逻辑像素，须在 resize 设置的 dpr 缩放变换下使用）。
 * 在布局视口中用任务面板的 getBoundingClientRect()（宽+高）挖去一块矩形后，对剩余区域做面积加权质心；
 * 同时计入面板占位在竖直方向上的影响（不再只用水平条带 + 整窗竖直中心）。
 */
function viewportFocusInCanvas() {
  const rect = canvas.getBoundingClientRect();
  const W = window.innerWidth;
  const H = window.innerHeight;

  const panel = document.getElementById("objectives-panel");
  if (!panel || panel.classList.contains("hidden")) {
    const vv = window.visualViewport;
    const cy = vv ? vv.offsetTop + vv.height * 0.5 : H * 0.5;
    return {
      fx: W * 0.5 - rect.left,
      fy: cy - rect.top,
    };
  }

  const pr = panel.getBoundingClientRect();
  if (pr.width < 4 || pr.height < 4) {
    return { fx: W * 0.5 - rect.left, fy: H * 0.5 - rect.top };
  }

  const m = 8;
  let pl = pr.left - m;
  let prr = pr.right + m;
  let pt = pr.top - m;
  let pb = pr.bottom + m;
  pl = Math.max(0, Math.min(pl, W));
  prr = Math.max(0, Math.min(prr, W));
  pt = Math.max(0, Math.min(pt, H));
  pb = Math.max(0, Math.min(pb, H));
  if (prr <= pl + 1 || pb <= pt + 1) {
    return { fx: W * 0.5 - rect.left, fy: H * 0.5 - rect.top };
  }

  const pieces = [
    [0, pl, 0, H],
    [pl, prr, 0, pt],
    [pl, prr, pb, H],
    [prr, W, 0, H],
  ];

  let sumAx = 0;
  let sumAy = 0;
  let sumA = 0;
  for (const [x0, x1, y0, y1] of pieces) {
    const aw = Math.max(0, x1 - x0);
    const ah = Math.max(0, y1 - y0);
    const a = aw * ah;
    if (a < 0.5) continue;
    const cx = (x0 + x1) * 0.5;
    const cy = (y0 + y1) * 0.5;
    sumAx += cx * a;
    sumAy += cy * a;
    sumA += a;
  }

  if (sumA < 0.5) {
    return { fx: W * 0.5 - rect.left, fy: H * 0.5 - rect.top };
  }

  const cenX = sumAx / sumA;
  const cenY = sumAy / sumA;
  return {
    fx: cenX - rect.left,
    fy: cenY - rect.top,
  };
}

if (canvas) {
  canvas.addEventListener("mousemove", (ev) => {
    const br = canvas.getBoundingClientRect();
    mouseCanvasX = ev.clientX - br.left;
    mouseCanvasY = ev.clientY - br.top;
  });
}

window.addEventListener("keydown", (e) => {
  const k = e.key.toLowerCase();
  if (["w", "a", "s", "d", "e", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(k)) {
    keys.add(k);
    e.preventDefault();
  }
});
window.addEventListener("keyup", (e) => {
  keys.delete(e.key.toLowerCase());
});

function blockedExplorerRects() {
  const zs = latestState?.explorer_zones;
  if (!zs?.length) return [];
  return zs.filter((z) => z.blocks_movement);
}

function movementObstacleAt(px, py, r) {
  if (px - r < 0 || px + r > WORLD.w || py - r < 0 || py + r > WORLD.h) return { kind: "world" };
  for (const z of blockedExplorerRects()) {
    const rect = { x: z.x, y: z.y, w: z.w, h: z.h };
    if (circleHitsRect(px, py, r, rect))
      return { kind: "access", reason_zh: z.reason_zh || "此处暂不可进入。" };
  }
  const tr = movementObstacleFromTiles(px, py, r);
  if (tr) return tr;
  return null;
}

function canPlace(px, py, r) {
  return movementObstacleAt(px, py, r) === null;
}

function bumpAccessDenied(reasonZh) {
  const now = performance.now();
  if (now - lastAccessToastAt < 2600) return;
  lastAccessToastAt = now;
  showToast(reasonZh, 4000);
}

function bumpOffroad() {
  const now = performance.now();
  if (now - lastOffroadToastAt < 1200) return;
  lastOffroadToastAt = now;
  showToast("仅可沿路面前进。", 2200);
}

function tryMove(nx, ny) {
  const r = PLAYER.r;
  const ox = movementObstacleAt(nx, PLAYER.y, r);
  if (!ox) PLAYER.x = nx;
  else if (ox.kind === "access") bumpAccessDenied(ox.reason_zh);
  else if (ox.kind === "offroad") bumpOffroad();

  const oy = movementObstacleAt(PLAYER.x, ny, r);
  if (!oy) PLAYER.y = ny;
  else if (oy.kind === "access") bumpAccessDenied(oy.reason_zh);
  else if (oy.kind === "offroad") bumpOffroad();
}

/** 与玩家相同的分轴碰撞试探；不向 NPC 弹出禁区 toast */
function tryMoveEntity(cx, cy, nx, ny, r) {
  const ox = movementObstacleAt(nx, cy, r);
  let x = cx;
  let y = cy;
  if (!ox) x = nx;
  const oy = movementObstacleAt(x, ny, r);
  if (!oy) y = ny;
  return { x, y };
}

/** 路格中心（与可走判定共用 ENTITY_R）；格左上为 TILE 对齐锚点 */
function tileCenterFromGrid(tx, ty) {
  return { x: tx * TILE + TILE * 0.5, y: ty * TILE + TILE * 0.5 };
}

function pixelToTileGrid(px, py) {
  return {
    tx: Math.min(MAP_TILES_X - 1, Math.max(0, Math.floor(px / TILE))),
    ty: Math.min(MAP_TILES_Y - 1, Math.max(0, Math.floor(py / TILE))),
  };
}

/** 是否与 NPC 可走规则一致（路格 + 禁区/建筑）；格心试探 */
function canNpcStandPixel(px, py) {
  return !movementObstacleAt(px, py, ENTITY_R);
}

function canNpcStandOnRoadTile(tx, ty) {
  if (tileTypeAt(tx, ty) !== T_ROAD) return false;
  const c = tileCenterFromGrid(tx, ty);
  return canNpcStandPixel(c.x, c.y);
}

/** 像素附近最近可站立路格（方形环扩散） */
function nearestStandableRoadTile(px, py, maxRing = 100) {
  const { tx: tx0, ty: ty0 } = pixelToTileGrid(px, py);
  for (let ring = 0; ring <= maxRing; ring++) {
    const yTop = ty0 - ring;
    const yBot = ty0 + ring;
    const xLeft = tx0 - ring;
    const xRight = tx0 + ring;
    if (ring === 0 && canNpcStandOnRoadTile(tx0, ty0)) return { tx: tx0, ty: ty0 };
    if (ring === 0) continue;
    for (let dx = -ring; dx <= ring; dx++) {
      const txA = tx0 + dx;
      if (canNpcStandOnRoadTile(txA, yTop)) return { tx: txA, ty: yTop };
      if (canNpcStandOnRoadTile(txA, yBot)) return { tx: txA, ty: yBot };
    }
    for (let dy = -ring + 1; dy <= ring - 1; dy++) {
      const tyA = ty0 + dy;
      if (canNpcStandOnRoadTile(xLeft, tyA)) return { tx: xLeft, ty: tyA };
      if (canNpcStandOnRoadTile(xRight, tyA)) return { tx: xRight, ty: tyA };
    }
  }
  return null;
}

/** BFS 结果去掉共线中段，仅在路口／拐弯处保留路点（横纵切换） */
function compressCardinalRoadTilePath(path) {
  if (path.length <= 2) return path.slice();
  const out = [path[0]];
  for (let i = 1; i < path.length - 1; i++) {
    const udx = Math.sign(path[i].tx - path[i - 1].tx);
    const udy = Math.sign(path[i].ty - path[i - 1].ty);
    const vdx = Math.sign(path[i + 1].tx - path[i].tx);
    const vdy = Math.sign(path[i + 1].ty - path[i].ty);
    if (udx !== vdx || udy !== vdy) out.push(path[i]);
  }
  out.push(path[path.length - 1]);
  return out;
}

function bfsRoadTilePath(start, goal) {
  if (start.tx === goal.tx && start.ty === goal.ty) return [start];
  const N = MAP_TILES_X * MAP_TILES_Y;
  const parent = new Int32Array(N).fill(-1);
  const ii = (tx, ty) => ty * MAP_TILES_X + tx;
  const si = ii(start.tx, start.ty);
  const gi = ii(goal.tx, goal.ty);
  parent[si] = si;
  const q = [si];
  for (let qi = 0; qi < q.length; qi++) {
    const cur = q[qi];
    if (cur === gi) break;
    const tcx = cur % MAP_TILES_X;
    const tcy = (cur / MAP_TILES_X) | 0;
    for (const [dx, dy] of [
      [1, 0],
      [-1, 0],
      [0, 1],
      [0, -1],
    ]) {
      const nx = tcx + dx;
      const ny = tcy + dy;
      if (nx < 0 || ny < 0 || nx >= MAP_TILES_X || ny >= MAP_TILES_Y) continue;
      const ni = ii(nx, ny);
      if (parent[ni] !== -1) continue;
      if (!canNpcStandOnRoadTile(nx, ny)) continue;
      parent[ni] = cur;
      q.push(ni);
    }
  }
  if (parent[gi] === -1) return null;
  const tiles = [];
  let w = gi;
  while (w !== si) {
    tiles.push({ tx: w % MAP_TILES_X, ty: (w / MAP_TILES_X) | 0 });
    w = parent[w];
  }
  tiles.push(start);
  tiles.reverse();
  return tiles;
}

/** 压缩路点 → 像素；寻路失败时 roadPathWp = null → 再走直线兜底 */
function npcRebuildRoadWaypoints(b) {
  const st = nearestStandableRoadTile(b.x, b.y, 140);
  const en = nearestStandableRoadTile(b.targetX, b.targetY, 140);
  if (!st || !en) {
    b.roadPathWp = null;
    b.pathSegIx = 0;
    return;
  }
  const raw = bfsRoadTilePath(st, en);
  if (!raw || raw.length === 0) {
    b.roadPathWp = null;
    b.pathSegIx = 0;
    return;
  }
  const comp = compressCardinalRoadTilePath(raw);
  b.roadPathWp = comp.map((t) => tileCenterFromGrid(t.tx, t.ty));
  b.pathSegIx = b.roadPathWp.length > 1 ? 1 : 0;
}

/**
 * 朝 (tx,ty) 只沿横轴或纵轴移动一步（本帧），优先修正误差较大的一轴，
 * 与「沿街直行到路口再拐」观感一致（不在斜路上对角滑移）。
 */
function npcStepCardinalToward(cx, cy, tx, ty, stepMax, radius) {
  const dx = tx - cx;
  const dy = ty - cy;
  if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return { x: cx, y: cy, arrived: true };
  let stepX = 0;
  let stepY = 0;
  if (Math.abs(dx) >= Math.abs(dy)) {
    stepX = Math.sign(dx) * Math.min(Math.abs(dx), stepMax);
  } else {
    stepY = Math.sign(dy) * Math.min(Math.abs(dy), stepMax);
  }
  const moved = tryMoveEntity(cx, cy, cx + stepX, cy + stepY, radius);
  return { x: moved.x, y: moved.y, arrived: false };
}

/** NPC 物理位置与当前日程目标（与玩家同速、同半径碰撞） */
const npcBodies = {};

function isNpcVisibleOnMap(id) {
  const srv = latestState?.overworld_npcs;
  if (!srv?.length) return true;
  const row = srv.find((r) => r.id === id);
  return row ? row.visible !== false : true;
}

function syncNpcTargetsFromSchedule(pos) {
  if (!pos) return;
  for (const [id, p] of Object.entries(pos)) {
    const key = `${Math.round(p.x)}:${Math.round(p.y)}`;
    if (!npcBodies[id]) {
      npcBodies[id] = {
        x: p.x,
        y: p.y,
        targetX: p.x,
        targetY: p.y,
        goalKey: key,
        roadPathWp: null,
        pathSegIx: 0,
      };
      npcRebuildRoadWaypoints(npcBodies[id]);
      continue;
    }
    if (npcBodies[id].goalKey !== key) {
      npcBodies[id].targetX = p.x;
      npcBodies[id].targetY = p.y;
      npcBodies[id].goalKey = key;
      npcRebuildRoadWaypoints(npcBodies[id]);
    }
  }
}

/**
 * NPC：`speed × dt` 与玩家一致。优先沿路格 BFS 路径，每帧仅在 X 或 Y 上迈步（直行到路口再拐）；
 * 无路或卡住时退回原来的方向向量 + tryMoveEntity 贴墙滑动。
 */
function stepAllNpcBodies(dt) {
  const r = PLAYER.r;
  const sp = PLAYER.speed * dt;
  for (const id of Object.keys(npcBodies)) {
    if (!isNpcVisibleOnMap(id)) continue;
    const b = npcBodies[id];
    if (movementObstacleAt(b.x, b.y, r)) {
      b.x = b.targetX;
      b.y = b.targetY;
    }
    const dx = b.targetX - b.x;
    const dy = b.targetY - b.y;
    const len = Math.hypot(dx, dy);
    if (len < 10) {
      b.x = b.targetX;
      b.y = b.targetY;
      continue;
    }
    const road = b.roadPathWp;
    if (road && road.length >= 2) {
      while (b.pathSegIx < road.length) {
        const wp = road[b.pathSegIx];
        const res = npcStepCardinalToward(b.x, b.y, wp.x, wp.y, sp, r);
        if (res.arrived) {
          b.pathSegIx++;
          continue;
        }
        b.x = res.x;
        b.y = res.y;
        break;
      }
      if (b.pathSegIx >= road.length) {
        const fin = npcStepCardinalToward(b.x, b.y, b.targetX, b.targetY, sp, r);
        b.x = fin.x;
        b.y = fin.y;
      }
      continue;
    }
    const ux = dx / len;
    const uy = dy / len;
    const res = tryMoveEntity(b.x, b.y, b.x + ux * sp, b.y + uy * sp, r);
    b.x = res.x;
    b.y = res.y;
  }
}

function pickHoveredExplorerZone() {
  const zs = latestState?.explorer_zones;
  if (!zs?.length) return null;
  const vw = canvas.clientWidth;
  const z = getWorldViewZoom(vw);
  const { fx, fy } = viewportFocusInCanvas();
  const wx = camX + (mouseCanvasX - fx) / z;
  const wy = camY + (mouseCanvasY - fy) / z;
  for (let i = zs.length - 1; i >= 0; i--) {
    const z = zs[i];
    if (wx >= z.x && wx <= z.x + z.w && wy >= z.y && wy <= z.y + z.h) return z;
  }
  return null;
}

function pollInput(dt) {
  if (isWorkshopOpen() || isMemoryFlashOverlayVisible()) return;
  let dx = 0;
  let dy = 0;
  if (keys.has("w") || keys.has("arrowup")) dy -= 1;
  if (keys.has("s") || keys.has("arrowdown")) dy += 1;
  if (keys.has("a") || keys.has("arrowleft")) dx -= 1;
  if (keys.has("d") || keys.has("arrowright")) dx += 1;
  if (dx === 0 && dy === 0) return;
  const len = Math.hypot(dx, dy) || 1;
  dx /= len;
  dy /= len;
  const sp = PLAYER.speed * dt;
  tryMove(PLAYER.x + dx * sp, PLAYER.y + dy * sp);
}

function dist(ax, ay, bx, by) {
  return Math.hypot(ax - bx, ay - by);
}

/** 点距轴对齐矩形（点在矩形内为 0）— 设施交互：以外沿距离判定是否足够靠近 */
function distPointToRect(px, py, rect) {
  const nx = Math.max(rect.x, Math.min(px, rect.x + rect.w));
  const ny = Math.max(rect.y, Math.min(py, rect.y + rect.h));
  return Math.hypot(px - nx, py - ny);
}

/** NPC：与圆心距离小于此值可交互 */
const NPC_INTERACT_RADIUS = 102;
/** 设施：与占地外沿距离 ≤ 此值时可交互（沿路缘贴近，远处无效） */
const FACILITY_INTERACT_MAX = 52;

/** 路点 POI：与圆心距离小于 radius 可交互 */
const POI_INTERACT_RADIUS = 54;

function nearestInteract() {
  let best = null;
  let bestD = NPC_INTERACT_RADIUS;
  for (const n of effectiveNpcs()) {
    const d = dist(PLAYER.x, PLAYER.y, n.x, n.y);
    if (d < bestD) {
      bestD = d;
      best = { kind: "npc", ...n };
    }
  }
  for (const p of MAP_POIS) {
    const d = dist(PLAYER.x, PLAYER.y, p.x, p.y);
    const rad = p.radius ?? POI_INTERACT_RADIUS;
    if (d > rad) continue;
    if (!best || d < bestD) {
      bestD = d;
      best = { kind: p.kind, name: p.name, id: p.id, blurb: p.blurb };
    }
  }
  for (const f of FACILITIES) {
    const d = distPointToRect(PLAYER.x, PLAYER.y, facilityFootprint(f));
    if (d > FACILITY_INTERACT_MAX) continue;
    if (!best || d < bestD) {
      bestD = d;
      best = { kind: "facility", name: f.name, id: f.id };
    }
  }
  return best;
}

function drawWorld(vw, vh) {
  ctx.save();
  // 镜头紧贴角色；焦点对齐浏览器窗口视觉中心（非画布盒子中心）
  camX = PLAYER.x;
  camY = PLAYER.y;

  const viewZoom = getWorldViewZoom(vw);
  const { fx, fy } = viewportFocusInCanvas();
  ctx.translate(fx, fy);
  ctx.scale(viewZoom, viewZoom);
  ctx.translate(-camX, -camY);

  const labelScale = 1 / viewZoom;
  const fzFacility = Math.max(11, Math.round(21 * labelScale));
  const fzNpcName = Math.max(11, Math.round(15 * labelScale));
  const fzNpcBlur = Math.max(9, Math.round(12 * labelScale));
  const fzNpcHint = Math.max(8, Math.round(11 * labelScale));
  ensureTileTerrainCanvas();
  ctx.drawImage(tileTerrainCanvas, 0, 0);

  const inc = incursionRatio();
  drawShoreIntrusion(ctx, inc, performance.now());

  // 设施 POI：sprite 贴图 + 标牌（碰撞体块由 TILE_MAP 的 core 铺设）
  for (const f of FACILITIES) {
    const draw = facilityDrawRect(f);
    const foot = facilityFootprint(f);
    // 按需加载设施贴图（首次渲染时触发，has() 防重复）
    if (!facilitySpriteImages.has(f.id)) loadFacilitySprite(f.id);
    const facImg = facilitySpriteImages.get(f.id);
    const hasSprite = facImg?.complete && facImg.naturalWidth > 0;
    if (hasSprite) {
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(facImg, draw.x, draw.y, draw.w, draw.h);
    } else {
      ctx.fillStyle = "rgba(18, 24, 34, 0.35)";
      ctx.strokeStyle = "rgba(160, 200, 255, 0.45)";
      ctx.lineWidth = 2;
      ctx.fillRect(draw.x, draw.y, draw.w, draw.h);
      ctx.strokeRect(draw.x, draw.y, draw.w, draw.h);
    }

    const fitFs = Math.round(
      Math.min(
        fzFacility,
        Math.max(10, Math.min(draw.h * 0.38, draw.w / Math.max(1, f.name.length * 0.58)))
      )
    );
    ctx.font = `bold ${fitFs}px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.shadowColor = "rgba(0, 0, 0, 0.72)";
    ctx.shadowBlur = 5;
    ctx.fillStyle = "rgba(220, 235, 255, 0.96)";
    ctx.fillText(f.name, foot.x + foot.w / 2, foot.y + foot.h * 0.42);
    ctx.shadowBlur = 0;
    ctx.textBaseline = "alphabetic";
  }

  for (const p of MAP_POIS) {
    const r = 22;
    const isCommand = p.id === "underground_workshop_command";
    ctx.fillStyle = isCommand ? "rgba(90, 200, 255, 0.16)" : "rgba(255, 200, 90, 0.18)";
    ctx.strokeStyle = isCommand ? "rgba(120, 220, 255, 0.78)" : "rgba(255, 210, 120, 0.72)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.font = `bold ${Math.max(10, Math.round(13 * labelScale))}px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillStyle = isCommand ? "rgba(200, 245, 255, 0.96)" : "rgba(255, 236, 190, 0.96)";
    ctx.shadowColor = "rgba(0, 0, 0, 0.72)";
    ctx.shadowBlur = 4;
    ctx.fillText(p.name, p.x, p.y - r - 8);
    if (p.blurb) {
      ctx.font = `${Math.max(8, Math.round(10 * labelScale))}px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif`;
      ctx.fillStyle = isCommand ? "rgba(160, 220, 255, 0.72)" : "rgba(255, 220, 160, 0.72)";
      ctx.fillText(p.blurb, p.x, p.y + r + 12);
    }
    ctx.shadowBlur = 0;
    ctx.textBaseline = "alphabetic";
  }

  // NPC（可见性由剧情状态驱动）
  for (const n of effectiveNpcs()) {
    const pulse = 0.6 + 0.4 * Math.sin(performance.now() / 420);
    ctx.beginPath();
    ctx.arc(n.x, n.y, 12 + pulse * 2, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 200, 120, 0.95)";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "rgba(40, 30, 20, 0.65)";
    ctx.stroke();

    ctx.fillStyle = "rgba(230, 240, 255, 0.95)";
    ctx.font = `${fzNpcName}px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillText(n.name, n.x, n.y - 42);
    ctx.font = `${fzNpcBlur}px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif`;
    ctx.fillStyle = "rgba(200, 215, 235, 0.88)";
    ctx.fillText(n.blurb || "", n.x, n.y - 24);
    // hidden_line 不在地图上显示，避免提前泄露隐藏信息
  }

  // 玩家
  ctx.beginPath();
  ctx.arc(PLAYER.x, PLAYER.y, PLAYER.r, 0, Math.PI * 2);
  ctx.fillStyle = "rgba(120, 255, 200, 0.95)";
  ctx.fill();
  ctx.strokeStyle = "rgba(0, 0, 0, 0.45)";
  ctx.lineWidth = 3;
  ctx.stroke();

  ctx.restore();
}

function measureToastLineWidth(ctx, text) {
  return ctx.measureText(text).width;
}

/** 将提示拆成多行以适配 Toast 区域（简体与英文混合） */
function wrapToastText(ctx, text, maxW, maxLines) {
  const s = String(text || "").replace(/\r\n/g, "\n");
  if (!s) return [];
  const lines = [];
  let rest = s;
  const maxL = Math.max(1, maxLines);
  while (rest.length && lines.length < maxL) {
    if (measureToastLineWidth(ctx, rest) <= maxW) {
      lines.push(rest);
      break;
    }
    let low = 1;
    let high = rest.length;
    let fit = 1;
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      const chunk = rest.slice(0, mid);
      if (measureToastLineWidth(ctx, chunk) <= maxW) {
        fit = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
    if (fit < 1) fit = 1;
    lines.push(rest.slice(0, fit));
    rest = rest.slice(fit).trimStart();
  }
  if (rest.length && lines.length >= maxL) {
    const last = lines[lines.length - 1];
    let t = last;
    const ell = "…";
    while (t.length > 0 && measureToastLineWidth(ctx, t + ell) > maxW) t = t.slice(0, -1);
    lines[lines.length - 1] = (t || "…") + ell;
  }
  return lines;
}

/**
 * 基地资源条为 DOM 浮层（盖在 canvas 之上），必须用实际高度为岸线/下一步 HUD 让位。
 * 返回：资源条底边在主画布 CSS 坐标系中的 y（画布顶端为 0），已含小缝隙。
 */
function resourceStripBottomInCanvasPx() {
  const strip = document.getElementById("resource-strip");
  const cv = document.getElementById("game");
  if (!strip || !cv) return 78;
  const sr = strip.getBoundingClientRect();
  const cr = cv.getBoundingClientRect();
  if (cr.width < 2 || cr.height < 2) return 78;
  return Math.max(14, sr.bottom - cr.top + 4);
}

function drawHud(vw, vh) {
  const t = nearestInteract();
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  const hz = pickHoveredExplorerZone();
  if (hz?.blocks_movement && hz.reason_zh) {
    const title = hz.display_label_zh || hz.label_zh || "受限区域";
    const tipW = Math.min(460, vw - 24);
    const x = Math.min(Math.max(12, mouseCanvasX + 16), vw - tipW - 12);
    const y = Math.min(Math.max(20, mouseCanvasY + 16), vh - 92);
    ctx.font = "13px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
    const sub = hz.reason_zh.length > 120 ? `${hz.reason_zh.slice(0, 120)}…` : hz.reason_zh;
    const boxH = 68;
    ctx.fillStyle = "rgba(14, 22, 38, 0.94)";
    hudRoundRect(ctx, x, y, tipW, boxH, 10);
    ctx.fill();
    ctx.strokeStyle = "rgba(140, 200, 255, 0.4)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.textAlign = "left";
    ctx.fillStyle = "#e8f4ff";
    ctx.fillText(title.length > 42 ? `${title.slice(0, 42)}…` : title, x + 12, y + 26);
    ctx.fillStyle = "#9eb8d4";
    ctx.fillText(sub, x + 12, y + 50);
  }
  ctx.font = "11px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
  ctx.fillStyle = "rgba(200, 218, 238, 0.92)";
  ctx.textAlign = "right";
  ctx.shadowColor = "rgba(0, 0, 0, 0.6)";
  ctx.shadowBlur = 4;
  const { hh, mm } = gameClockHHMM();
  const slot = hh >= 8 && hh < 20 ? "昼" : "夜";
  const minsPer = REAL_MS_PER_GAME_HOUR / 60000;
  const clockLong = `游戏内 ${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")} ${slot} · 按现实时间流逝（≈${minsPer} 分钟/游戏小时）`;
  const clockShort = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")} ${slot} · ≈${minsPer.toFixed(1)}分/时`;
  let clockStr = vw < 520 ? clockShort : clockLong;
  if (ctx.measureText(clockStr).width > vw - 24) clockStr = clockShort;
  if (ctx.measureText(clockStr).width > vw - 24) {
    clockStr = `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")} ${slot}`;
  }
  ctx.fillText(clockStr, vw - 14, 28);
  ctx.shadowBlur = 0;
  ctx.textAlign = "left";

  const incPct = Math.round(incursionRatio() * 100);
  const stripBottomPx = resourceStripBottomInCanvasPx();
  const barX = 14;
  const hudMargin = 100; // HUD与资源条的额外间距，确保互不遮挡
  const intrusionLabelY = stripBottomPx + hudMargin;
  const intrusionBarY = intrusionLabelY + 22;
  const barW = Math.min(500, Math.max(300, vw * 0.58));
  const barH = 18;
  ctx.font = "700 21px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
  ctx.fillStyle = "rgba(218, 235, 255, 0.98)";
  ctx.fillText(`岸线侵入 · ${incPct}%`, barX, intrusionLabelY);
  ctx.fillStyle = "rgba(18, 28, 45, 0.92)";
  hudRoundRect(ctx, barX, intrusionBarY, barW, barH, 4);
  ctx.fill();
  ctx.strokeStyle = "rgba(110, 210, 255, 0.42)";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  const fillW = Math.max(0, (barW - 4) * (incPct / 100));
  if (fillW > 0.5) {
    const bg = ctx.createLinearGradient(barX, 0, barX + barW, 0);
    bg.addColorStop(0, "rgba(0, 220, 255, 0.82)");
    bg.addColorStop(0.5, "rgba(160, 100, 255, 0.72)");
    bg.addColorStop(1, "rgba(255, 120, 160, 0.62)");
    ctx.fillStyle = bg;
    hudRoundRect(ctx, barX + 2, intrusionBarY + 2, fillW, barH - 4, 2);
    ctx.fill();
  }

  /** 左侧「下一步目标」叠在岸线进度条下方，与右侧任务栏解耦 */
  let leftHudStackBottom = intrusionBarY + barH;
  if (latestState) {
    const g = computeNextStepGuide(latestState);
    if (g) {
      const bodyRaw =
        g.label_zh.startsWith("前往") || g.label_zh.startsWith("靠近")
          ? g.label_zh
          : `下一步：${g.label_zh}`;
      let yLine = leftHudStackBottom + 18;
      ctx.font = "700 16px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
      ctx.fillStyle = "rgba(150, 210, 255, 0.98)";
      ctx.fillText("下一步目标", barX, yLine);
      yLine += 28;
      ctx.font = "18px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
      ctx.fillStyle = "rgba(232, 243, 252, 0.98)";
      const bodyLines = wrapToastText(ctx, bodyRaw, barW, 5);
      const stepLineGap = 26;
      for (const ln of bodyLines) {
        ctx.fillText(ln, barX, yLine);
        yLine += stepLineGap;
      }
      leftHudStackBottom = yLine + 6;
    }
  }

  if (latestState) drawObjectiveGuideArrow(vw, vh, leftHudStackBottom + 6);

  if (t) {
    const raw =
      t.kind === "npc"
        ? `靠近：${t.name}（${t.blurb}）— 按 E 互动`
        : t.kind === "facility"
          ? `贴近设施外墙：${t.name} — 按 E 查看`
          : `${t.name} — 按 E 互动`;
    const bw = Math.min(720, vw - 24);
    const { fx: winCx } = viewportFocusInCanvas();
    const bx = Math.min(Math.max(12, winCx - bw / 2), vw - bw - 12);
    ctx.font = "15px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
    const lines = wrapToastText(ctx, raw, bw - 44, 2);
    const lineGap = 24;
    const padV = 20;
    const bhh = Math.max(56, lines.length * lineGap + padV);
    const by = vh - bhh - 32;
    ctx.fillStyle = "rgba(14, 22, 38, 0.94)";
    hudRoundRect(ctx, bx, by, bw, bhh, 12);
    ctx.fill();
    ctx.strokeStyle = "rgba(140, 200, 255, 0.35)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = "#e8f4ff";
    ctx.textAlign = "center";
    const line0Y = by + padV + 16;
    for (let i = 0; i < lines.length; i++) {
      ctx.fillText(lines[i], winCx, line0Y + i * lineGap);
    }
    ctx.textAlign = "left";
  }

  const intrusionStackBottom = leftHudStackBottom;
  if (toast && performance.now() < toastUntil) {
    const tw = Math.min(vw - 28, 560);
    const padL = 14;
    ctx.font = "13px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
    const innerW = tw - 24;
    const toastLines = wrapToastText(ctx, toast, innerW, 4);
    const lineH = 17;
    const padY = 12;
    const th = Math.max(34, toastLines.length * lineH + padY * 2);
    let ty = Math.max(stripBottomPx + 8, padY);
    if (th > 46 || toastLines.length > 1) {
      ty = Math.max(intrusionStackBottom + 10, stripBottomPx + 12);
    }
    ctx.fillStyle = "rgba(14, 22, 38, 0.94)";
    hudRoundRect(ctx, padL, ty, tw, th, 10);
    ctx.fill();
    ctx.strokeStyle = "rgba(126, 184, 255, 0.35)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#e8f7ff";
    ctx.textAlign = "left";
    toastLines.forEach((ln, i) => {
      ctx.fillText(ln, 26, ty + padY + 14 + i * lineH);
    });
  }

  ctx.restore();
}

function drawMinimap() {
  if (!mctx || !mini) return;
  const mw = mini.width;
  const mh = mini.height;
  mctx.clearRect(0, 0, mw, mh);
  const sx = mw / WORLD.w;
  const sy = mh / WORLD.h;

  mctx.imageSmoothingEnabled = false;
  ensureTileTerrainCanvas();
  mctx.drawImage(tileTerrainCanvas, 0, 0, mw, mh);

  const incM = incursionRatio();
  const depthM = Math.min(mw * 0.52, 8 + incM * mw * 0.45);
  const mg = mctx.createLinearGradient(0, 0, depthM, 0);
  mg.addColorStop(0, `rgba(0, 210, 255, ${0.28 + incM * 0.28})`);
  mg.addColorStop(0.45, `rgba(120, 60, 200, ${0.12 + incM * 0.15})`);
  mg.addColorStop(1, "rgba(10, 18, 30, 0)");
  mctx.save();
  mctx.globalAlpha = 0.52;
  mctx.fillStyle = mg;
  mctx.fillRect(0, 0, depthM, mh);
  mctx.restore();
  mctx.strokeStyle = `rgba(180, 240, 255, ${0.35 + incM * 0.35})`;
  mctx.lineWidth = 1;
  mctx.beginPath();
  mctx.moveTo(depthM, 0);
  mctx.lineTo(depthM, mh);
  mctx.stroke();

  for (const f of FACILITIES) {
    const c = facilityFootprint(f);
    mctx.fillStyle = "rgba(80, 130, 210, 0.7)";
    mctx.fillRect(c.x * sx, c.y * sy, Math.max(1, c.w * sx), Math.max(1, c.h * sy));
  }

  for (const n of effectiveNpcs()) {
    mctx.fillStyle = "rgba(255, 200, 120, 0.9)";
    mctx.fillRect(n.x * sx - 1.5, n.y * sy - 1.5, 3, 3);
  }

  mctx.fillStyle = "#6fffc2";
  mctx.beginPath();
  mctx.arc(PLAYER.x * sx, PLAYER.y * sy, 3.2, 0, Math.PI * 2);
  mctx.fill();

  const gMin = computeNextStepGuide(latestState);
  if (gMin) {
    const gx = gMin.wx * sx;
    const gy = gMin.wy * sy;
    mctx.fillStyle = "rgba(90, 255, 190, 0.95)";
    mctx.beginPath();
    mctx.moveTo(gx, gy - 4);
    mctx.lineTo(gx - 3.5, gy + 3.5);
    mctx.lineTo(gx + 3.5, gy + 3.5);
    mctx.closePath();
    mctx.fill();
  }

  // 视锥框（小地图上的视野范围，与主画布 zoom 一致）
  const vw = canvas.clientWidth;
  const vh = canvas.clientHeight;
  const vz = getWorldViewZoom(vw);
  const visW = vw / vz;
  const visH = vh / vz;
  const vx = (camX - visW / 2) * sx;
  const vy = (camY - visH / 2) * sy;
  mctx.strokeStyle = "rgba(200, 255, 255, 0.55)";
  mctx.lineWidth = 1;
  mctx.strokeRect(vx, vy, visW * sx, visH * sy);
}

function frame(ts) {
  try {
    ensureMainGameSceneVisible();
    if (!ctx || !canvas) {
      requestAnimationFrame(frame);
      return;
    }
    if (!lastTs) lastTs = ts;
    const dt = Math.min(0.05, (ts - lastTs) / 1000);
    lastTs = ts;

    tickWorldClock(ts);

    if (!isWorkshopOpen() && !isMemoryFlashOverlayVisible()) {
      pollInput(dt);
      npcScheduleSnapshot = scheduledNpcWorldPositions(latestState);
      syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
      stepAllNpcBodies(dt);

      if (keys.has("e")) {
        const t = nearestInteract();
        if (t) openStoryFromInteract(t);
        keys.delete("e");
      }
    }

    const vw = Math.max(1, canvas.clientWidth);
    const vh = Math.max(1, canvas.clientHeight);
    const hzHover = pickHoveredExplorerZone();
    canvas.style.cursor = hzHover?.blocks_movement ? "help" : "crosshair";
    ctx.clearRect(0, 0, vw, vh);
    drawWorld(vw, vh);
    drawHud(vw, vh);
    drawMinimap();
  } catch (err) {
    console.error("[explorer] frame error:", err);
  }
  requestAnimationFrame(frame);
}

npcScheduleSnapshot = scheduledNpcWorldPositions(null);
syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
if (ctx && canvas) requestAnimationFrame(frame);
