/* =============================================================
   Bubble Shooter — working build (split files)
   Features:
   - Canvas loop, aiming clamp, wall bounces
   - Staggered offset grid (odd rows shifted)
   - BFS matching & popping, floating island drop with gravity
   - Win (empty grid) / Lose (touch floor)
   - Ceiling drop every N shots (counted at shoot; drop after shot resolves)
   ============================================================= */

//// Config //////////////////////////////////////////////////////
const LOGICAL_W = 480, LOGICAL_H = 720;
const R = 16;                            // bubble radius
const D = R * 2;                         // bubble diameter
const ROW_H = Math.sqrt(3)/2 * D;        // hex-ish vertical spacing
const COLS = Math.floor(LOGICAL_W / D);  // even-row column count
const COLORS = ["#ff6b6b", "#feca57", "#1dd1a1", "#54a0ff", "#c56cf0", "#ff9ff3"];
const SHOOT_SPEED = 520;                 // px/s
const MIN_ANGLE = Math.PI * 0.06, MAX_ANGLE = Math.PI - MIN_ANGLE;

//// Canvas //////////////////////////////////////////////////////
const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
function resizeCanvasForDPR() {
  const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
  canvas.width = LOGICAL_W * dpr;
  canvas.height = LOGICAL_H * dpr;
  canvas.style.width = LOGICAL_W + 'px';
  canvas.style.height = LOGICAL_H + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
resizeCanvasForDPR();
window.addEventListener('resize', resizeCanvasForDPR);

//// State ///////////////////////////////////////////////////////
const state = {
  running: true,
  mode: 'playing',   // 'playing' | 'win' | 'lose'
  score: 0,
  grid: [],
  rows: 0,
  shooter: { x: LOGICAL_W/2, y: LOGICAL_H - 40, angle: Math.PI/2, current: null, next: null },
  moving: null,      // {x,y,vx,vy,color}
  falling: [],       // [{x,y,vy,color}]
  input: { aimingX: LOGICAL_W/2, aimingY: LOGICAL_H - 200, shooting: false },
  drop: { every: 5, shotsLeft: 5, rows: 1, pending: false }
};

//// Grid helpers ///////////////////////////////////////////////
function rowCols(r){ return (r % 2 === 0) ? COLS : COLS - 1; }

function ensureRows(n){
  while(state.grid.length < n){
    const r = state.grid.length;
    state.grid.push(new Array(rowCols(r)).fill(null));
  }
  state.rows = state.grid.length;
}

function cellToWorld(c, r){
  const offset = (r % 2 === 1) ? R : 0; // odd rows shifted right by R
  const x = c * D + R + offset;
  const y = r * ROW_H + R;
  return {x, y};
}

function worldToCell(x, y){
  const r = Math.max(0, Math.round((y - R) / ROW_H));
  const offset = (r % 2 === 1) ? R : 0;
  const c = Math.round((x - R - offset) / D);
  return {c, r};
}

function neighbors(c, r){
  const odd = (r % 2 === 1);
  const deltas = odd
    ? [[-1,0],[1,0],[0,-1],[1,-1],[0,1],[1,1]]
    : [[-1,0],[1,0],[-1,-1],[0,-1],[-1,1],[0,1]];
  return deltas.map(([dc,dr]) => ({ c: c+dc, r: r+dr }));
}

function inBounds(c, r){
  if(r < 0 || r >= state.rows) return false;
  const cols = rowCols(r);
  return c >= 0 && c < cols;
}

function occupiedAt(c, r){ return inBounds(c,r) && state.grid[r][c] !== null; }

function placeAt(c, r, color){
  ensureRows(Math.max(state.rows, r+1));
  if(!inBounds(c,r) || state.grid[r][c] != null) return false;
  state.grid[r][c] = { color };
  return true;
}

//// Seed board //////////////////////////////////////////////////
function seedBoard(rows=6){
  state.grid = [];
  ensureRows(rows);
  for(let r=0;r<rows;r++){
    state.grid[r] = new Array(rowCols(r)).fill(null);
    for(let c=0;c<rowCols(r);c++){
      if(Math.random() < 0.85){
        // fewer colors early for solvability
        state.grid[r][c] = { color: COLORS[(r+c) % Math.min(4, COLORS.length)] };
      }
    }
  }
  state.rows = state.grid.length;
}

//// Colors (only spawn colors still on board) //////////////////
function activeColorPool(){
  const present = new Set();
  for(let r=0;r<state.rows;r++){
    for(let c=0;c<rowCols(r);c++){
      const cell = state.grid[r][c];
      if(cell) present.add(cell.color);
    }
  }
  const pool = [...present];
  return pool.length ? pool : COLORS;
}
function randomAvailableColor(){
  const pool = activeColorPool();
  return pool[Math.floor(Math.random()*pool.length)];
}

function prepareShooter(){
  if(!state.shooter.current) state.shooter.current = { color: randomAvailableColor() };
  if(!state.shooter.next)    state.shooter.next    = { color: randomAvailableColor() };
  const nextEl = document.getElementById('nextLabel');
  if(nextEl) nextEl.textContent = colorName(state.shooter.next.color);
}

//// Matching & floating islands ////////////////////////////////
function key(c,r){ return c+","+r; }

function bfsSameColor(c0, r0){
  if(!inBounds(c0,r0)) return [];
  const start = state.grid[r0][c0];
  if(!start) return [];
  const color = start.color;
  const q = [{c:c0,r:r0}], seen = new Set([key(c0,r0)]), out = [{c:c0,r:r0}];
  while(q.length){
    const {c,r} = q.shift();
    for(const nb of neighbors(c,r)){
      if(!inBounds(nb.c, nb.r)) continue;
      if(seen.has(key(nb.c, nb.r))) continue;
      const cell = state.grid[nb.r][nb.c];
      if(cell && cell.color === color){
        seen.add(key(nb.c, nb.r));
        q.push(nb);
        out.push(nb);
      }
    }
  }
  return out;
}

function popClusterAt(c, r){
  const cluster = bfsSameColor(c,r);
  if(cluster.length >= 3){
    for(const {c, r} of cluster){ state.grid[r][c] = null; }
    state.score += cluster.length * 10;
    return cluster.length;
  }
  return 0;
}

function computeReachableFromCeiling(){
  const seen = new Set();
  const q = [];
  if(state.rows > 0){
    for(let c=0;c<rowCols(0);c++){
      if(state.grid[0][c]){ seen.add(key(c,0)); q.push({c,r:0}); }
    }
  }
  while(q.length){
    const {c,r} = q.shift();
    for(const nb of neighbors(c,r)){
      if(!inBounds(nb.c, nb.r)) continue;
      if(seen.has(key(nb.c, nb.r))) continue;
      if(state.grid[nb.r][nb.c]){ seen.add(key(nb.c, nb.r)); q.push(nb); }
    }
  }
  return seen;
}

function dropIslands(){
  const reachable = computeReachableFromCeiling();
  const toDrop = [];
  for(let r=0;r<state.rows;r++){
    for(let c=0;c<rowCols(r);c++){
      if(state.grid[r][c] && !reachable.has(key(c,r))){ toDrop.push({c,r}); }
    }
  }
  if(!toDrop.length) return 0;
  for(const {c,r} of toDrop){
    const {x,y} = cellToWorld(c,r);
    const color = state.grid[r][c].color;
    state.grid[r][c] = null;
    state.falling.push({ x, y, vy: 0, color });
  }
  state.score += toDrop.length * 5;
  return toDrop.length;
}

//// Input ///////////////////////////////////////////////////////
const pointer = { x: LOGICAL_W/2, y: LOGICAL_H/2, down:false };
canvas.addEventListener('mousemove', e => {
  const rect = canvas.getBoundingClientRect();
  pointer.x = (e.clientX - rect.left) * (LOGICAL_W / rect.width);
  pointer.y = (e.clientY - rect.top) * (LOGICAL_H / rect.height);
});
canvas.addEventListener('mousedown', () => { pointer.down = true; });
canvas.addEventListener('mouseup',   () => { pointer.down = false; });
canvas.addEventListener('touchstart', e => handleTouch(e, true));
canvas.addEventListener('touchmove',  e => handleTouch(e, false));
canvas.addEventListener('touchend',   () => { pointer.down = false; });
function handleTouch(e, press){
  const t = e.touches[0]; if(!t) return;
  const rect = canvas.getBoundingClientRect();
  pointer.x = (t.clientX - rect.left) * (LOGICAL_W / rect.width);
  pointer.y = (t.clientY - rect.top) * (LOGICAL_H / rect.height);
  if(press) pointer.down = true;
  e.preventDefault();
}

//// Shooting ////////////////////////////////////////////////////
function clamp(v, a, b){ return Math.max(a, Math.min(b, v)); }

function shoot(){
  if(state.moving || !state.running || state.mode !== 'playing') return;
  const { x, y } = state.shooter;
  const dx = pointer.x - x, dy = y - pointer.y; // invert Y so up is positive
  let angle = Math.atan2(dy, dx);
  angle = clamp(angle, MIN_ANGLE, MAX_ANGLE);
  const vx = Math.cos(angle) * SHOOT_SPEED;
  const vy = -Math.sin(angle) * SHOOT_SPEED; // negative vy moves up on canvas
  const color = state.shooter.current.color;
  state.moving = { x, y, vx, vy, color };
  state.shooter.current = state.shooter.next;
  state.shooter.next = { color: randomAvailableColor() };
  document.getElementById('nextLabel').textContent = colorName(state.shooter.next.color);

  // Count the shot immediately; schedule drop after resolution if needed
  if(state.mode === 'playing'){
    state.drop.shotsLeft -= 1;
    if(state.drop.shotsLeft <= 0){
      state.drop.pending = true;           // perform drop when shot resolves
      state.drop.shotsLeft = state.drop.every;
    }
    updateDropHud();
  }
}

canvas.addEventListener('click', shoot);
window.addEventListener('keydown', (e) => {
  if(e.key === ' ') shoot();
  if(e.key.toLowerCase() === 'p'){
    state.running = !state.running;
    document.getElementById('btnPause').textContent = state.running ? 'Pause' : 'Resume';
  }
  if(e.key.toLowerCase() === 'r') restart();
});
document.getElementById('btnPause').addEventListener('click', () => {
  state.running = !state.running;
  document.getElementById('btnPause').textContent = state.running ? 'Pause' : 'Resume';
});
document.getElementById('btnRestart').addEventListener('click', restart);

//// Collision & snapping ///////////////////////////////////////
function hitsSideWall(ball){
  return (ball.x - R <= 0 && ball.vx < 0) || (ball.x + R >= LOGICAL_W && ball.vx > 0);
}
function reflectX(ball){ ball.vx = -ball.vx; }
function distance2(ax,ay,bx,by){ const dx=ax-bx, dy=ay-by; return dx*dx+dy*dy; }

function findCollision(ball){
  // 1) Ceiling
  if(ball.y - R <= 0){
    return { type:'ceiling', at:{x:ball.x, y:R} };
  }
  // 2) Grid nearby
  const approxR = Math.max(0, Math.round((ball.y - R)/ROW_H));
  const rowsToCheck = [];
  for(let rr = approxR-2; rr <= approxR+2; rr++) if(rr>=0 && rr<state.rows) rowsToCheck.push(rr);
  const rr2 = (R+R)*(R+R);

  for(const r of rowsToCheck){
    for(let c=0;c<rowCols(r);c++){
      const cell = state.grid[r][c];
      if(!cell) continue;
      const p = cellToWorld(c,r);
      if(distance2(ball.x, ball.y, p.x, p.y) <= rr2){
        return { type:'grid', cell:{x:p.x,y:p.y,c,r} };
      }
    }
  }
  return null;
}

function snapToNearestFreeCell(x, y){
  let {c, r} = worldToCell(x, y);
  r = Math.max(0, r);
  ensureRows(r+2);

  const candidates = [{c,r}];
  for(const n of neighbors(c,r)) candidates.push(n);
  for(const n1 of neighbors(c,r)) for(const n2 of neighbors(n1.c,n1.r)) candidates.push(n2);

  let best = null, bestD2 = Infinity;
  for(const cand of candidates){
    if(!inBounds(cand.c, cand.r)) continue;
    if(occupiedAt(cand.c, cand.r)) continue;
    const p = cellToWorld(cand.c, cand.r);
    const d2 = distance2(x,y,p.x,p.y);
    if(d2 < bestD2){ bestD2 = d2; best = { c:cand.c, r:cand.r, x:p.x, y:p.y }; }
  }
  return best;
}

//// Ceiling drop mechanics /////////////////////////////////////
function makeRowAt(r){
  const arr = new Array(rowCols(r)).fill(null);
  const pool = activeColorPool();
  for(let c=0;c<arr.length;c++){
    arr[c] = { color: pool[Math.floor(Math.random()*pool.length)] };
  }
  return arr;
}

function dropCeiling(rows=1){
  for(let i=0;i<rows;i++){
    const newRow = makeRowAt(0);
    state.grid.unshift(newRow);
  }
  // Normalize row lengths after parity shift
  for(let r=0;r<state.grid.length;r++){
    const targetLen = rowCols(r);
    const row = state.grid[r];
    if(row.length < targetLen){
      for(let k=row.length; k<targetLen; k++) row.push(null);
    } else if(row.length > targetLen){
      row.length = targetLen;
    }
  }
  state.rows = state.grid.length;
  updateDropHud();
  checkWinLose();
}

function updateDropHud(){
  const el = document.getElementById('drop');
  if(el) el.textContent = state.drop.shotsLeft.toString();
}

function onShotResolved(){
  if(state.mode !== 'playing') return;
  if(state.drop.pending){
    state.drop.pending = false;
    dropCeiling(state.drop.rows);
  }
}

//// Win/Lose ////////////////////////////////////////////////////
function gridIsEmpty(){
  for(let r=0;r<state.rows;r++){
    for(let c=0;c<rowCols(r);c++) if(state.grid[r][c]) return false;
  }
  return true;
}
function touchesFloor(){
  for(let r=0;r<state.rows;r++){
    for(let c=0;c<rowCols(r);c++){
      if(state.grid[r][c]){
        const p = cellToWorld(c,r);
        if(p.y + R >= LOGICAL_H - 1) return true;
      }
    }
  }
  return false;
}
function checkWinLose(){
  if(gridIsEmpty()){
    state.mode = 'win';
    state.running = false;
    return;
  }
  if(touchesFloor()){
    state.mode = 'lose';
    state.running = false;
  }
}

//// Update / Draw //////////////////////////////////////////////
let last = performance.now();
function loop(now){
  const dt = Math.min(0.033, (now - last) / 1000);
  last = now;
  if(state.running) update(dt);
  draw();
  requestAnimationFrame(loop);
}

function update(dt){
  // Update aim
  const dx = pointer.x - state.shooter.x, dy = state.shooter.y - pointer.y;
  let ang = Math.atan2(dy, dx);
  state.shooter.angle = clamp(ang, MIN_ANGLE, MAX_ANGLE);

  // Move shot bubble
  if(state.moving){
    const b = state.moving;
    b.x += b.vx * dt;
    b.y += b.vy * dt;
    if(hitsSideWall(b)) reflectX(b);

    const hit = findCollision(b);
    if(hit){
      let targetCell = null;
      if(hit.type === 'ceiling'){
        targetCell = snapToNearestFreeCell(b.x, R);
      } else if(hit.type === 'grid'){
        targetCell = snapToNearestFreeCell(b.x, b.y);
      }
      if(targetCell){
        placeAt(targetCell.c, targetCell.r, b.color);
        const popped = popClusterAt(targetCell.c, targetCell.r);
        if(popped > 0) dropIslands();
        checkWinLose();
        onShotResolved(); // perform pending drop after resolution
      }
      state.moving = null;
    }

    // If bubble falls below screen, resolve anyway
    if(b.y - R > LOGICAL_H + 20){
      state.moving = null;
      onShotResolved(); // counts toward drop if it was pending
    }
  }

  // Update falling bubbles (island drops)
  if(state.falling.length){
    for(const f of state.falling){
      f.vy += 1800 * dt; // gravity
      f.y += f.vy * dt;
    }
    // cull offscreen
    state.falling = state.falling.filter(f => f.y - R <= LOGICAL_H + 60);
  }

  // Extra safety: check end states
  if(state.mode === 'playing') checkWinLose();
}

function draw(){
  ctx.clearRect(0,0,LOGICAL_W,LOGICAL_H);

  // Ceiling line
  ctx.globalAlpha = 0.25;
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, LOGICAL_W, 4);
  ctx.globalAlpha = 1;

  // Grid
  for(let r=0;r<state.rows;r++){
    for(let c=0;c<rowCols(r);c++){
      const cell = state.grid[r][c];
      if(cell){ const p = cellToWorld(c,r); drawBubble(p.x, p.y, cell.color); }
    }
  }

  // Moving bubble
  if(state.moving){ drawBubble(state.moving.x, state.moving.y, state.moving.color); }
  // Falling islands
  for(const f of state.falling){ drawBubble(f.x, f.y, f.color); }

  // Shooter & aim
  drawShooter();
  if(state.mode === 'playing') drawAimGuide();

  // HUD
  document.getElementById('score').textContent = state.score.toString();

  // Win/Lose overlay
  if(state.mode !== 'playing'){
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    ctx.fillRect(0,0,LOGICAL_W,LOGICAL_H);
    ctx.fillStyle = '#eef1ff';
    ctx.font = 'bold 28px system-ui, -apple-system, Segoe UI, Roboto';
    ctx.textAlign = 'center';
    ctx.fillText(state.mode === 'win' ? 'You Win!' : 'Game Over', LOGICAL_W/2, LOGICAL_H/2 - 8);
    ctx.font = '16px system-ui, -apple-system, Segoe UI, Roboto';
    ctx.fillText('Press R to Restart', LOGICAL_W/2, LOGICAL_H/2 + 24);
    ctx.restore();
  }
}

