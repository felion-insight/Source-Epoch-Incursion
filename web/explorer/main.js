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

/**
 * zone：片区示意；core：阻挡行走的建筑核心。设施 id 与 game/narrative_map.py API 一致（comm/mine/lab…）。
 */
/** 主纵街 x=2860 宽 96 → 东缘 2908；主轴 y=2140 宽 84 → 北缘 2098、南缘 2182。建筑 core 与路缘留约 4 单位间隙。 */
const FACILITIES = [
  { id: "sunk_lab", name: "沉没实验室", zone: { x: 2552, y: 280, w: 1080, h: 480 }, core: { x: 2912, y: 440, w: 460, h: 260 } },
  { id: "mine_ruins", name: "废弃矿场表层", zone: { x: 2532, y: 820, w: 1160, h: 500 }, core: { x: 2912, y: 980, w: 480, h: 300 } },
  { id: "helipad", name: "停机坪", zone: { x: 3320, y: 1000, w: 560, h: 360 }, core: { x: 3520, y: 1120, w: 260, h: 160 } },
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
        if (tileCenterInAabb(cx, cy, f.core)) {
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

function startMapTileTexturesLoad() {
  wireTileImage(voidTileTexture, "./assets/tile_void.jpg", "void");
  wireTileImage(roadTileTexture, "./assets/tile_road.jpg", "road");
  wireTileImage(buildTileTexture, "./assets/tile_build.jpg", "build");
  wireTileImage(roadTileFallbackTexture, "./assets/walkable_floor_tile.png", "road_fallback");
}

startMapTileTexturesLoad();

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
      return c ? { wx: c.wx, wy: c.wy, label_zh: `前往「${c.name}」确认升级倾向` } : null;
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
 * 根据当前游戏时刻与存档状态计算 NPC 日程目标点（片区内锚点）；实际位置由 stepAllNpcBodies 走向目标。
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
  const base = NPCS.filter((n) => n.id !== "echo_7");
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

/** 去掉尾部 /，避免出现 //api/... 导致服务端路径与路由不一致（404） */
const API_BASE = (
  new URLSearchParams(location.search).get("api") || "http://127.0.0.1:8787"
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
  const base = (API_BASE || "").trim().replace(/\/+$/, "") || "http://127.0.0.1:8787";
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
const storySpriteBlock = document.getElementById("story-sprite-block");
const storySpriteLabel = document.getElementById("story-sprite-label");
const storyTextbox = document.getElementById("story-textbox");
const storyPanel = document.getElementById("story-panel");
const storyAiLine = document.getElementById("story-ai-line");
const storyAdvanceHint = document.getElementById("story-advance-hint");
const storyClose = document.getElementById("story-close");

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

function setPortraitPlaceholder(kindId, labelText) {
  const c = PORTRAIT_NPC[kindId] || PORTRAIT_FACILITY[kindId] || "#3d4f66";
  storySpriteBlock.style.background = c;
  storySpriteLabel.textContent = labelText || "";
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
    r = await fetch(url, { ...options, headers });
  } catch (e) {
    const msg = e?.message || String(e);
    throw new Error(
      `${msg.includes("Failed to fetch") || msg.includes("NetworkError") ? "无法连接服务器" : msg} · 请先在本机运行剧情 API：python -m game（默认 8787）；若端口不同请在地址栏加 ?api=http://127.0.0.1:端口`,
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
    <p class="explorer-api-banner__body">静态页面当前请求的接口基址为 <kbd>${esc}</kbd>。请在<strong>另一个终端</strong>于仓库根目录运行 <kbd>python -m game</kbd>（默认 <kbd>127.0.0.1:8787</kbd>），然后<strong>刷新本页</strong>。端口不一致时用地址参数：<kbd>?api=http://127.0.0.1:你的端口</kbd></p>${errLine}`;
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
    showToast(String(e.message || e), 4200);
  }
  await refreshTopBar();
}

let facilitySimBackdrop = null;
let facilitySimRaf = null;

function closeFacilitySimLayerIfOpen() {
  if (facilitySimRaf != null) {
    cancelAnimationFrame(facilitySimRaf);
    facilitySimRaf = null;
  }
  if (!facilitySimBackdrop || facilitySimBackdrop.classList.contains("hidden")) return false;
  facilitySimBackdrop.classList.add("hidden");
  facilitySimBackdrop.setAttribute("aria-hidden", "true");
  return true;
}

function ensureFacilitySimBackdrop() {
  if (facilitySimBackdrop) return facilitySimBackdrop;
  const bd = document.createElement("div");
  bd.id = "facility-sim-backdrop";
  bd.className = "facility-sim-backdrop hidden";
  bd.setAttribute("aria-hidden", "true");
  bd.innerHTML = `
    <div class="facility-sim-panel" role="dialog" aria-modal="true" aria-labelledby="facility-sim-title">
      <button type="button" class="facility-sim-close" aria-label="关闭">×</button>
      <h2 id="facility-sim-title" class="facility-sim-title"></h2>
      <p class="facility-sim-lead"></p>
      <label class="facility-sim-label" for="facility-sim-select">选择本轮作业类型</label>
      <select id="facility-sim-select" class="facility-sim-select"></select>
      <p class="facility-sim-act-hint"></p>
      <div class="facility-sim-game" aria-label="校准小游戏">
        <div class="facility-sim-strip">
          <div class="facility-sim-green"></div>
          <div class="facility-sim-needle"></div>
        </div>
        <div class="facility-sim-game-meta"></div>
        <button type="button" class="facility-sim-hit">点击校准（需连续 3 次命中）</button>
      </div>
      <button type="button" class="facility-sim-submit">提交作业结算</button>
      <p class="facility-sim-footnote">说明：结算仍走服务器资源活动校验；成功与否由活动内置概率决定。侧栏仍可执行同类行动。</p>
    </div>`;
  bd.addEventListener("click", (ev) => {
    if (ev.target === bd) closeFacilitySimLayerIfOpen();
  });
  bd.querySelector(".facility-sim-close").addEventListener("click", () => closeFacilitySimLayerIfOpen());
  document.body.appendChild(bd);
  facilitySimBackdrop = bd;
  return bd;
}

/** 静默期设施专用全屏工作台：短时校准 + POST /api/sim/activity/run */
function openFacilitySimWorkbench(fac, overlay) {
  closeFacilitySimLayerIfOpen();

  const bd = ensureFacilitySimBackdrop();
  const title = bd.querySelector(".facility-sim-title");
  const lead = bd.querySelector(".facility-sim-lead");
  const sel = bd.querySelector(".facility-sim-select");
  const actHint = bd.querySelector(".facility-sim-act-hint");
  const green = bd.querySelector(".facility-sim-green");
  const needle = bd.querySelector(".facility-sim-needle");
  const meta = bd.querySelector(".facility-sim-game-meta");
  const hitBtn = bd.querySelector(".facility-sim-hit");
  const submitBtn = bd.querySelector(".facility-sim-submit");

  title.textContent = `${fac.name} · 静默工作台`;
  lead.textContent = overlay.manual_hint_zh || "";

  sel.replaceChildren();
  for (const a of overlay.activities || []) {
    const o = document.createElement("option");
    o.value = a.activity_id;
    const rp = a.reward_preview || {};
    const gain = Object.entries(rp)
      .filter(([, v]) => Number(v))
      .map(([k, v]) => `${k}+${v}`)
      .join(" / ");
    o.textContent = `${a.run_kind_zh || a.activity_id}（${gain || "参见预览"}）`;
    if (!a.can_run_now) o.disabled = true;
    sel.appendChild(o);
  }

  function updateActHint() {
    const aid = sel.value;
    const row = (overlay.activities || []).find((x) => String(x.activity_id) === String(aid));
    if (!row) {
      actHint.textContent = "";
      return;
    }
    actHint.textContent = row.can_run_now
      ? `行前消耗：能量 ${row.cost_preview?.energy ?? 0} · 补给 ${row.cost_preview?.food ?? 0} · ${row.incursion_notes || ""}`
      : row.blocked_reason_zh || "当前不可执行该项作业";
  }

  sel.onchange = updateActHint;
  updateActHint();

  let phase = 0;
  let greenCenter = 0.5;
  let successes = 0;

  function placeGreen() {
    greenCenter = 0.18 + Math.random() * 0.64;
    const half = 0.11;
    green.style.left = `${(greenCenter - half) * 100}%`;
    green.style.width = `${half * 2 * 100}%`;
  }

  placeGreen();

  function tick() {
    phase += 0.07;
    const t = (Math.sin(phase) + 1) / 2;
    needle.style.left = `${t * 100}%`;
    needle.dataset.t = String(t);
    facilitySimRaf = requestAnimationFrame(tick);
  }

  hitBtn.disabled = false;
  submitBtn.disabled = true;
  successes = 0;
  meta.textContent = "命中 0 / 3";

  hitBtn.onclick = () => {
    const t = Number(needle.dataset.t || "0");
    if (Math.abs(t - greenCenter) <= 0.11) {
      successes++;
      meta.textContent = `命中 ${successes} / 3`;
      placeGreen();
      if (successes >= 3) {
        if (facilitySimRaf != null) cancelAnimationFrame(facilitySimRaf);
        facilitySimRaf = null;
        hitBtn.disabled = true;
        meta.textContent = "校准完成，可提交结算。";
        submitBtn.disabled = false;
      }
    } else {
      showToast("未命中稳定区：指针需在绿色区间内。", 2400);
    }
  };

  submitBtn.onclick = async () => {
    const aid = sel.value;
    const row = (overlay.activities || []).find((x) => String(x.activity_id) === String(aid));
    if (!aid || !row) {
      showToast("请选择一项作业。", 2200);
      return;
    }
    if (!row.can_run_now) {
      showToast(row.blocked_reason_zh || "当前不可执行。", 3400);
      return;
    }
    if (successes < 3) {
      showToast("请先完成 3 次校准。", 2200);
      return;
    }
    try {
      const j = await fetchJSON(gameApiUrl("/api/sim/activity/run"), {
        method: "POST",
        body: JSON.stringify({ activity_id: aid }),
      });
      closeFacilitySimLayerIfOpen();
      showToast(
        j.activity_success ? "作业顺利完成，资源已入账。" : "作业受挫：行前成本已付，增益未达标。",
        3600,
      );
      await refreshOpenStoryPanel();
    } catch (e) {
      showToast(e.message || String(e), 4200);
    }
  };

  facilitySimRaf = requestAnimationFrame(tick);

  bd.classList.remove("hidden");
  bd.setAttribute("aria-hidden", "false");
}

async function postDecryptDatastick(via) {
  await fetchJSON(gameApiUrl("/api/narrative/action"), {
    method: "POST",
    body: JSON.stringify({ kind: "decrypt_datastick", via }),
  });
  showToast("加密数据棒解密流程已完成，可推进至下一段剧情。", 3400);
  await refreshOpenStoryPanel();
}

async function postDebugJumpNode(nodeId, resetCompleted = true) {
  const data = await fetchJSON(gameApiUrl("/api/debug/jump_node"), {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId, reset_completed: resetCompleted }),
  });
  showToast(`已跳转节点 → ${data.jumped_to || nodeId}`, 3400);
  latestState = data;
  await refreshOpenStoryPanel();
}

/** 地址栏加 ?debug=1 时显示；服务端需 GAME_DEBUG_API=1 */
function initDebugJumpBar() {
  const params = new URLSearchParams(location.search);
  if (params.get("debug") !== "1") return;

  const bar = document.createElement("aside");
  bar.className = "debug-jump-bar";
  bar.setAttribute("aria-label", "调试：剧情节点跳转");

  const title = document.createElement("div");
  title.className = "debug-jump-bar__title";
  title.textContent = "调试跳转";
  bar.appendChild(title);

  const note = document.createElement("p");
  note.className = "debug-jump-bar__hint";
  note.textContent =
    "需在游戏 API 进程设置环境变量 GAME_DEBUG_API=1。默认勾选「清空已完成列表」以便重复验证门闩（如 02-01 数据棒解密）。";
  bar.appendChild(note);

  const row = document.createElement("div");
  row.className = "debug-jump-bar__row";
  const inp = document.createElement("input");
  inp.type = "text";
  inp.placeholder = "节点 ID，如 02-01";
  inp.value = "02-01";
  inp.className = "debug-jump-bar__input";
  const go = document.createElement("button");
  go.type = "button";
  go.textContent = "跳转";
  const chk = document.createElement("label");
  chk.className = "debug-jump-bar__chk";
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = true;
  chk.appendChild(cb);
  chk.appendChild(document.createTextNode(" 清空已完成列表"));

  go.addEventListener("click", async () => {
    const nid = inp.value.trim();
    if (!nid) return;
    try {
      await postDebugJumpNode(nid, cb.checked);
    } catch (e) {
      showToast(String(e.message || e), 5200);
    }
  });
  row.appendChild(inp);
  row.appendChild(go);
  bar.appendChild(row);
  bar.appendChild(chk);

  const presets = document.createElement("div");
  presets.className = "debug-jump-bar__presets";
  for (const [lab, id] of [
    ["02-01", "02-01"],
    ["02-02", "02-02"],
    ["PRO-01", "PRO-01"],
  ]) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = lab;
    b.addEventListener("click", async () => {
      inp.value = id;
      try {
        await postDebugJumpNode(id, cb.checked);
      } catch (e) {
        showToast(String(e.message || e), 5200);
      }
    });
    presets.appendChild(b);
  }
  bar.appendChild(presets);
  document.body.appendChild(bar);

  fetchJSON(gameApiUrl("/api/routes"))
    .then((r) => {
      if (!r.debug_api_enabled) {
        note.textContent +=
          " （当前服务端未启用 GAME_DEBUG_API，跳转将返回 403。）";
      }
    })
    .catch(() => {});
}

function showToast(msg, ms = 2800) {
  toast = msg;
  toastUntil = performance.now() + ms;
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
  storySpriteBlock.style.background = "#3d4f66";
  storySpriteLabel.textContent = "";
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
  showToast(`已选择 · 当前节点 ${data.narrative.node_id}`);
  closeStoryUI();
  await refreshTopBar();
}

async function postAdvance() {
  const data = await fetchJSON(gameApiUrl("/api/advance"), { method: "POST", body: "{}" });
  showToast(`已推进 · 当前节点 ${data.narrative.node_id}`);
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
    "记忆碎片（占位）：展示 NPC 信任、由系统汇总的印象语，以及最近写入的长期记忆摘录；随对话与经营累积。";
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
      renderObjectivesPanel(st);
      renderMgmtResourcesHud(st.session);
      renderMgmtLogStrip(st.management_recent);
      renderSandboxDock(st);
      npcScheduleSnapshot = scheduledNpcWorldPositions(st);
      syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
      showToast(`时间推进 ${mins} 分钟`, 3200);
    } catch (e) {
      showToast(String(e.message || e), 5200);
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
        showToast(String(e.message || e), 6200);
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
  el.innerHTML = `
    <span class="resource-strip__title">基地资源</span>
    <div class="resource-strip__chips" role="list">
      <div class="resource-strip__chip" role="listitem"><span class="resource-strip__k">能源</span><span class="resource-strip__v">${r.energy}</span></div>
      <div class="resource-strip__chip" role="listitem"><span class="resource-strip__k">补给</span><span class="resource-strip__v">${r.food}</span></div>
      <div class="resource-strip__chip" role="listitem"><span class="resource-strip__k">医疗</span><span class="resource-strip__v">${r.medical}</span></div>
      <div class="resource-strip__chip" role="listitem"><span class="resource-strip__k">情报</span><span class="resource-strip__v">${r.intel}</span></div>
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

  const dockTopTools = document.querySelector(".objectives-panel__top-tools");
  if (dockTopTools) dockTopTools.classList.toggle("hidden", !sandboxOpsUnlocked);

  sandboxDock.classList.remove("hidden");
  sandboxDock.classList.remove("sandbox-dock--operating", "sandbox-dock--beat");
  sandboxDock.classList.toggle("sandbox-dock--operating", phase === "Sandbox");
  sandboxDock.classList.toggle("sandbox-dock--beat", phase !== "Sandbox");
  sandboxDock.replaceChildren();

  const row = document.createElement("div");
  row.className = "sandbox-dock__title-row";
  row.title = "静默期内每推进一日，AI 交流配额会重置。";
  const badge = document.createElement("span");
  badge.className = `sandbox-dock__badge ${phase === "Sandbox" ? "sandbox-dock__badge--sandbox" : "sandbox-dock__badge--beat"}`;
  badge.textContent = phase === "Sandbox" ? "静默运营" : "剧情节拍";
  row.appendChild(badge);

  const meta = document.createElement("span");
  meta.className = "sandbox-dock__meta";
  const wd = Number(sess.world_day ?? sb.world_day ?? 1);
  const api = sb.sandbox_npc_quota || {};
  const clockDisp = state?.world_clock?.display_zh || "";
  meta.textContent = clockDisp
    ? `第 ${wd} 日 · ${clockDisp} · AI ${api.used_today ?? 0}/${api.cap ?? 5}`
    : `第 ${wd} 日 · AI ${api.used_today ?? 0}/${api.cap ?? 5}`;
  row.appendChild(meta);
  sandboxDock.appendChild(row);

  const tagline = document.createElement("div");
  tagline.className = "sandbox-dock__tagline";
  if (phase === "Sandbox") {
    tagline.textContent = "基地日、地图资源行动、远征共用同一时钟。";
    tagline.title =
      "科技立项摘要在下方摘要；具体决算选项需走近设施面板。基地日 +1 会先结算归国远征，再写入简报。";
  } else if (sandboxOpsUnlocked) {
    tagline.textContent = "可在此进入静默，用基地日驱动资源与远征结算。";
    tagline.title =
      "进入静默后左侧为「时钟 + 决算 + 远征」经营循环；需要时也可结束静默回到剧情节拍。";
  } else {
    tagline.textContent = "静默运营将随主线推进首次解锁。";
    tagline.title = "剧情在特定节点会自动切入静默；解锁后本节可再次手动进入。";
  }
  sandboxDock.appendChild(tagline);

  if (phase === "Sandbox") {
    const detail = document.createElement("div");
    detail.className = "sandbox-dock__meta sandbox-dock__detail-line";
    const rem = sb.sandbox_min_remaining_days;
    const pend = (sb.management_pending_queue_tags || []).length;
    const gen = sb.sandbox_generation ?? sess.sandbox_generation;
    const exN = (sb.expeditions_active || []).length;
    const remBit = rem != null ? `${rem}d` : "—";
    detail.textContent = `#${gen} · 最短 ${remBit} · 决算 ${pend} · 远征 ${exN}`;
    detail.title =
      rem != null ? `第 ${gen} 轮静默 · 距可结束静默至少还需 ${rem} 个基地日 · 决算待命 ${pend} · 在外的远征 ${exN} 队` : `第 ${gen} 轮静默 · 未设置最短日数 · 决算待命 ${pend} · 在外的远征 ${exN} 队`;
    sandboxDock.appendChild(detail);
  }

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
      showToast(String(e.message || e), 5200);
      return undefined;
    }
  }

  if (phase !== "Sandbox") {
    if (!sandboxOpsUnlocked) {
      const lock = document.createElement("div");
      lock.className = "sandbox-dock__meta sandbox-dock__locked-hint";
      lock.textContent = "静默尚未解锁，请推进主线。";
      lock.title =
        "首次由剧情节点自动切入静默后即永久解锁本节；之后可在侧边栏查看教程并多次手动进入静默。";
      actions.appendChild(lock);
    } else {
      const labMin = document.createElement("label");
      labMin.className = "sandbox-dock__meta";
      labMin.textContent = "最短静默基数日";
      const inp = document.createElement("input");
      inp.type = "number";
      inp.min = "0";
      inp.step = "1";
      inp.className = "sandbox-dock__input-min";
      inp.value = "1";
      labMin.appendChild(inp);
      actions.appendChild(labMin);

      const bEnter = document.createElement("button");
      bEnter.type = "button";
      bEnter.className = "sandbox-dock__btn sandbox-dock__btn--primary sandbox-dock__btn--fat";
      bEnter.textContent = "进入静默（经营循环）";
      bEnter.addEventListener("click", () =>
        syncAfterSim(async () => {
          const raw = parseInt(inp.value, 10);
          const payload = {};
          if (Number.isFinite(raw)) payload.min_world_days = Math.max(0, raw);
          await fetchJSON(gameApiUrl("/api/sim/enter_sandbox"), {
            method: "POST",
            body: JSON.stringify(payload),
          });
          showToast("已进入静默——「基地日」现为节奏核心；可查远征与简报。", 5200);
        }),
      );
      actions.appendChild(bEnter);
    }
  } else {
    const bDay = document.createElement("button");
    bDay.type = "button";
    bDay.className = "sandbox-dock__btn sandbox-dock__btn--primary sandbox-dock__btn--fat";
    bDay.textContent = "基地日推进 +1";
    bDay.title =
      "本按钮为静默主轴：先结算归国远征，再结转物资/岸线/矿区并写入简报，同时重置 NPC 交流配额。";
    bDay.addEventListener("click", async () => {
      const out = await syncAfterSim(async () =>
        fetchJSON(gameApiUrl("/api/sim/advance_world_day"), { method: "POST", body: "{}" }),
      );
      if (!out?.fnRet) return;
      const tick = out.fnRet;
      const parts = [];
      if (tick.world_day_after != null) parts.push(`第 ${tick.world_day_after} 日已结转`);
      if (Array.isArray(tick.expeditions_settled) && tick.expeditions_settled.length)
        parts.push(`远征归国 ${tick.expeditions_settled.length} 队`);
      const eco = tick.economy_tick || {};
      if (eco.bulletin_line_zh) parts.push(String(eco.bulletin_line_zh).slice(0, 120));
      showToast(parts.length ? parts.join(" · ") : "已过一日。", 6800);
    });
    actions.appendChild(bDay);

    const bExit = document.createElement("button");
    bExit.type = "button";
    bExit.className = "sandbox-dock__btn";
    bExit.textContent = "结束静默";
    bExit.addEventListener("click", () =>
      syncAfterSim(async () => {
        await fetchJSON(gameApiUrl("/api/sim/exit_sandbox"), {
          method: "POST",
          body: JSON.stringify({ force: false }),
        });
        showToast("已恢复剧情节拍；待办决算已尝试落地。", 4200);
      }),
    );
    actions.appendChild(bExit);

    const bForce = document.createElement("button");
    bForce.type = "button";
    bForce.className = "sandbox-dock__btn sandbox-dock__btn--danger";
    bForce.textContent = "强制结束";
    bForce.title = "忽略最短静默日数，但仍需决算队列可落地";
    bForce.addEventListener("click", () =>
      syncAfterSim(async () => {
        await fetchJSON(gameApiUrl("/api/sim/exit_sandbox"), {
          method: "POST",
          body: JSON.stringify({ force: true }),
        });
        showToast("已强制结束静默。", 3600);
      }),
    );
    actions.appendChild(bForce);
  }
  sandboxDock.appendChild(actions);

  if (phase === "Sandbox") {
    const cr = document.createElement("div");
    cr.className = "sandbox-dock__clock-actions";
    const lab = document.createElement("span");
    lab.className = "sandbox-dock__meta";
    lab.textContent = `调时：${state?.world_clock?.display_zh || "—"}（洞穴 21:00–5:00）`;
    cr.appendChild(lab);
    async function bumpSim(mins) {
      await syncAfterSim(async () => postAdvanceClockMinutes(mins));
    }
    const mk = (t, m) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "sandbox-dock__btn";
      b.textContent = t;
      b.addEventListener("click", () => bumpSim(m));
      cr.appendChild(b);
    };
    mk("+30分", 30);
    mk("+2时", 120);
    mk("+6时", 360);
    sandboxDock.appendChild(cr);
  }

  if (phase === "Sandbox") {
    const expBox = document.createElement("div");
    expBox.className = "sandbox-dock__exp";
    const expHead = document.createElement("div");
    expHead.className = "sandbox-dock__exp-head";
    const expTitle = document.createElement("div");
    expTitle.className = "sandbox-dock__exp-title";
    expTitle.textContent = "野外远征";
    const expSub = document.createElement("div");
    expSub.className = "sandbox-dock__exp-sub";
    expSub.textContent = "静默专有 · 出发前扣资源 · 归国跟基地日结算";
    expSub.title = "仅静默期可用；出发前扣除能源与补给；归国日随「基地日 +1」一并入账。";
    expHead.appendChild(expTitle);
    expHead.appendChild(expSub);
    expBox.appendChild(expHead);

    const active = sb.expeditions_active || [];
    const busyLeaders = new Set(active.map((e) => e.leader_npc_id).filter(Boolean));
    if (active.length) {
      const wrap = document.createElement("div");
      wrap.className = "sandbox-dock__exp-cards";
      for (const ex of active) {
        const card = document.createElement("div");
        card.className = "sandbox-dock__exp-card";
        const head = document.createElement("div");
        head.className = "sandbox-dock__exp-card-head";
        const leaderLab = ex.leader_label_zh || ex.leader_npc_id || "?";
        const destLab = ex.destination_label_zh || ex.destination_id || "";
        head.textContent = `${leaderLab} · ${destLab}`;
        const sub = document.createElement("div");
        sub.className = "sandbox-dock__exp-card-sub";
        const pct = Math.min(100, Math.round(Number(ex.progress ?? 0) * 100));
        const du = ex.days_until_return ?? 0;
        sub.textContent =
          du > 0
            ? `航程进度约 ${pct}% · 尚需 ${du} 个基地日 · 定于第 ${ex.return_world_day ?? "?"} 日归国`
            : `已定在第 ${ex.return_world_day ?? "?"} 日归国 · 请点击「基地日 +1」以触发结算`;
        const bar = document.createElement("div");
        bar.className = "sandbox-dock__exp-bar";
        const fill = document.createElement("span");
        fill.className = "sandbox-dock__exp-bar-fill";
        fill.style.width = `${pct}%`;
        bar.appendChild(fill);
        card.appendChild(head);
        card.appendChild(sub);
        card.appendChild(bar);
        wrap.appendChild(card);
      }
      expBox.appendChild(wrap);
    }

    const rowE = document.createElement("div");
    rowE.className = "sandbox-dock__exp-row";
    const selL = document.createElement("select");
    selL.className = "sandbox-dock__select";
    selL.title = "每位干员同时仅可带领一支在外的远征";
    for (const [id, zh] of [
      ["chubby", "小胖"],
      ["karen", "卡伦"],
      ["jin", "堇"],
    ]) {
      const o = document.createElement("option");
      o.value = id;
      const outBusy = busyLeaders.has(id);
      o.disabled = outBusy;
      o.textContent = outBusy ? `${zh}（远征中）` : zh;
      selL.appendChild(o);
    }

    const selD = document.createElement("select");
    selD.className = "sandbox-dock__select";
    const cat = sb.expedition_catalog || [];
    let firstUnlocked = "";
    for (const d of cat) {
      const o = document.createElement("option");
      o.value = d.dest_id || "";
      const c = d.cost || {};
      const ce = Number(c.energy ?? 0);
      const cf = Number(c.food ?? 0);
      const lockTag = d.unlocked ? "" : "（门禁未开）";
      o.textContent = `${d.duration_days ?? "?"}日 · 能耗${ce}粮${cf} · ${d.label_zh || d.dest_id}${lockTag}`;
      o.title = [d.reward_hint_zh || "", d.blocked_reason_zh || ""].filter(Boolean).join("\n") || "";
      o.disabled = !d.unlocked;
      selD.appendChild(o);
      if (d.unlocked && !firstUnlocked) firstUnlocked = d.dest_id;
    }
    if (firstUnlocked) selD.value = firstUnlocked;

    const hintDest = document.createElement("div");
    hintDest.className = "sandbox-dock__exp-hint";

    for (const o of [...selL.options]) {
      if (!o.disabled) {
        selL.value = o.value;
        break;
      }
    }

    const bExp = document.createElement("button");
    bExp.type = "button";
    bExp.className = "sandbox-dock__btn sandbox-dock__btn--emph";
    bExp.textContent = "签发远征";

    const expWarn = document.createElement("div");
    expWarn.className = "sandbox-dock__exp-warn";

    function expeditionPreflightMsg() {
      if (!cat.length) {
        return { ok: false, zh: "未收到远征目录：请刷新页面；若仍存在，重启本仓库的 python -m game。" };
      }
      if (!firstUnlocked) {
        return {
          ok: false,
          zh: "暂无门禁已满足的远征目的地；请先在「探索」与剧情中解锁岸线洞穴、矿脉深区、回声信标塔或议会前哨等区域。",
        };
      }
      if ([...selL.options].every((o) => o.disabled)) {
        return {
          ok: false,
          zh: "三名队长均已在外执行任务，请先推进基地日直至至少一队归国后再派新远征。",
        };
      }
      const lid = selL.value || "";
      if (busyLeaders.has(lid)) {
        const name =
          ({ chubby: "小胖", karen: "卡伦", jin: "堇" })[lid] ||
          selL.selectedOptions[0]?.textContent?.replace(/（远征中）$/, "").trim() ||
          lid;
        return { ok: false, zh: `${name}正在远征途中，请换队长或等国后再派出第二支小队。` };
      }
      const destId = selD.value || "";
      const row = cat.find((x) => String(x.dest_id) === String(destId));
      const opt = selD.selectedOptions[0];
      if (!row || opt?.disabled) {
        return { ok: false, zh: "当前选中的目的地尚未门禁开放；请下拉选择门禁已满足的远征目标。" };
      }
      const ce = Number(row.cost?.energy ?? 0);
      const cf = Number(row.cost?.food ?? 0);
      const resSnap = sess.resources || {};
      const e = Number(resSnap.energy ?? 0);
      const f = Number(resSnap.food ?? 0);
      if (e < ce || f < cf) {
        return {
          ok: false,
          zh: `物资不足以签发本条远征：需 能耗≥${ce}、补给≥${cf}（当前 能源 ${e}、补给 ${f}）；可多几次「基地日 +1」或在「决算」侧补资源后再试。`,
        };
      }
      return { ok: true, zh: "" };
    }

    function refreshExpIssue() {
      const pf = expeditionPreflightMsg();
      expWarn.textContent = pf.zh || "";
      expWarn.hidden = pf.ok || !pf.zh;
      bExp.disabled = !pf.ok;
    }

    function refreshDestHint() {
      const pick = cat.find((x) => String(x.dest_id) === String(selD.value));
      if (!pick) {
        hintDest.textContent = "";
      } else {
        hintDest.textContent = [pick.reward_hint_zh || "", pick.blocked_reason_zh || ""].filter(Boolean).join(" ").trim();
      }
      refreshExpIssue();
    }

    selD.addEventListener("change", refreshDestHint);
    selL.addEventListener("change", refreshExpIssue);

    bExp.addEventListener("click", async () => {
      const pf = expeditionPreflightMsg();
      if (!pf.ok && pf.zh) {
        showToast(pf.zh, 6500);
        return;
      }
      const out = await syncAfterSim(async () =>
        fetchJSON(gameApiUrl("/api/expedition/start"), {
          method: "POST",
          body: JSON.stringify({ leader_npc_id: selL.value, destination_id: selD.value }),
        }),
      );
      if (!out?.fnRet?.ok) return;
      const ex = out.fnRet.expedition || {};
      const rw = ex.return_world_day;
      showToast(
        Number.isFinite(Number(rw))
          ? `远征队已编成：出发前物资已记账，预计第 ${rw} 个基地日归国（请用「基地日 +1」推进）。`
          : "远征队已出发。归国结算与基地日绑定。",
        4200,
      );
    });

    refreshDestHint();

    rowE.appendChild(selL);
    rowE.appendChild(selD);
    rowE.appendChild(bExp);
    expBox.appendChild(rowE);
    expBox.appendChild(expWarn);
    expBox.appendChild(hintDest);
    sandboxDock.appendChild(expBox);

    const techHints = sb.facility_tech_hints || [];
    if (techHints.length) {
      const techBox = document.createElement("div");
      techBox.className = "sandbox-dock__tech-hint";
      const thTitle = document.createElement("div");
      thTitle.className = "sandbox-dock__tech-hint-title";
      thTitle.textContent = "设施科技 · 静默摘要";
      techBox.appendChild(thTitle);
      const ul = document.createElement("div");
      ul.className = "sandbox-dock__tech-hint-list";
      for (const row of techHints) {
        const line = document.createElement("div");
        line.className = "sandbox-dock__tech-hint-row";
        const pend = Number(row.pending_research_count ?? 0);
        const tot = Number(row.nodes_total ?? 0);
        const rs = Number(row.nodes_researched ?? 0);
        line.textContent = `${row.facility_label_zh || row.facility_id} · 已定案节点 ${rs}/${tot} · 当前可先立项 ${pend}`;
        ul.appendChild(line);
      }
      techBox.appendChild(ul);
      const foot = document.createElement("div");
      foot.className = "sandbox-dock__tech-hint-foot";
      foot.textContent = "立项走近设施决算卡；排队项结束静默后落地。";
      foot.title =
        "正式立项仍以走近对应设施时出现之「决算卡片」为准；静默内标记为「排队」的决议会在结束后落地。";
      techBox.appendChild(foot);
      sandboxDock.appendChild(techBox);
    }

    const actCat = sb.resource_activity_catalog || [];
    if (actCat.length) {
      const actBox = document.createElement("div");
      actBox.className = "sandbox-dock__res-act";
      const ah = document.createElement("div");
      ah.className = "sandbox-dock__res-act-head";
      const at = document.createElement("span");
      at.className = "sandbox-dock__res-act-title";
      at.textContent = "地图资源行动";
      const asub = document.createElement("span");
      asub.className = "sandbox-dock__res-act-sub";
      asub.textContent = "静默内补充四项资源，与远征、基地日同一时钟。";
      asub.title = "与区域门禁、远征、基地日结转共用同一时间轴；受冷却与资源约束。";
      ah.appendChild(at);
      ah.appendChild(asub);
      actBox.appendChild(ah);

      const selAct = document.createElement("select");
      selAct.className = "sandbox-dock__select";
      let firstRunnable = "";
      for (const a of actCat) {
        const o = document.createElement("option");
        o.value = a.activity_id || "";
        const rp = a.reward_preview || {};
        const gainBits = [];
        if (rp.energy) gainBits.push(`能+${rp.energy}`);
        if (rp.food) gainBits.push(`粮+${rp.food}`);
        if (rp.medical) gainBits.push(`医+${rp.medical}`);
        if (rp.intel) gainBits.push(`情+${rp.intel}`);
        const gainStr = gainBits.join(" ") || "见简报";
        const cp = a.cost_preview || {};
        let tag = "";
        if (!a.zone_unlocked) tag = " · 区域未放行";
        else if (Number(a.cooldown_remain_days || 0) > 0) tag = ` · 冷却≈${a.cooldown_remain_days}日`;
        else if (!a.can_run_now) tag = " · 条件不足";

        o.textContent = `${a.run_kind_zh || a.activity_id}（${a.primary_resource} · ${gainStr}）${tag}`;
        o.title =
          `片区 ${a.region_id}\n` +
          `${!a.zone_unlocked ? `门禁：${a.blocked_gate_zh || ""}\n` : ""}` +
          `岸线备注：${a.incursion_notes || "—"}\n` +
          `行前能耗 ${cp.energy ?? 0} · 行前粮 ${cp.food ?? 0}\n失败率约 ${Math.round(Number(a.risk_failure ?? 0) * 100)}%`;
        selAct.appendChild(o);
        if (a.can_run_now && !firstRunnable) firstRunnable = a.activity_id;
      }
      if (firstRunnable) selAct.value = firstRunnable;

      const hintAct = document.createElement("div");
      hintAct.className = "sandbox-dock__res-act-hint";

      function pickedActivity() {
        return actCat.find((x) => String(x.activity_id) === String(selAct.value));
      }

      function actPreflightMsg() {
        const p = pickedActivity();
        if (!p) return { ok: false, zh: "请先选择一项地图行动。" };
        if (!p.can_run_now)
          return { ok: false, zh: p.blocked_reason_zh || p.blocked_gate_zh || "当前无法执行该行功。" };
        return { ok: true, zh: "" };
      }

      function refreshActHint() {
        const pf = actPreflightMsg();
        const p = pickedActivity();
        bRunAct.disabled = !pf.ok;
        if (pf.ok && p) {
          hintAct.textContent = p.incursion_notes ? `岸线提示：${p.incursion_notes}` : "";
        } else if (pf.zh) {
          hintAct.textContent = pf.zh;
        } else {
          hintAct.textContent = "";
        }
      }

      const rowAct = document.createElement("div");
      rowAct.className = "sandbox-dock__res-act-row";
      const bRunAct = document.createElement("button");
      bRunAct.type = "button";
      bRunAct.className = "sandbox-dock__btn sandbox-dock__btn--primary";
      bRunAct.textContent = "执行行动";
      bRunAct.title = "结算一次该区域操作；成功可得资源，亦有失败机率";
      selAct.addEventListener("change", refreshActHint);
      refreshActHint();

      bRunAct.addEventListener("click", async () => {
        const pf = actPreflightMsg();
        if (!pf.ok) {
          showToast(pf.zh, 6200);
          return;
        }
        const aid = selAct.value;
        if (!aid) return;
        try {
          const out = await syncAfterSim(async () =>
            fetchJSON(gameApiUrl("/api/sim/activity/run"), {
              method: "POST",
              body: JSON.stringify({ activity_id: aid }),
            }),
          );
          const j = out?.fnRet;
          if (!j?.ok) return;
          showToast(
            j.activity_success
              ? "行动顺利：资源已记入仓库与简报。"
              : "行动受挫：行前成本已消耗，详见简报。",
            4800,
          );
        } catch (_) {
          /* toast from fetchJSON */
        }
      });

      rowAct.appendChild(selAct);
      rowAct.appendChild(bRunAct);
      actBox.appendChild(rowAct);
      actBox.appendChild(hintAct);
      sandboxDock.appendChild(actBox);
    }
  } else {
    const hint = document.createElement("div");
    hint.className = "sandbox-dock__meta sandbox-dock__beat-hint";
    hint.style.marginTop = "4px";
    hint.innerHTML =
      "进入静默后，侧栏可<strong>签发远征</strong>并进行<strong>地图资源行动</strong>；设施决算仍须走近建筑并在剧情框内确认。";
    sandboxDock.appendChild(hint);
  }

  const bulls = [...(sb.bulletin_tail_zh || []).slice(-4)];
  if (bulls.length) {
    const box = document.createElement("div");
    box.className = `sandbox-dock__bull ${phase === "Sandbox" ? "sandbox-dock__bull--wide" : ""}`;
    for (const line of bulls) {
      const p = document.createElement("div");
      p.className = "sandbox-dock__bull-row";
      p.textContent = line;
      box.appendChild(p);
    }
    sandboxDock.appendChild(box);
  }
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
      showToast(String(e.message || e), 6200);
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