//// Drawing helpers ////////////////////////////////////////////
function drawBubble(x,y,color){
  // Body
  ctx.beginPath();
  ctx.arc(x,y,R,0,Math.PI*2);
  ctx.fillStyle = color;
  ctx.fill();
  // Rim
  ctx.lineWidth = 2;
  ctx.strokeStyle = 'rgba(0,0,0,.35)';
  ctx.stroke();
  // Gloss
  const gx = x - R*0.4, gy = y - R*0.4;
  const gr = ctx.createRadialGradient(gx,gy,1, x,y,R);
  gr.addColorStop(0, 'rgba(255,255,255,.9)');
  gr.addColorStop(0.25, 'rgba(255,255,255,.4)');
  gr.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = gr;
  ctx.beginPath(); ctx.arc(x,y,R,0,Math.PI*2); ctx.fill();
}

function drawShooter(){
  const s = state.shooter;

  // safe rounded-rect path (no roundRect dependency)
  function pathRoundRect(x,y,w,h,r){
    const rr = Math.min(r, Math.abs(w)/2, Math.abs(h)/2);
    ctx.moveTo(x+rr,y);
    ctx.arcTo(x+w,y,x+w,y+h,rr);
    ctx.arcTo(x+w,y+h,x,y+h,rr);
    ctx.arcTo(x,y+h,x,y,rr);
    ctx.arcTo(x,y,x+w,y,rr);
    ctx.closePath();
  }

  ctx.save();
  ctx.translate(s.x, s.y);
  ctx.rotate(s.angle);

  // Base
  ctx.fillStyle = '#2a3161';
  ctx.strokeStyle = 'rgba(255,255,255,.15)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  pathRoundRect(-18,-10,36,20,10);
  ctx.fill();
  ctx.stroke();

  // Barrel
  ctx.fillStyle = '#3b4489';
  ctx.beginPath();
  pathRoundRect(0,-4,40,8,4);
  ctx.fill();

  ctx.restore();

  // Current bubble in barrel
  drawBubble(s.x, s.y, s.current?.color || '#888');
}