async function refreshTopBar() {
  try {
    const data = await fetchJSON(gameApiUrl("/api/state"));
    latestState = data;
    syncExplorerApiBanner(true);
    renderObjectivesPanel(data);
    renderMgmtResourcesHud(data.session);
    renderMgmtLogStrip(data.management_recent);
    renderSandboxDock(data);
    tryShowMemoryFlash022(data);
    maybeOfferSandboxPlaybookIntro(data);
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
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = e.label_zh;
      b.disabled = navBlocked;
      if (navBlocked) b.title = narrative.story_navigation_blocked_zh || "";
      b.addEventListener("click", () => postChoice(e.id));
      storyChoices.appendChild(b);
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
    const decryptAfterTalk =
      nar?.node_id === "02-01" &&
      npcId === "dr_lin" &&
      storyFocus &&
      data.session &&
      !plotHasFlag(data.session, "datastick_decrypt_complete");

    revealNpcDialogueSequential(storyAiLine, data.text || "", {
      onComplete: async () => {
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
          showToast(String(e.message || e), 5200);
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
    showToast(String(e.message || e), 5200);
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

function renderNpcPanel(stateData, checkData, npc, opts = {}) {
  const skipOpening = !!opts.skipOpening;
  storyExtras.innerHTML = "";
  storyMeta.innerHTML = "";
  storyBody.classList.add("story-body--npc-dialogue");
  const focus = checkData.is_story_focus;
  const row = (stateData.overworld_npcs || []).find((r) => r.id === npc.id);
  storyTitle.textContent = row?.name || npc.name;
  storySub.textContent = "";
  storyBullets.innerHTML = "";
  setPortraitPlaceholder(npc.id, `${row?.name || npc.name}\n（立绘占位）`);
  const nar = checkData.narrative;
  storyChoices.innerHTML = "";
  const hasBranch =
    (nar.fin_endings && nar.fin_endings.length > 0) ||
    (nar.choices && nar.choices.length > 0) ||
    !!nar.can_advance_default;
  if (hasBranch) addChoiceButtons(nar);
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
  if (storyChoices.children.length > 0 && !skipOpening) setStoryChoicesLocked(true);
  if (!skipOpening) queueMicrotask(() => postNpcOpening(npc.id, focus));
}

function renderFacilityPanel(stateData, checkData, fac) {
  storyExtras.innerHTML = "";
  storyMeta.innerHTML = "";
  storyBody.classList.remove("story-body--npc-dialogue");
  storyTitle.textContent = fac.name;
  setPortraitPlaceholder(fac.id, `${fac.name}\n（设施占位）`);
  const nar = stateData.narrative;
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
  if (nar.node_id === "01-02" && rel) {
    if (uq) {
      const pick = (nar.choices || []).find((c) => c.id === uq);
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = pick ? `在此确认：${pick.label_zh}` : "确认升级选择";
      b.addEventListener("click", () => postChoice(uq));
      storyChoices.appendChild(b);
    }
    if (fac.id === "command") {
      storySub.textContent = "会议室：三项升级优先（与节点 01-02 一致）。";
      addChoiceButtons(nar);
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
  if (rel && nar.can_advance_default && !(nar.node_id === "01-02" && uq)) {
    const adv = document.createElement("button");
    adv.type = "button";
    adv.className = "secondary";
    adv.textContent = "推进剧情（本节点无分支）";
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

  /** 须与后端 `game/facility_sim_ops.FACILITY_ACTIVITY_REGIONS` 键一致（带工作台静默玩法的地图设施） */
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
            showToast(e.message || String(e), 4200);
          }
        });
        row.appendChild(bClaim);
        if ((simOv.activities || []).length) {
          const bGo = document.createElement("button");
          bGo.type = "button";
          bGo.className = "facility-sim-btn facility-sim-btn--primary";
          bGo.textContent = "手动作业（开小窗校准）";
          bGo.addEventListener("click", () => openFacilitySimWorkbench(fac, simOv));
          row.appendChild(bGo);
        } else {
          const bx = document.createElement("span");
          bx.className = "facility-sim-no-act";
          bx.textContent =
            "当前清单中无该项设施对应的可执行作业（多为区域门禁或未满足冷却/物资）；仍可走侧栏资源行动入口。";
          row.appendChild(bx);
        }
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
    showToast(`剧情服务：${e.message || e}`, 4200);
  }
}

storyClose.addEventListener("click", closeStoryUI);
storyBackdrop.addEventListener("click", (ev) => {
  if (ev.target === storyBackdrop) closeStoryUI();
});
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    const pb = sandboxPlaybookBackdropEl();
    if (pb && !pb.classList.contains("hidden")) {
      closeSandboxPlaybook();
      return;
    }
    if (closeFacilitySimLayerIfOpen()) return;
    if (!storyBackdrop.classList.contains("hidden")) closeStoryUI();
  }
});

document.getElementById("sandbox-playbook-open")?.addEventListener("click", () => {
  rememberSandboxPlaybookAutoSessionIfEligible(latestState);
  openSandboxPlaybook();
});

setInterval(refreshTopBar, 3200);
refreshTopBar();
initDebugJumpBar();

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
const ctx = canvas.getContext("2d");
const mini = document.getElementById("minimap");
const mctx = mini.getContext("2d");
const wsizeEl = document.getElementById("wsize");
wsizeEl && (wsizeEl.textContent = `${WORLD.w}×${WORLD.h}`);

function resize() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.floor(canvas.clientWidth * dpr);
  canvas.height = Math.floor(canvas.clientHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
window.addEventListener("resize", resize);
resize();

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

canvas.addEventListener("mousemove", (ev) => {
  const br = canvas.getBoundingClientRect();
  mouseCanvasX = ev.clientX - br.left;
  mouseCanvasY = ev.clientY - br.top;
});

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
        wanderOX: 0,
        wanderOY: 0,
        wanderTX: 0,
        wanderTY: 0,
        wanderTimer: 0,
        headingWobble: 0,
      };
      continue;
    }
    if (npcBodies[id].goalKey !== key) {
      npcBodies[id].targetX = p.x;
      npcBodies[id].targetY = p.y;
      npcBodies[id].goalKey = key;
      npcBodies[id].wanderOX = 0;
      npcBodies[id].wanderOY = 0;
      npcBodies[id].wanderTX = 0;
      npcBodies[id].wanderTY = 0;
      npcBodies[id].wanderTimer = 0;
      npcBodies[id].headingWobble = 0;
    }
  }
}

/** 围绕日程锚点的随机游荡半径（像素） */
const NPC_WANDER_RADIUS_LO = 28;
const NPC_WANDER_RADIUS_HI = 72;
/** NPC 行走速度相对玩家的比例（略慢更像逛基地） */
const NPC_WALK_SPEED_SCALE = 0.5;
/** 游荡偏移平滑（越大越快贴上新随机点） */
const NPC_WANDER_SMOOTH = 2.8;
/** 朝向微摆：弧度级随机游走，避免笔直斜线 */
const NPC_HEADING_WOBBLE_GAIN = 1.25;
const NPC_HEADING_WOBBLE_DECAY = 0.988;
const NPC_HEADING_WOBBLE_MAX = 0.55;

function _npcWanderTick(id, b, dt) {
  b.wanderTimer -= dt;
  if (b.wanderTimer <= 0) {
    const tick = Math.floor(performance.now() * 0.001) ^ hashHour(id, (b.goalKey || "").length + 13);
    const r = NPC_WANDER_RADIUS_LO + (hashHour(id, tick) % (NPC_WANDER_RADIUS_HI - NPC_WANDER_RADIUS_LO));
    const ang = ((hashHour(id, tick + 1) % 360) * Math.PI) / 180;
    b.wanderTX = Math.cos(ang) * r;
    b.wanderTY = Math.sin(ang) * r;
    b.wanderTimer = 1.4 + (hashHour(id, tick + 2) % 120) / 100;
  }
  const k = Math.min(1, NPC_WANDER_SMOOTH * dt);
  b.wanderOX += (b.wanderTX - b.wanderOX) * k;
  b.wanderOY += (b.wanderTY - b.wanderOY) * k;
}