function drawAimGuide(){
  const s = state.shooter;
  const len = 120, step = 10;
  const dx = Math.cos(s.angle), dy = -Math.sin(s.angle);
  ctx.save();
  ctx.globalAlpha = 0.6;
  for(let t=10;t<len;t+=step){
    const x = s.x + dx * t;
    const y = s.y + dy * t;
    ctx.beginPath();
    ctx.arc(x,y,2,0,Math.PI*2);
    ctx.fillStyle = '#eef1ff';
    ctx.fill();
  }
  ctx.restore();
}

function colorName(hex){
  const map = {
    '#ff6b6b':'Red', '#feca57':'Yellow', '#1dd1a1':'Green',
    '#54a0ff':'Blue', '#c56cf0':'Purple', '#ff9ff3':'Pink'
  };
  return map[hex] || '#';
}

//// Restart & Boot /////////////////////////////////////////////
function restart(){
  state.running = true;
  state.mode = 'playing';
  state.score = 0;
  state.moving = null;
  state.falling = [];
  seedBoard(6);
  state.shooter.current = null;
  state.shooter.next = null;
  state.drop.shotsLeft = state.drop.every;
  state.drop.pending = false;
  updateDropHud();
  prepareShooter();
}

seedBoard(6);
prepareShooter();
state.drop.shotsLeft = state.drop.every;
updateDropHud();
requestAnimationFrame(loop);