function stepAllNpcBodies(dt) {
  const r = PLAYER.r;
  const spBase = PLAYER.speed * dt * NPC_WALK_SPEED_SCALE;
  for (const id of Object.keys(npcBodies)) {
    if (!isNpcVisibleOnMap(id)) continue;
    const b = npcBodies[id];
    if (typeof b.wanderTimer !== "number" || Number.isNaN(b.wanderTimer)) {
      b.wanderOX = 0;
      b.wanderOY = 0;
      b.wanderTX = 0;
      b.wanderTY = 0;
      b.wanderTimer = 0;
      b.headingWobble = typeof b.headingWobble === "number" ? b.headingWobble : 0;
    }
    _npcWanderTick(id, b, dt);
    if (movementObstacleAt(b.x, b.y, r)) {
      b.x = b.targetX;
      b.y = b.targetY;
    }
    const aimX = b.targetX + b.wanderOX;
    const aimY = b.targetY + b.wanderOY;
    let dx = aimX - b.x;
    let dy = aimY - b.y;
    const len = Math.hypot(dx, dy);
    if (len < 18) {
      b.x = aimX;
      b.y = aimY;
      continue;
    }
    b.headingWobble += (Math.random() - 0.5) * NPC_HEADING_WOBBLE_GAIN * dt;
    b.headingWobble *= NPC_HEADING_WOBBLE_DECAY;
    if (b.headingWobble > NPC_HEADING_WOBBLE_MAX) b.headingWobble = NPC_HEADING_WOBBLE_MAX;
    if (b.headingWobble < -NPC_HEADING_WOBBLE_MAX) b.headingWobble = -NPC_HEADING_WOBBLE_MAX;
    const ux = dx / len;
    const uy = dy / len;
    const c = Math.cos(b.headingWobble);
    const s = Math.sin(b.headingWobble);
    const wx = ux * c - uy * s;
    const wy = ux * s + uy * c;
    const jitter = 0.92 + (hashHour(id, Math.floor(performance.now() * 0.3) % 500) % 17) / 100;
    const sp = spBase * jitter;
    const stepX = wx * sp;
    const stepY = wy * sp;
    const res = tryMoveEntity(b.x, b.y, b.x + stepX, b.y + stepY, r);
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

/** 点距轴对齐矩形（点在矩形内为 0）— 设施交互：以外沿距离判定「是否贴墙」 */
function distPointToRect(px, py, rect) {
  const nx = Math.max(rect.x, Math.min(px, rect.x + rect.w));
  const ny = Math.max(rect.y, Math.min(py, rect.y + rect.h));
  return Math.hypot(px - nx, py - ny);
}

/** NPC：与圆心距离小于此值可交互 */
const NPC_INTERACT_RADIUS = 102;
/** 设施：仅当与建筑 core 外沿距离 ≤ 此值时可交互（须贴近墙体，站远处无效） */
const FACILITY_WALL_INTERACT_MAX = 38;

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
  for (const f of FACILITIES) {
    const d = distPointToRect(PLAYER.x, PLAYER.y, f.core);
    if (d > FACILITY_WALL_INTERACT_MAX) continue;
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
  const fzEzLab = Math.max(9, Math.round(13 * labelScale));
  const fzNpcName = Math.max(11, Math.round(15 * labelScale));
  const fzNpcBlur = Math.max(9, Math.round(12 * labelScale));
  const fzNpcHint = Math.max(8, Math.round(11 * labelScale));
  ensureTileTerrainCanvas();
  ctx.drawImage(tileTerrainCanvas, 0, 0);

  const inc = incursionRatio();
  drawShoreIntrusion(ctx, inc, performance.now());

  // 设施 POI：在格网上加描边与标牌（体块已由 TILE_MAP 铺设）
  for (const f of FACILITIES) {
    const c = f.core;
    ctx.fillStyle = "rgba(18, 24, 34, 0.35)";
    ctx.strokeStyle = "rgba(160, 200, 255, 0.45)";
    ctx.lineWidth = 2;
    ctx.fillRect(c.x, c.y, c.w, c.h);
    ctx.strokeRect(c.x, c.y, c.w, c.h);

    const fitFs = Math.round(
      Math.min(
        fzFacility,
        Math.max(10, Math.min(c.h * 0.42, c.w / Math.max(1, f.name.length * 0.58)))
      )
    );
    ctx.font = `bold ${fitFs}px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.shadowColor = "rgba(0, 0, 0, 0.72)";
    ctx.shadowBlur = 5;
    ctx.fillStyle = "rgba(220, 235, 255, 0.96)";
    ctx.fillText(f.name, c.x + c.w / 2, c.y + c.h / 2);
    ctx.shadowBlur = 0;
    ctx.textBaseline = "alphabetic";
  }

  const ez = latestState?.explorer_zones;
  if (ez?.length) {
    const lockedStroke = {
      story: "rgba(255, 190, 120, 0.55)",
      info: "rgba(200, 140, 255, 0.5)",
      ability: "rgba(120, 210, 255, 0.52)",
      resource: "rgba(255, 228, 90, 0.48)",
      time: "rgba(100, 160, 255, 0.5)",
      none: "rgba(140, 200, 255, 0.35)",
    };
    const lockedFill = {
      story: "rgba(255, 160, 80, 0.07)",
      info: "rgba(180, 120, 255, 0.06)",
      ability: "rgba(80, 180, 255, 0.07)",
      resource: "rgba(255, 220, 60, 0.06)",
      time: "rgba(80, 140, 255, 0.07)",
      none: "rgba(120, 180, 255, 0.04)",
    };
    for (const ex of ez) {
      const lt = ex.lock_type || "none";
      if (!ex.blocks_movement) {
        ctx.strokeStyle = "rgba(110, 255, 170, 0.22)";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 6]);
        ctx.strokeRect(ex.x, ex.y, ex.w, ex.h);
        ctx.setLineDash([]);
        continue;
      }
      ctx.fillStyle = lockedFill[lt] || lockedFill.none;
      ctx.fillRect(ex.x, ex.y, ex.w, ex.h);
      ctx.strokeStyle = lockedStroke[lt] || lockedStroke.none;
      ctx.lineWidth = 2;
      ctx.setLineDash([10, 7]);
      ctx.strokeRect(ex.x, ex.y, ex.w, ex.h);
      ctx.setLineDash([]);
      const lab = ex.display_label_zh || ex.label_zh || "";
      if (lab) {
        ctx.font = `bold ${fzEzLab}px Segoe UI, PingFang SC, Microsoft YaHei, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillStyle = "rgba(230, 240, 255, 0.82)";
        ctx.fillText(lab, ex.x + ex.w / 2, ex.y + 18);
      }
    }
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
        : `贴近建筑外墙：${t.name} — 按 E 查看`;
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
    const c = f.core;
    mctx.fillStyle = "rgba(80, 130, 210, 0.7)";
    mctx.fillRect(c.x * sx, c.y * sy, Math.max(1, c.w * sx), Math.max(1, c.h * sy));
    mctx.strokeStyle = "rgba(150, 200, 255, 0.45)";
    mctx.lineWidth = 1;
    mctx.strokeRect(c.x * sx, c.y * sy, Math.max(1, c.w * sx), Math.max(1, c.h * sy));
  }

  const ez = latestState?.explorer_zones;
  if (ez?.length) {
    for (const z of ez) {
      mctx.strokeStyle = z.blocks_movement ? "rgba(255, 190, 120, 0.65)" : "rgba(120, 255, 180, 0.35)";
      mctx.lineWidth = 1;
      mctx.strokeRect(z.x * sx, z.y * sy, z.w * sx, z.h * sy);
    }
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
  if (!lastTs) lastTs = ts;
  const dt = Math.min(0.05, (ts - lastTs) / 1000);
  lastTs = ts;

  pollInput(dt);
  tickWorldClock(ts);
  npcScheduleSnapshot = scheduledNpcWorldPositions(latestState);
  syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
  stepAllNpcBodies(dt);

  if (keys.has("e")) {
    const t = nearestInteract();
    if (t) openStoryFromInteract(t);
    keys.delete("e");
  }

  const vw = canvas.clientWidth;
  const vh = canvas.clientHeight;
  const hzHover = pickHoveredExplorerZone();
  canvas.style.cursor = hzHover?.blocks_movement ? "help" : "crosshair";
  // 与 resize() 的 dpr 缩放一致：按 CSS 像素尺寸清除（勿用 canvas.width/height，否则会错清/漏清）
  ctx.clearRect(0, 0, vw, vh);
  drawWorld(vw, vh);
  drawHud(vw, vh);
  drawMinimap();

  requestAnimationFrame(frame);
}

npcScheduleSnapshot = scheduledNpcWorldPositions(null);
syncNpcTargetsFromSchedule(npcScheduleSnapshot.pos);
requestAnimationFrame(frame);
