const COLORS = { "Google Chrome":"#4285f4", "Claude Code":"#c96442", "Vim":"#019833",
  "Neovim":"#019833", "Viber":"#7360f2", "Firefox":"#ff7139", "memmon":"#7a5cd6",
  "Terminal":"#5a5852", "VS Code":"#0078d4", "Files":"#77767b", "Slack":"#4a154b" };
const PALETTE = ["#2f7d8c","#a8642b","#7a5cd6","#3f7d3f","#94566f","#736b5e"];
const colorOf = a => COLORS[a] || (COLORS[a] = PALETTE[Object.keys(COLORS).length % PALETTE.length]);
const $ = s => document.querySelector(s);
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const utf8 = new TextEncoder();
// INSERT is wherever the keyboard is: a terminal or a document has it
const inInsert = () => document.body.classList.contains('insert');
// ids for things made here; two made in the same millisecond still differ
let idCount = 0;
const newId = () => Date.now().toString(36) + (idCount++ % 36).toString(36);

// The arrangement lives here, not on the desktop: dragging a window on the
// virtual screen moves the tile and nothing else. Kept per window id, so a
// window we have not seen before falls back to where it really is.
const store = {
  get(k, fb) { try { return JSON.parse(localStorage.getItem('winlist.' + k)) ?? fb; }
               catch { return fb; } },
  set(k, v) { try { localStorage.setItem('winlist.' + k, JSON.stringify(v)); } catch {} },
};

let data = null, failures = 0, sel = null;
let started = null;                        // which run of the server we are talking to
let bare = store.get('bare', true);        // top bar folded away, the surface takes the page
let layout = store.get('layout', {});      // window id -> [x, y] on the virtual screen
let zoom = store.get('zoom', 0);           // 0 until we have measured a fit
let origin = store.get('origin', [0, 0]);  // where the surface sits in the frame
const saveLayout = () => store.set('layout', layout);

// A drag's three listeners, put on together; what comes back takes them off.
function follow(target, move, end) {
  target.addEventListener('pointermove', move);
  target.addEventListener('pointerup', end);
  target.addEventListener('pointercancel', end);
  return () => {
    target.removeEventListener('pointermove', move);
    target.removeEventListener('pointerup', end);
    target.removeEventListener('pointercancel', end);
  };
}
const CAP_H = 28;                          // screen px: a tile's caption, as .cap sets it
const GRID = 40;                           // virtual px: what moving and resizing snap to
const GUTTER = 140;                        // virtual px between one workspace and the next

function shotUrl(i) {
  const s = data.shots && data.shots[i];
  return s ? `/api/screen/${i}?v=${encodeURIComponent(s.clock)}` : null;
}


// always the whole browser window, F11 not involved
document.body.classList.add('full', 'app');
function setBare(v) {
  bare = v;
  store.set('bare', v);
  document.body.classList.toggle('bare', v);
  $('#tray').textContent = v ? '▾' : '▴';
  render();
}
$('#tray').onclick = () => setBare(!bare);

// none of the plumbing shows on the page, so it gets a picture of its own
const archbox = $('#archbox');
const showArch = () => { if (!archbox.open) archbox.showModal(); };
$('#arch').onclick = showArch;
$('#archclose').onclick = () => archbox.close();
// the bar only has room for the common keys; ? lists them all
// u asks for a URL; the server finds the page's title, as for one sent by curl
const linkbox = $('#linkbox');
function askLink() {
  if (linkbox.open) return;
  $('#linkurl').value = '';
  linkbox.returnValue = '';          // else Esc would reuse the last Add
  linkbox.showModal();
  $('#linkurl').focus();
}
linkbox.addEventListener('close', async () => {
  let url = $('#linkurl').value.trim();
  if (linkbox.returnValue !== 'add' || !url) return;
  if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
  try {
    const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ url }) });
    const l = await r.json();
    if (!r.ok) return;
    markTaken(l.id);                           // made here, so the poll leaves it be
    takeCard(l);
  } catch {}
});
// whatever kind of card the server sent: a page, a document or a picture
const takeCard = l => l.image ? addImage(l.image, l.title)
  : l.path ? addDoc(l.path, l.title) : addLink(l.url, l.title);

// p asks for a picture: a file on this machine or an image on the web
const imgbox = $('#imgbox');
function askImage(msg) {
  if (imgbox.open) return;
  $('#imgsrc').value = '';
  $('#imgsrc').placeholder = msg || 'Path to an image, or an image URL';
  imgbox.returnValue = '';
  imgbox.showModal();
  $('#imgsrc').focus();
}
imgbox.addEventListener('close', async () => {
  const image = $('#imgsrc').value.trim();
  if (imgbox.returnValue !== 'add' || !image) return;
  try {
    const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ image }) });
    const l = await r.json();
    if (!r.ok) return askImage('Could not open it: ' + (l.error || 'unknown error'));
    markTaken(l.id);
    takeCard(l);
  } catch {}
});
// o asks for a markdown file; the server checks it is one before it is shown
const docbox = $('#docbox');
function askDoc() {
  if (docbox.open) return;
  $('#docpath').value = '';
  docbox.returnValue = '';
  docbox.showModal();
  $('#docpath').focus();
}
docbox.addEventListener('close', async () => {
  const path = $('#docpath').value.trim();
  if (docbox.returnValue !== 'add' || !path) return;
  try {
    const r = await fetch('/api/file?path=' + encodeURIComponent(path));
    const d = await r.json();
    if (!r.ok) return alertDoc(d.error);
    addDoc(d.path, d.name);
  } catch {}
});
function alertDoc(msg) {            // said where you were typing, not in a modal
  askDoc();
  $('#docpath').value = '';
  $('#docpath').placeholder = 'Could not open it: ' + (msg || 'unknown error');
}
const helpbox = $('#helpbox');
const showHelp = () => { if (!helpbox.open) helpbox.showModal(); };
$('#helpclose').onclick = () => helpbox.close();
// squared, so the slider gives fine control down at the small end where the
// whole surface lives and still reaches far enough in to read a window
$('#zoom').addEventListener('input', () => {
  setZoom(MAX_ZOOM * Math.pow($('#zoom').value / 100, 2));
});
// 1:1 is the one zoom where a terminal is not scaled at all, so its text lands
// on whole pixels; held about the picked tile, or the middle with none picked
function actualSize() {
  const el = sel && tileEls.get(sel);
  if (!el) setZoom(1);
  else {
    const r = el.getBoundingClientRect();
    zoomAbout(1, r.left + r.width / 2, r.top + r.height / 2);
  }
  // and on whole screen pixels too: half a pixel off and the text smears
  const box = $('#pan').getBoundingClientRect();
  shift(Math.round(box.left + origin[0]) - box.left - origin[0],
        Math.round(box.top + origin[1]) - box.top - origin[1]);
}
$('#actual').onclick = actualSize;
$('#reset').onclick = () => {
  layout = {};
  saveLayout();
  render();
};
addEventListener('resize', render);
$('#q').addEventListener('input', () => { sel = null; render(); });

// A window that has closed leaves its place behind in the layout. It is let go
// once it has been missing for a minute of polls — not on the first, since a
// window can blink out while it is being remapped — and a terminal's place is
// kept while the terminal server is not answering, when they all look gone.
const missing = new Map();        // window id -> polls it has been absent for
function forgetGone() {
  const here = new Set(data.windows.map(w => w.id));
  const ptyDown = !data.pty || !data.pty.on || data.pty.error;
  let changed = false;
  Object.keys(layout).forEach(id => {
    if (here.has(id) || (ptyDown && id.startsWith('web:'))) return missing.delete(id);
    const n = (missing.get(id) || 0) + 1;
    missing.set(id, n);
    if (n >= 30) { delete layout[id]; missing.delete(id); changed = true; }
  });
  if (changed) saveLayout();
}

async function poll() {
  try {
    // asking for screens is what keeps the grabber awake
    const r = await fetch('/api/windows?screens=1');
    const got = await r.json();
    // an error answer is no picture of the desktop: keep the last good one
    if (!r.ok || !Array.isArray(got.windows)) throw new Error(got.error || r.status);
    data = got;
    data.windows.push(...links.map(linkWin));
    // a link sent from outside becomes a card once; the server keeps offering it
    (data.links || []).forEach(l => {
      if (taken.includes(l.id)) return;
      markTaken(l.id);
      takeCard(l);
    });
    forgetGone();
    failures = 0;
    // restarted from its terminal: the page it served is the old one
    if (started !== null && data.started !== started) return location.reload();
    started = data.started;
  } catch { failures++; }
  render();
}

function visible() {
  const q = $('#q').value.trim().toLowerCase();
  return w => !q || (w.title + " " + w.app).toLowerCase().includes(q);
}

function onWorkspace(i) { return data.windows.filter(w => w.desktop === i); }

// Windows of one app sit together, apps ordered by their topmost window, so two
// windows sharing a title never end up split by something stacked between them.
function byApp(ws) {
  const order = [], groups = new Map();
  ws.forEach(w => {
    if (!groups.has(w.app)) { groups.set(w.app, []); order.push(w.app); }
    groups.get(w.app).push(w);
  });
  return order.map(app => [app, groups.get(app)]);
}

// the on-screen order, which is what the arrow keys walk
function ordered(i) { return byApp(onWorkspace(i)).flatMap(([, group]) => group); }

// ---- groups: a frame you put windows in, and move together ----------------
let groups = store.get('groups', []);   // [{id, name, x, y, w, h}] in surface px
const groupEls = new Map();

function newGroup() {
  const w = 1600, h = 1000, [cx, cy] = viewCenter();
  const [x, y] = clearSpot([cx - w / 2, cy - h / 2]);
  groups.push({ id: newId(), name: 'Group', x, y, w, h });
  store.set('groups', groups);
  render();
}

function saveGroups() { store.set('groups', groups); }

function placeGroup(el, g) {
  el.style.left = g.x * zoom + 'px';
  el.style.top = g.y * zoom + 'px';
  el.style.width = g.w * zoom + 'px';
  el.style.height = g.h * zoom + 'px';
}

// only a window wholly inside is the group's: one hanging over the edge stays put
function members(g) {
  return data.windows.filter(w => {
    const [x, y] = seatOf(w);
    return x >= g.x && y >= g.y && x + w.w <= g.x + g.w && y + w.h <= g.y + g.h;
  });
}

function carryGroup(e, g, el) {
  if (e.button || pointers.size > 1) return;   // a second finger means pinch
  e.preventDefault();
  e.stopPropagation();                  // the caption is not the surface: no pan
  const sx = e.clientX, sy = e.clientY, gx = g.x, gy = g.y;
  const riders = members(g).map(w => [w, seatOf(w), layout[w.id]]);
  el.classList.add('dragging');
  el.setPointerCapture(e.pointerId);
  showGrid(true);
  const move = ev => {
    const dx = snap((ev.clientX - sx) / zoom), dy = snap((ev.clientY - sy) / zoom);
    g.x = gx + dx; g.y = gy + dy;
    placeGroup(el, g);
    riders.forEach(([w, [x, y]]) => {
      layout[w.id] = [x + dx, y + dy];
      const t = tileEls.get(w.id);
      if (t) place(t, w);
    });
  };
  const done = undo => {
    off();
    el.classList.remove('dragging');
    showGrid(false);
    letGo = null;
    if (undo === true) {             // a pinch began: the group and its windows go back
      g.x = gx; g.y = gy;
      riders.forEach(([w, , had]) => { if (had) layout[w.id] = had; else delete layout[w.id]; });
    }
    saveGroups();
    saveLayout();
    render();
  };
  letGo = () => done(true);
  const off = follow(el, move, done);
}

function sizeGroup(e, g, el) {
  if (e.button || pointers.size > 1) return;   // a second finger means pinch
  e.preventDefault();
  e.stopPropagation();
  const sx = e.clientX, sy = e.clientY, w0 = g.w, h0 = g.h;
  el.setPointerCapture(e.pointerId);
  showGrid(true);
  const move = ev => {
    g.w = Math.max(GRID * 4, snap(w0 + (ev.clientX - sx) / zoom));
    g.h = Math.max(GRID * 3, snap(h0 + (ev.clientY - sy) / zoom));
    placeGroup(el, g);
  };
  const off = follow(el, move, () => {
    off();
    showGrid(false);
    saveGroups();
  });
}

// a double click on the name renames it; Enter or leaving keeps the new one
function rename(g, name) {
  name.contentEditable = 'true';
  name.focus();
  getSelection().selectAllChildren(name);
  const end = () => {
    name.contentEditable = 'false';
    g.name = name.textContent.trim() || 'Group';
    name.textContent = g.name;
    saveGroups();
  };
  name.addEventListener('blur', end, { once: true });
  name.onkeydown = ev => {
    ev.stopPropagation();
    if (ev.key === 'Enter' || ev.key === 'Escape') { ev.preventDefault(); name.blur(); }
  };
}

function renderGroups() {
  const live = new Set();
  groups.forEach(g => {
    live.add(g.id);
    let el = groupEls.get(g.id);
    if (!el) {
      el = document.createElement('div');
      el.className = 'group';
      el.innerHTML = `<div class="gcap"><span class="gname"></span>`
        + `<span class="shut" title="Remove the group (its windows stay)">✕</span></div>`
        + `<div class="grip" title="Drag to resize this group"></div>`;
      const cap = el.querySelector('.gcap'), name = el.querySelector('.gname');
      cap.addEventListener('pointerdown', e => {
        if (name.isContentEditable) return e.stopPropagation();
        if (e.target.closest('.shut')) {
          e.preventDefault(); e.stopPropagation();
          groups = groups.filter(v => v !== el.group);
          saveGroups();
          return render();
        }
        carryGroup(e, el.group, el);
      });
      cap.addEventListener('dblclick', e => {
        if (e.target === name) rename(el.group, name);
      });
      el.querySelector('.grip').addEventListener('pointerdown', e => sizeGroup(e, el.group, el));
      groupEls.set(g.id, el);
      $('#groups').append(el);
    }
    el.group = g;
    if (!el.querySelector('.gname').isContentEditable) el.querySelector('.gname').textContent = g.name;
    placeGroup(el, g);
  });
  groupEls.forEach((el, id) => { if (!live.has(id)) { el.remove(); groupEls.delete(id); } });
}

function render() {
  if (!data) return;
  const match = visible(), q = $('#q').value.trim();
  renderGroups();
  renderCanvas(match);
  status(match, q);
  syncLens();
}

function status(match, q) {
  const hits = data.windows.filter(w => !w.link && match(w));
  const ours = data.windows.filter(w => w.term).length;
  const desks = new Set(data.windows.filter(w => !w.term).map(w => w.desktop)).size;
  $('#stat').textContent = `${hits.length - ours}${q ? " of " + (data.windows.length - links.length - ours) : ""} windows · `
    + (ours ? `${ours} terminal${ours > 1 ? 's' : ''} of our own · ` : '')
    + `${data.grid.cols}×${data.grid.rows} workspaces · ${desks} in use`;
  $('#ts').innerHTML = failures ? `<span class="stale">disconnected — retrying</span>`
    : `updated ${data.captured}`;
  $('#foot').innerHTML = `Every window on one surface, seeded from where it `
      + `really sits and then yours to arrange: drag a tile and only the tile moves — the `
      + `desktop is never touched. The arrangement is remembered in this browser; `
      + `<b>Reset layout</b> puts everything back where the desktop has it. Scroll or `
      + `pinch to zoom, drag the background or slide two fingers to pan, and click a window `
      + `(or press <kbd>Enter</kbd>) to focus it for real. Windows start out grouped by `
      + `the workspace they live on, packed together rather than spread over the desktop's `
      + `own grid.`
    + (!data.shots_on
        ? ` Screens are off (<code>--no-screens</code>), so tiles stay plain colours.`
        : data.shot_error
        ? ` No photographs: ${esc(data.shot_error)}.`
        : ` X can only photograph the workspace in front of you, so a tile shows the last `
          + `look at its workspace; visit one to fill its windows in.`)
    + (!data.pty || !data.pty.on ? ''
       : data.pty.error
       ? ` No terminals: ${esc(data.pty.error)}. Start it with <code>python3 winlist/pty_server.py</code>.`
       : ` <b>New terminal</b> starts a shell of this page's own, off to the right of the `
         + `workspaces — drag it by its title bar, click into it and type. It lives in `
         + `<code>pty_server.py</code>, not in this tab, so a reload picks it back up.`);
}


// ---- the virtual screen ----------------------------------------------------
// One surface holding every window there is, and it goes on forever: the
// surface is drawn at an offset and a scale of our choosing rather than scrolled
// inside a box, so a drag can carry everything anywhere and the zoom has no
// stops. A tile starts life where its window really sits and from then on you
// put it wherever you like. Nothing here talks to the window manager: dragging
// rearranges the picture, not the desktop.

const tileEls = new Map();   // window id -> element, kept so a drag survives a poll
const MIN_ZOOM = 0.02, MAX_ZOOM = 4;

// Where a window starts out. The desktop's own 3x6 grid is no use here: it is
// far taller than any browser window and most of its cells are empty, so the
// workspaces that actually hold something get packed into a squarish block
// instead. Windows that shared a workspace still start out together.
let seating = { key: '', cols: 1, at: new Map() };
function plan() {
  const used = [...new Set(data.windows.filter(w => !w.link).map(w => w.desktop))].sort((a, b) => a - b);
  const key = used.join(',');
  if (key !== seating.key) {
    seating = { key, cols: Math.max(1, Math.ceil(Math.sqrt(used.length))),
                at: new Map(used.map((d, i) => [d, i])) };
  }
  return seating;
}

function seat(w) {
  const p = plan(), i = p.at.get(w.desktop) || 0;
  const col = i % p.cols, row = Math.floor(i / p.cols);
  return [col * (data.screen.w + GUTTER) + Math.max(0, w.x),
          row * (data.screen.h + GUTTER) + Math.max(0, w.y)];
}
const seatOf = w => layout[w.id] || seat(w);

// what the windows actually cover, which is the thing worth fitting
function bounds() {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  data.windows.forEach(w => {
    const [x, y] = seatOf(w);
    x0 = Math.min(x0, x); y0 = Math.min(y0, y);
    x1 = Math.max(x1, x + Math.max(240, w.w)); y1 = Math.max(y1, y + Math.max(160, w.h));
  });
  return isFinite(x0) ? [x0, y0, x1, y1] : [0, 0, 1, 1];
}

const clamp = z => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

// the point on the surface at the middle of the frame
function viewCenter() {
  const pan = $('#pan');
  return [(pan.clientWidth / 2 - origin[0]) / zoom, (pan.clientHeight / 2 - origin[1]) / zoom];
}

function shift(dx, dy) {          // slide the whole surface, no edges to run into
  origin = [origin[0] + dx, origin[1] + dy];
  store.set('origin', origin);
  $('#canvas').style.transform = `translate(${origin[0]}px,${origin[1]}px)`;
  markEdges();
}

// A triangle on the frame's edge for windows wholly out of view, on the line from
// the frame's middle to the window's. Nearby ones share a triangle, and a window
// the search has ruled out gets none.
let edgeQueued = false;
function markEdges() {
  if (edgeQueued) return;
  edgeQueued = true;
  requestAnimationFrame(() => { edgeQueued = false; drawEdges(); });
}
function drawEdges() {
  const pan = $('#pan'), box = $('#edges'), W = pan.clientWidth, H = pan.clientHeight;
  const spots = new Map();
  if (data && W && H) {
    const match = visible(), cx = W / 2, cy = H / 2, inset = 8;
    data.windows.forEach(w => {
      if (!match(w)) return;
      const [x, y] = seatOf(w);
      const px = origin[0] + x * zoom, py = origin[1] + y * zoom;
      const pw = w.term ? w.w * zoom : Math.max(90, w.w * zoom);
      const ph = w.term ? w.h * zoom : Math.max(60, w.h * zoom);
      if (px < W && px + pw > 0 && py < H && py + ph > 0) return;   // some of it shows
      const dx = px + pw / 2 - cx, dy = py + ph / 2 - cy;
      const k = Math.min((cx - inset) / Math.abs(dx || 1e-9), (cy - inset) / Math.abs(dy || 1e-9));
      const ex = cx + dx * k, ey = cy + dy * k;
      spots.set(Math.round(ex / 40) + ',' + Math.round(ey / 40),
                [ex, ey, Math.atan2(dy, dx)]);
    });
  }
  const list = [...spots.values()];
  while (box.children.length < list.length) {
    const d = document.createElement('div');
    d.className = 'edge';
    box.append(d);
  }
  while (box.children.length > list.length) box.lastChild.remove();
  list.forEach(([ex, ey, a], i) => {
    const s = box.children[i].style;
    s.left = ex + 'px';
    s.top = ey + 'px';
    s.transform = `rotate(${a}rad)`;
  });
}

// zoom about a point: whatever is under the mouse, or between the fingers, is
// the one thing that must not move
function zoomAbout(next, cx, cy) {
  next = clamp(next);
  if (next === zoom) return;
  const box = $('#pan').getBoundingClientRect();
  const fx = cx - box.left, fy = cy - box.top;
  origin = [fx - (fx - origin[0]) / zoom * next, fy - (fy - origin[1]) / zoom * next];
  zoom = next;
  store.set('zoom', zoom);
  store.set('origin', origin);
  render();
}

function setZoom(z) {
  const box = $('#pan').getBoundingClientRect();
  zoomAbout(z, box.left + box.width / 2, box.top + box.height / 2);   // about the middle
}

function fitAll() {
  const pan = $('#pan'), [x0, y0, x1, y1] = bounds();
  const pad = 24;
  zoom = clamp(Math.min((pan.clientWidth - pad * 2) / (x1 - x0),
                        (pan.clientHeight - pad * 2) / (y1 - y0)));
  origin = [(pan.clientWidth - (x1 - x0) * zoom) / 2 - x0 * zoom,
            (pan.clientHeight - (y1 - y0) * zoom) / 2 - y0 * zoom];
  store.set('zoom', zoom);
  store.set('origin', origin);
}

// ---- links: a page you mean to come back to, kept as a card ---------------
let links = store.get('links', []);
let taken = store.get('taken', []);    // ids of links sent from outside, already carded
function markTaken(id) {
  taken = [...taken, id].slice(-50);
  store.set('taken', taken);
}

function linkWin(l) {
  return { id: 'link:' + l.id, link: l, title: l.title,
           app: l.image ? 'Image' : l.path ? 'Markdown' : new URL(l.url).host,
           w: l.w || (l.image ? 640 : l.path ? 720 : 320),
           h: l.h || (l.image ? 480 : l.path ? 900 : 76),
           x: 0, y: 0, z: 1e9, desktop: null };
}

// ---- docs: a markdown file kept on the surface, read again when it changes --
const docs = new Map();             // path -> {mtime, html} or {error}
const md = new marked.Marked({ gfm: true });
md.use({ renderer: {
  // a file can carry HTML, and this page can type into terminals: none of it runs
  html: () => '',
  link: (href, title, text) => /^(https?:|mailto:)/i.test(href || '')
    ? `<a href="${esc(href)}" target="_blank" rel="noopener">${text}</a>` : text,
  image: (href, title, text) => /^https?:/i.test(href || '')
    ? `<img src="${esc(href)}" alt="${esc(text || '')}">` : esc(text || ''),
} });

async function readDocs() {
  let changed = false;
  for (const l of links) {
    if (!l.path) continue;
    const had = docs.get(l.path);
    const q = 'path=' + encodeURIComponent(l.path) + (had && had.mtime ? '&since=' + had.mtime : '');
    try {
      const r = await fetch('/api/file?' + q), d = await r.json();
      if (!r.ok) {
        if (!had || !had.error) { docs.set(l.path, { error: d.error }); changed = true; }
      } else if ('text' in d) {
        docs.set(l.path, { mtime: d.mtime, html: md.parse(d.text) });
        changed = true;
      }
    } catch {}
  }
  if (changed) render();
}

function docKey(w) {
  const d = docs.get(w.link.path);
  return w.link.path + ' ' + (d ? d.mtime || d.error : '');
}

function docCard(pic, w) {
  const old = pic.querySelector('.docwrap'), top = old ? old.scrollTop : 0;
  const inside = old && old.contains(document.activeElement);
  const d = docs.get(w.link.path);
  pic.className = 'pic card doc';
  pic.style.cssText = '';
  pic.innerHTML = `<div class="docwrap" tabindex="-1"><div class="md"></div></div>`;
  pic.querySelector('.md').innerHTML = !d ? '<p>Reading…</p>'
    : d.error ? `<p class="gone">${esc(w.link.path)}: ${esc(d.error)}</p>` : d.html;
  pic.querySelector('.docwrap').scrollTop = top;   // a save keeps your place
  if (inside) pic.querySelector('.docwrap').focus({ preventScroll: true });
}

const addDoc = (path, name) => { addCard({ path, title: name }); readDocs(); };

// a closed issue was finished, so it is purple; a closed PR was given up, so red
const ghColor = gh => ({ open: '#1f883d', merged: '#8250df', 'not planned': '#59636e',
                         closed: gh.pr ? '#cf222e' : '#8250df' })[gh.state] || '#59636e';
const ghStates = new Map();        // card url -> {state, pr}, asked of the server
const ghOf = w => w.link.url && ghStates.get(w.link.url);

async function askGitHub() {
  for (const l of links) {
    if (!/^https:\/\/github\.com\/[^/]+\/[^/]+\/(pull|issues)\/\d+/.test(l.url || '')) continue;
    try {
      const r = await fetch('/api/ghstate?url=' + encodeURIComponent(l.url));
      const st = await r.json();
      if (st) ghStates.set(l.url, st);
    } catch {}
  }
  render();
}

// what a card shows; it is drawn again only when this changes
function cardKey(w) {
  const gh = ghOf(w);
  return w.link.image ? w.link.image
    : w.link.path ? docKey(w) : w.link.url + (gh ? ' ' + gh.state : '');
}

const imgSrc = l => /^https?:/i.test(l.image) ? l.image : '/api/image?path=' + encodeURIComponent(l.image);

function imgCard(pic, w) {
  pic.className = 'pic card img';
  pic.style.cssText = '';
  pic.innerHTML = '<img alt="">';
  const img = pic.querySelector('img');
  img.onerror = () => { pic.innerHTML = `<div class="gone">${esc(w.link.image)}: cannot be shown</div>`; };
  // first sight of a picture sizes its tile to it, at most a screen across
  img.onload = () => {
    const l = w.link;
    if (l.w || !img.naturalWidth) return;
    const k = Math.min(1, 960 / img.naturalWidth, 720 / img.naturalHeight);
    l.w = Math.max(GRID * 3, snap(img.naturalWidth * k));
    l.h = Math.max(GRID * 2, snap(img.naturalHeight * k + CAP_H));
    store.set('links', links);
    w.w = l.w; w.h = l.h;
    render();
  };
  img.src = imgSrc(w.link);
}

const addImage = (image, title) => { addCard({ image, title }); render(); };

function card(pic, w) {
  if (w.link.image) return imgCard(pic, w);
  if (w.link.path) return docCard(pic, w);
  const u = new URL(w.link.url);
  pic.className = 'pic card';
  pic.style.cssText = '';
  pic.innerHTML = `<div class="ttl"><img alt=""><span></span></div><div class="url"></div>`;
  const img = pic.querySelector('img');
  img.onerror = () => img.remove();
  img.src = u.origin + '/favicon.ico';
  pic.querySelector('.ttl span').textContent = w.title;
  pic.querySelector('.url').textContent = u.host + u.pathname;
  const gh = ghOf(w);
  if (gh) {
    const b = document.createElement('span');
    b.className = 'gh';
    b.textContent = gh.state;
    b.style.background = ghColor(gh);
    pic.querySelector('.url').prepend(b);
  }
}

const addLink = (url, title) => { addCard({ url, title }); render(); };

// dropped in the middle of what you are looking at, so you see it arrive
function addCard(fields) {
  const l = { id: newId(), ...fields }, w = linkWin(l), [cx, cy] = viewCenter();
  links.push(l);
  store.set('links', links);
  layout[w.id] = clearSpot([cx - w.w / 2, cy - w.h / 2], w.id);
  saveLayout();
  // picked if the keyboard is the page's; a terminal you are typing in keeps it
  if (!inInsert()) sel = w.id;
  if (data) data.windows.push(w);
}

function closeLink(id) {
  links = links.filter(l => 'link:' + l.id !== id);
  store.set('links', links);
  delete layout[id];
  saveLayout();
  if (data) data.windows = data.windows.filter(w => w.id !== id);
  if (sel === id) sel = null;
  render();
}

// cut this window out of its workspace photo — percentages, so the photo's own
// pixel size never comes into it
function dress(pic, w) {
  const S = data.screen, c = w.crop, url = shotUrl(w.desktop);
  const x = c && Math.max(0, c[0]), y = c && Math.max(0, c[1]);
  const cw = c && Math.min(c[2], S.w - x), ch = c && Math.min(c[3], S.h - y);
  // nothing of this window was showing, so there is nothing honest to display
  const buried = w.seen !== undefined && w.seen < 0.08;
  if (!url || !cw || !ch || buried) {
    pic.className = 'pic none';
    pic.style.cssText = `background:${colorOf(w.app)}`;
    pic.textContent = buried ? 'was behind another window'
      : data.shots_on ? 'not photographed yet' : '';
    return;
  }
  pic.className = 'pic';
  pic.textContent = '';
  pic.style.cssText = `background-image:url("${url}");`
    + `background-size:${S.w / cw * 100}% ${S.h / ch * 100}%;`
    + `background-position:${S.w > cw ? x / (S.w - cw) * 100 : 0}% `
    + `${S.h > ch ? y / (S.h - ch) * 100 : 0}%`;
  (w.over || []).forEach(o => {
    const m = document.createElement('div');
    m.className = 'hid';
    m.style.cssText = `left:${o[0]}%;top:${o[1]}%;width:${o[2]}%;height:${o[3]}%`;
    pic.append(m);
  });
}

function place(el, w) {
  const [x, y] = seatOf(w);
  el.style.left = x * zoom + 'px';
  el.style.top = y * zoom + 'px';
  if (w.term) {
    // a terminal is drawn at its own size and scaled to match the surface, so
    // it cannot be given a floor the way a photograph can: the tile is exactly
    // as big as what is inside it
    const t = terms.get(w.term.session);
    // the caption is the one part left at screen size
    const cap = t && t.cap ? t.capH : 0;
    el.style.width = w.w * zoom + 'px';
    el.style.height = (w.h - cap) * zoom + cap + 'px';
    if (t && t.wrap) t.wrap.style.transform = `scale(${zoom})`;
    return;
  }
  el.style.width = Math.max(90, w.w * zoom) + 'px';
  el.style.height = Math.max(60, w.h * zoom) + 'px';
  const dw = w.link && w.link.path && el.querySelector('.docwrap');
  if (dw) {                          // the caption stays at screen size
    dw.style.width = w.w + 'px';
    dw.style.height = Math.max(0, Math.max(60, w.h * zoom) - CAP_H) / zoom + 'px';
    dw.style.transform = `scale(${zoom})`;
  }
}

// The grid is only there while a window is being moved or resized. It is a
// repeating background laid over the frame, lined up with the surface's origin.
function showGrid(on) {
  const g = $('#grid');
  g.classList.toggle('on', on);
  if (!on) return;
  const step = GRID * zoom;
  g.style.backgroundSize = `${step}px ${step}px`;
  // a dot sits in the middle of its cell, so shift half a cell to put it on the line
  g.style.backgroundPosition = `${origin[0] - step / 2}px ${origin[1] - step / 2}px`;
}
const snap = v => Math.round(v / GRID) * GRID;
// one grid line on in a direction; from a spot between lines, the next one that way
const stepTo = (v, dir) => dir > 0 ? (Math.floor(v / GRID) + 1) * GRID
                                   : (Math.ceil(v / GRID) - 1) * GRID;

function drag(e, w, el) {
  if (e.button || pointers.size > 1) return;   // a second finger means pinch
  e.preventDefault();
  const from = seatOf(w), had = layout[w.id], sx = e.clientX, sy = e.clientY;
  let moved = false;
  el.setPointerCapture(e.pointerId);
  const move = ev => {
    const dx = ev.clientX - sx, dy = ev.clientY - sy;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;   // still a click
    if (!moved) {
      moved = true;
      el.classList.add('dragging');
      showGrid(true);
      $('#tiles').append(el);          // the one you just touched belongs on top
      // moving an element in the document drops its pointer capture, and the
      // drag then only lasts while the pointer happens to stay over the tile —
      // which for a terminal, grabbed by a thin title bar, is no time at all
      try { el.setPointerCapture(ev.pointerId); } catch {}
    }
    layout[w.id] = [snap(from[0] + dx / zoom), snap(from[1] + dy / zoom)];
    place(el, w);
  };
  const done = settle => {
    off();
    el.classList.remove('dragging');
    showGrid(false);
    letGo = null;
    // a tile the pinch interrupted goes back where it was: the first finger
    // landing on it was the start of a zoom, not a move
    if (moved && !settle) {
      if (had) layout[w.id] = had; else delete layout[w.id];
      place(el, w);
    }
    if (moved) saveLayout();
    if (!settle) return;
    // a click on a terminal in NORMAL only picks it: Enter is what types into it
    const typing = inInsert();
    // a card only picks on a click: opening a page is a double click's worth
    if (moved || w.link || (w.term && !typing)) { sel = w.id; render(); } else activate(w.id);
  };
  const up = ev => {
    try { el.releasePointerCapture(ev.pointerId); } catch {}
    done(true);
  };
  letGo = () => done(false);       // put back if a pinch begins
  const off = follow(el, move, up);
}

// ---- terminals -----------------------------------------------------------
// A session lives in pty_server.py; what lives here is the emulator drawing it
// and the socket carrying bytes each way. Both are kept per session and reused
// across renders, so a poll never disturbs what you are typing into.

const terms = new Map();          // session id -> { term, ws, wrap, cap, natural }
// What a terminal looks like is yours to say, and you have already said it in
// ~/.Xresources: the server reads the plain XTerm class at startup and these
// are only what is used when it has nothing to go on.
const FALLBACK_COLS = 100, FALLBACK_ROWS = 30;
const look = () => (data && data.look) || {};
const termCols = () => look().cols || FALLBACK_COLS;
const termRows = () => look().rows || FALLBACK_ROWS;
// A prompt is whatever the shell says it is, and plenty of them are drawn out
// of a Nerd Font's private use area — a Powerline arrow in a font that has
// never heard of one is a blank. The browser falls back per glyph, so naming a
// symbol font after the workhorse fills those in without disturbing the
// metrics, which come from the first font only.
const FALLBACK_FONT = '"DejaVu Sans Mono","Liberation Mono"';
// whatever the font is, the symbol fonts come after it, never instead of it
const SYMBOLS = ',"PowerlineSymbols","Symbols Nerd Font",ui-monospace,monospace';
const termFont = (face = look().font) => (face ? `"${face}",` : '') + FALLBACK_FONT + SYMBOLS;
// the faces in ~/.Xresources a terminal can switch between, default first
const profiles = () => look().profiles || [];
const FALLBACK_THEME = { background: '#12110d', foreground: '#e9e7df', cursor: '#e0875c',
  black: '#2a2820', red: '#d76b5a', green: '#7fa84f', yellow: '#d0a33c',
  blue: '#6f9bc4', magenta: '#b07ec0', cyan: '#5fa8a0', white: '#d9d5c8' };
// a palette read from X is taken whole, not mixed with this one: half of one
// scheme and half of another is nobody's idea of a colour scheme
const termTheme = () => look().theme || FALLBACK_THEME;

function connect(t, id) {
  if (t.ws || !data.pty || !data.pty.on) return;
  const ws = new WebSocket(`ws://${location.hostname}:${data.pty.port}/attach/${id}`);
  ws.binaryType = 'arraybuffer';
  t.ws = ws;
  ws.onmessage = e => {
    // bytes are the terminal; text is the server talking about it, which the
    // window list already covers
    if (typeof e.data !== 'string') t.term.write(new Uint8Array(e.data));
  };
  ws.onclose = () => { if (t.ws === ws) t.ws = null; };
  ws.onerror = () => { if (t.ws === ws) t.ws = null; };
}

function mount(w) {
  const id = w.term.session;
  let t = terms.get(id);
  if (t) return t;
  const l = look();
  const term = new Terminal({
    cols: w.term.cols, rows: w.term.rows, theme: termTheme(),
    fontFamily: termFont(),
    fontSize: l.size || 13,
    // xterm.js clips each row to its cell, and a tight face like Pragmata
    // draws capitals above its own line box: at 1.0 the bar of a T is cut off
    lineHeight: 1.125,
    cursorBlink: l.blink === undefined ? true : l.blink,
    scrollback: l.scrollback || 4000,
    drawBoldTextInBrightColors: l.bold_bright === undefined ? true : l.bold_bright,
    convertEol: false, macOptionIsMeta: true,
  });
  t = { term, ws: null, wrap: null, cap: null, capH: 0, natural: null, cell: null, pad: [0, 0], read: false, title: '', prof: 0 };
  terms.set(id, t);
  // the title the shell sets (OSC 0/2) is what a desktop terminal shows, and
  // xterm.js hears it as it streams by, well before the next poll would
  term.onRender(() => termDrew(id));
  term.onTitleChange(s => {
    t.title = s;
    if (t.cap && s) t.cap.querySelector('.t2').textContent = s;
  });
  // what you type goes straight down the socket; nothing is echoed locally,
  // because the far end is what decides what a keystroke looks like
  term.onData(d => {
    if (t.ws && t.ws.readyState === 1) t.ws.send(utf8.encode(d));
  });
  // xterm.js sends a bare CR for Shift+Enter, same as Enter. Send ESC CR
  // instead, which is what Claude Code and readline take as "newline, don't
  // submit". keypress has to be swallowed too, or the CR goes out as well.
  term.attachCustomKeyEventHandler(e => {
    // Ctrl+Space hands the keyboard back to the page, like Esc out of vi's
    // insert mode — Esc itself belongs to whatever runs in the terminal
    if (e.code === 'Space' && e.ctrlKey && !e.altKey && !e.metaKey) {
      if (e.type === 'keydown') { term.blur(); sel = 'web:' + id; render(); }
      e.preventDefault();
      return false;
    }
    // Ctrl+Alt+F, the same keys as xterm-font on the desktop: the next face
    if (e.code === 'KeyF' && e.ctrlKey && e.altKey && !e.metaKey) {
      if (e.type === 'keydown') swapFace(id);
      e.preventDefault();
      return false;
    }
    if (e.key !== 'Enter' || !e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return true;
    if (e.type === 'keydown' && t.ws && t.ws.readyState === 1) t.ws.send(utf8.encode('\x1b\r'));
    e.preventDefault();
    return false;
  });
  return t;
}

// A new face keeps the count of characters and the tile grows or shrinks
// around it, the way an xterm window does when its font is changed under it.
function swapFace(id) {
  const t = terms.get(id), ps = profiles();
  if (!t || ps.length < 2) return;
  t.prof = (t.prof + 1) % ps.length;
  t.term.options.fontFamily = termFont(ps[t.prof].font);
  t.term.options.fontSize = ps[t.prof].size || 13;
  if (t.wrap) measure(t);
  render();
}

// xterm.js turns a mouse position into a cell with its own unscaled cell size,
// so on a terminal drawn at any zoom but 1:1 a click lands on the wrong row and
// column — further off the further from the corner. Each real mouse event meant
// for a terminal is caught first and sent on again with its position brought
// back to the terminal's own scale. A press keeps its terminal until let go, so
// a selection dragged out past the edge is still measured against it.
let mouseScreen = null;
['mousedown', 'mousemove', 'mouseup', 'click', 'dblclick', 'auxclick', 'contextmenu', 'wheel']
  .forEach(type => addEventListener(type, e => {
    if (!e.isTrusted) return;                  // ours, already put right
    const host = e.target.closest && e.target.closest('.termhost');
    const screen = (host && host.querySelector('.xterm-screen')) || mouseScreen;
    if (type === 'mousedown') mouseScreen = host ? screen : null;
    if (!screen || zoom === 1) {
      if (type === 'mouseup') mouseScreen = null;
      return;
    }
    const r = screen.getBoundingClientRect();
    const init = {
      bubbles: true, cancelable: true, composed: true, view: window, detail: e.detail,
      clientX: r.left + (e.clientX - r.left) / zoom, clientY: r.top + (e.clientY - r.top) / zoom,
      screenX: e.screenX, screenY: e.screenY, button: e.button, buttons: e.buttons,
      ctrlKey: e.ctrlKey, shiftKey: e.shiftKey, altKey: e.altKey, metaKey: e.metaKey,
      relatedTarget: e.relatedTarget,
    };
    const again = type === 'wheel'
      ? new WheelEvent(type, { ...init, deltaX: e.deltaX, deltaY: e.deltaY, deltaZ: e.deltaZ, deltaMode: e.deltaMode })
      : new MouseEvent(type, init);
    e.stopImmediatePropagation();
    if (!e.target.dispatchEvent(again)) e.preventDefault();
    if (type === 'mouseup') mouseScreen = null;
  }, { capture: true, passive: false }));

function dressTerm(el, w) {
  const t = mount(w), id = w.term.session;
  if (!t.wrap) {
    el.innerHTML = `<div class="cap"><span class="dot"></span><span class="t2"></span>` +
                   `<span class="note"></span>` +
                   `<span class="prof" title="Switch font (Ctrl+Alt+F)"></span>` +
                   `<span class="shut" title="Close">✕</span></div>` +
                   `<div class="termbody"><div class="termwrap"></div></div>`;
    const wrap = el.querySelector('.termwrap');
    const host = document.createElement('div');
    host.className = 'termhost';
    wrap.append(host);
    t.cap = el.querySelector('.cap');
    // the keyboard arriving here by any route (a click, a script) makes this
    // the picked window, so the outline never stays behind on the last one
    host.addEventListener('focusin', () => {
      if (sel !== 'web:' + id && inInsert()) activate('web:' + id);
    });
    // xterm measures a character by laying one out, so it has to do that at
    // its own size: the surface scale goes on afterwards, never before
    wrap.style.transform = 'none';
    t.term.open(host);
    t.wrap = wrap;
    // a finger has no wheel, so one dragged up or down the terminal is turned
    // into one: xterm.js then scrolls, or tells the program, exactly as it
    // would for the mouse. A second finger makes it a pinch again.
    host.addEventListener('pointerdown', e => {
      if (e.pointerType === 'mouse' || zoom <= 0.5 || pointers.size > 1) return;
      let py = e.clientY;
      const move = ev => {
        if (ev.pointerId !== e.pointerId) return;
        const dy = (py - ev.clientY) / zoom;
        py = ev.clientY;
        if (dy) t.term.element.dispatchEvent(new WheelEvent('wheel',
          { deltaY: dy, deltaMode: 0, bubbles: true, cancelable: true }));
      };
      const done = ev => {
        if (ev && ev.pointerId !== e.pointerId) return;
        off();
        if (letGo === done) letGo = null;
      };
      if (letGo) letGo();
      letGo = done;
      const off = follow(window, move, done);
    });
    measure(t);
    const grip = document.createElement('div');
    grip.className = 'grip';
    grip.title = 'Drag to resize this terminal';
    el.append(grip);                  // outside the scaled wrap: a handle you
  }                                   // can still grab when zoomed out
  // measured again each time, not just at mount: the face can settle after
  // xterm.js first lays out, and a stale size cuts off the bottom row. Not
  // mid-resize, though, where the corner is what decides the size
  if (!el.querySelector('.termsize')) measure(t);
  if (t.natural) { w.w = t.natural[0]; w.h = t.natural[1]; }
  const cap = t.cap;
  cap.querySelector('.dot').style.background = colorOf(w.app);
  cap.querySelector('.prof').textContent = (profiles()[t.prof] || {}).name || '';
  cap.querySelector('.t2').textContent = t.title || w.term.title || w.term.running || w.title;
  cap.querySelector('.note').textContent = w.term.alive
    ? (w.term.cwd || '')
    : 'exited ' + (w.term.exit === null ? '?' : w.term.exit);
  el.classList.toggle('gone', !w.term.alive);
  // a running session is reconnected whenever its socket has dropped; one that
  // has ended is closed, the way a terminal window goes when its shell exits
  if (w.term.alive) connect(t, id);
  else if (!t.closing) { t.closing = true; closeTerm(id); }
}

// What one character costs, worked out from what xterm.js actually laid out
// rather than from anything we told it: the font decides, and it is the only
// one that knows. Everything about a terminal's size follows from this.
function measure(t) {
  const host = t.wrap.querySelector('.termhost');
  const screen = host.querySelector('.xterm-screen') || host;
  // taken unscaled, and to the fraction: offsetHeight rounds the title bar's
  // part-pixel down, and the tile then shaves that much off the bottom row
  const was = t.wrap.style.transform;
  t.wrap.style.transform = 'none';
  const wide = host.offsetWidth || screen.offsetWidth;
  // the caption is outside the scaled part, but still counted in the tile
  t.capH = t.cap.getBoundingClientRect().height;
  const high = t.wrap.getBoundingClientRect().height + t.capH;
  t.wrap.style.transform = was;
  // the title bar and xterm's own padding are there whatever the size, so they
  // are held apart from the grid of characters rather than averaged into it
  t.pad = [Math.max(0, wide - screen.offsetWidth),
           Math.max(0, high - screen.offsetHeight)];
  t.cell = [screen.offsetWidth / t.term.cols, screen.offsetHeight / t.term.rows];
  t.natural = [Math.ceil(wide), Math.ceil(high)];
}

// how big a tile has to be to hold this many characters
function span(t, cols, rows) {
  return [Math.round(cols * t.cell[0] + t.pad[0]),
          Math.round(rows * t.cell[1] + t.pad[1])];
}

// Pulling the corner is the same gesture as dragging the tile, so it is the
// same shape of code: the terminal is resized as you go, and the far end is
// told each time the count actually changes — which is what a real terminal
// does, and why a full-screen program redraws while you are still pulling.
function resizeTo(w, el, t, edge) {
  const [x, y] = seatOf(w);
  // an unmoved terminal sits wherever the others' sizes leave room, so resizing
  // one would carry its neighbours off (and a reload would not put them back):
  // pin it where it is the first time it changes size
  if (!layout[w.id]) { layout[w.id] = [x, y]; saveLayout(); }
  const cols = Math.max(20, Math.round((edge[0] - x - t.pad[0]) / t.cell[0]));
  const rows = Math.max(5, Math.round((edge[1] - y - t.pad[1]) / t.cell[1]));
  if (cols === t.term.cols && rows === t.term.rows) return false;
  t.term.resize(cols, rows);
  t.natural = span(t, cols, rows);
  w.w = t.natural[0];
  w.h = t.natural[1];
  place(el, w);
  if (t.ws && t.ws.readyState === 1) {
    t.ws.send(JSON.stringify({ resize: { cols, rows } }));
  }
  return true;
}

function grab(e, w, el) {
  if (e.button || pointers.size > 1) return;   // a second finger means pinch
  e.preventDefault();
  e.stopPropagation();
  const t = terms.get(w.term.session);
  if (!t || !t.cell) return;
  const sx = e.clientX, sy = e.clientY;
  // the size it had when grabbed: resizeTo changes w.w and w.h as you pull
  const w0 = w.w, h0 = w.h;
  const tag = document.createElement('div');
  tag.className = 'termsize';
  el.append(tag);
  const show = () => { tag.textContent = `${t.term.cols}×${t.term.rows}`; };
  show();
  showGrid(true);
  el.setPointerCapture(e.pointerId);
  const move = ev => {
    // the far corner lands on the nearest grid line, give or take half a character
    const [x, y] = seatOf(w);
    const edge = [snap(x + w0 + (ev.clientX - sx) / zoom), snap(y + h0 + (ev.clientY - sy) / zoom)];
    if (resizeTo(w, el, t, edge)) show();
  };
  const off = follow(el, move, ev => {
    try { el.releasePointerCapture(ev.pointerId); } catch {}
    off();
    tag.remove();
    showGrid(false);
    measure(t);                      // what it settled at, measured not assumed
    poll();
  });
}

// A card is resized the same way, with no characters to count: the far corner
// lands on the nearest grid line, and the size is kept with the link.
function grabLink(e, w, el) {
  if (e.button || pointers.size > 1) return;   // a second finger means pinch
  e.preventDefault();
  e.stopPropagation();
  const sx = e.clientX, sy = e.clientY, w0 = w.w, h0 = w.h;
  const [x, y] = seatOf(w);
  if (!layout[w.id]) { layout[w.id] = [x, y]; saveLayout(); }
  showGrid(true);
  el.setPointerCapture(e.pointerId);
  const move = ev => {
    w.w = Math.max(90, snap(w0 + (ev.clientX - sx) / zoom));
    w.h = Math.max(60, snap(h0 + (ev.clientY - sy) / zoom));
    place(el, w);
  };
  const off = follow(el, move, ev => {
    try { el.releasePointerCapture(ev.pointerId); } catch {}
    off();
    showGrid(false);
    const l = links.find(v => 'link:' + v.id === w.id);
    if (l) { l.w = w.w; l.h = w.h; store.set('links', links); }
  });
}

// A new tile that lands on another's corner hides it, and you cannot tell
// anything opened: step it down and right, as a desktop does, until its corner
// is clear. Only new tiles go through this, never ones that are already placed.
function clearSpot([x, y], exceptId) {
  const taken = () => data.windows.some(v => {
    if (v.id === exceptId) return false;
    const [a, b] = seatOf(v);
    return Math.abs(a - x) < GRID && Math.abs(b - y) < GRID;
  });
  x = snap(x); y = snap(y);
  for (let n = 0; n < 100 && taken(); n++) { x += 2 * GRID; y += 2 * GRID; }
  return [x, y];
}

// A new terminal opens in the middle of whatever you are looking at, and the
// view stays where it is: you zoomed in there to work there.
async function newTerm() {
  const at = viewCenter();
  const made = await fetch('/api/terminals', {
    method: 'POST',
    body: JSON.stringify({ cols: termCols(), rows: termRows() }),
  }).then(r => r.json()).catch(() => null);
  if (!made || !made.id) return;
  // the new one is picked and brought to the front, but you stay in NORMAL:
  // Enter is what types into it, as with any other terminal
  const pickIt = () => {
    sel = 'web:' + made.id;
    const el = tileEls.get(sel);
    if (el) $('#tiles').append(el);
    render();
  };
  if (!zoom) {
    await poll();
    const v = data.windows.find(v => v.id === 'web:' + made.id);
    if (v) { layout[v.id] = clearSpot(seatOf(v), v.id); saveLayout(); }
    return pickIt();
  }
  await poll();                  // its size is only known once it is listed
  const w = data.windows.find(v => v.id === 'web:' + made.id);
  if (!w) return;
  layout[w.id] = clearSpot([at[0] - w.w / 2, at[1] - w.h / 2], w.id);
  saveLayout();
  pickIt();
}
$('#newterm').onclick = newTerm;

async function closeTerm(id) {
  await fetch('/api/terminals/' + id, { method: 'DELETE' }).catch(() => {});
  const t = terms.get(id);
  if (t && t.ws) t.ws.close();
  poll();
}

function renderCanvas(match) {
  if (!zoom) fitAll();                 // the first time only: after that the view is yours
  $('#zoom').value = Math.round(Math.sqrt(zoom / MAX_ZOOM) * 100);
  $('#canvas').style.transform = `translate(${origin[0]}px,${origin[1]}px)`;
  markEdges();

  const live = new Set();
  data.windows.slice().sort((a, b) => a.z - b.z).forEach(w => {
    live.add(w.id);
    let el = tileEls.get(w.id);
    if (!el) {
      el = document.createElement('div');
      if (!w.term) {
        el.innerHTML = `<div class="cap"><span class="dot"></span><span class="t2"></span>`
          + (w.link ? `<span class="shut" title="Remove">✕</span>` : '') + `</div>`;
        el.append(document.createElement('div'));
        if (w.link) {
          const grip = document.createElement('div');
          grip.className = 'grip';
          grip.title = 'Drag to resize this card';
          el.append(grip);
        }
      }
      el.addEventListener('pointerdown', e => {
        const win = tileEls.get(w.id).win;
        if (e.target.closest('.md a')) return;    // a link in a document is for following
        if (win.term) {
          // the drag takes the pointer captive, and a captured pointer's click
          // is delivered to the tile rather than to what was under it — so the
          // close button has to be answered here, before any of that
          if (e.target.closest('.shut')) { e.preventDefault(); return closeTerm(win.term.session); }
          if (e.target.closest('.prof')) { e.preventDefault(); return swapFace(win.term.session); }
          if (e.target.closest('.grip')) return grab(e, win, el);
          // a terminal is for typing into, so only its caption is a handle;
          // a photograph has nothing to click, so all of it is
          // — except in NORMAL, where the mouse moves windows and never types
          if (inInsert() && !e.target.closest('.cap')) return;
        } else if (win.link && e.target.closest('.grip')) {
          return grabLink(e, win, el);
        } else if (win.link && e.target.closest('.shut')) {
          e.preventDefault();
          return closeLink(win.id);
        } else if (inInsert()) {
          return;                // in INSERT a photograph is just more surface: it pans
        }
        drag(e, win, el);
      });
      if (w.link) el.addEventListener('dblclick', e => {
        if (!e.target.closest('.shut, .grip')) activate(w.id);
      });
      tileEls.set(w.id, el);
      $('#tiles').append(el);
    }
    el.win = w;                       // the drag handler always wants the fresh one
    el.className = 'tile' + (w.term ? ' term' : '') + (w.link ? ' link' : '') + (w.focused ? ' focused' : '')
      + (match(w) ? '' : ' off') + (w.id === sel ? ' sel' : '');
    if (w.term) {
      el.title = `${w.title} · pid ${w.pid}`;
      dressTerm(el, w);
    } else {
      el.title = `${w.app} — ${w.title} · workspace ${w.desktop + 1}`;
      el.querySelector('.dot').style.background = colorOf(w.app);
      el.querySelector('.t2').textContent = w.title;
      if (w.link) {
        el.title = w.link.url || w.link.path || w.link.image;
        const gh = ghOf(w), key = cardKey(w);
        if (gh) el.querySelector('.dot').style.background = ghColor(gh);
        const pic = el.children[1];          // the grip comes after it
        if (pic.dataset.key !== key) {
          card(pic, w);
          pic.dataset.key = key;
        }
      } else dress(el.lastElementChild, w);
    }
    place(el, w);
  });
  tileEls.forEach((el, id) => {
    if (live.has(id)) return;
    el.remove();
    tileEls.delete(id);
    const t = terms.get(id.slice(4));         // a session that has gone for good
    if (id.startsWith('web:') && t) {
      if (t.ws) t.ws.close();
      t.term.dispose();
      terms.delete(id.slice(4));
    }
  });
}

// ---- the loupe: the surface under the pointer at 1:1 ----------------------
// A second copy of the surface at its own size: a photograph cut the same way,
// a terminal as a copy of its rows. It is laid out when the surface is, and
// following the pointer only slides it, so a move costs no layout at all.

let lensOn = store.get('lens', true), lensAt = null, lensFrame = 0;
const lensEls = new Map();        // window id -> its copy in the loupe
const lensDirty = new Set();      // terminals whose rows changed since copied

function setLens(v) {
  lensOn = v;
  store.set('lens', v);
  $('#lens').setAttribute('aria-pressed', v);
  syncLens();
  aimLens();
}
$('#lens').onclick = () => setLens(!lensOn);

// called from render(): tiles come, go and move, and the copy follows
function syncLens() {
  if (!lensOn || !data) return;
  const lens = $('#loupe .lens'), match = visible(), live = new Set();
  data.windows.slice().sort((a, b) => a.z - b.z).forEach(w => {
    live.add(w.id);
    let el = lensEls.get(w.id);
    if (!el) {
      el = document.createElement('div');
      el.append(document.createElement('div'));
      lensEls.set(w.id, el);
      if (w.term) lensDirty.add(w.term.session);
    }
    lens.append(el);                  // in stacking order, cheap when already there
    const [x, y] = seatOf(w);
    el.style.cssText = `left:${x}px;top:${y}px;width:${w.w}px;height:${w.h}px`
      + (w.term ? ';background:#12110d' : '') + (match(w) ? '' : ';opacity:.3');
    el.win = w;
    if (w.term) return;
    if (w.link) {
      const key = cardKey(w);
      if (el.key !== key) { el.key = key; card(el.firstChild, w); }
      return;
    }
    // a photograph only needs cutting again when the cut changes
    const key = shotUrl(w.desktop) + JSON.stringify([w.crop, w.over, w.seen, w.w, w.h]);
    if (el.key !== key) { el.key = key; dress(el.firstChild, w); }
  });
  lensEls.forEach((el, id) => { if (!live.has(id)) { el.remove(); lensEls.delete(id); } });
}

// a terminal that has redrawn: copy its rows over, if the loupe can see it
function termDrew(id) {
  lensDirty.add(id);
  if (lensOn && lensAt && !lensFrame) lensFrame = requestAnimationFrame(drawLens);
}

function drawLens() {
  lensFrame = 0;
  const loupe = $('#loupe'), lens = loupe.querySelector('.lens');
  loupe.classList.toggle('on', !!(lensOn && lensAt && data));
  if (!loupe.classList.contains('on')) return;
  const box = $('#pan').getBoundingClientRect();
  // out of its own way: under the pointer, it moves to the other corner
  const r = loupe.getBoundingClientRect();
  if (lensAt[0] >= r.left && lensAt[0] <= r.right && lensAt[1] >= r.top && lensAt[1] <= r.bottom)
    loupe.classList.toggle('right');
  const W = loupe.clientWidth, H = loupe.clientHeight;
  const x0 = (lensAt[0] - box.left - origin[0]) / zoom - W / 2;
  const y0 = (lensAt[1] - box.top - origin[1]) / zoom - H / 2;
  lens.style.transform = `translate(${Math.round(-x0)}px,${Math.round(-y0)}px)`;
  // only the terminals in view are copied, and only once per redraw
  lensDirty.forEach(id => {
    const el = lensEls.get('web:' + id), w = el && el.win;
    if (!w) return lensDirty.delete(id);
    const [x, y] = seatOf(w);
    if (x > x0 + W || y > y0 + H || x + w.w < x0 || y + w.h < y0) return;
    const t = terms.get(id), xt = t && t.wrap && t.wrap.querySelector('.xterm');
    if (!xt) return;
    lensDirty.delete(id);
    // the caption stays at screen size on the surface too, so it is the same
    // height here; below it, the rows at their own size. The shell keeps the
    // .xterm classes, which is what xterm.js hangs its colours on
    const shell = document.createElement('div');
    shell.className = xt.className;
    shell.style.marginTop = t.capH + 'px';
    shell.append(xt.querySelector('.xterm-screen').cloneNode(true));
    el.replaceChildren(shell);
  });
}

function aimLens(e) {
  if (e) lensAt = [e.clientX, e.clientY];
  if (lensOn && !lensFrame) lensFrame = requestAnimationFrame(drawLens);
  else if (!lensOn) drawLens();
}
$('#pan').addEventListener('pointermove', aimLens);
$('#pan').addEventListener('wheel', aimLens);
$('#pan').addEventListener('pointerleave', () => { lensAt = null; drawLens(); });

// ---- getting about: wheel, drag, and two fingers -------------------------

let letGo = null;   // how to call off whatever single-pointer gesture is running

$('#pan').addEventListener('wheel', e => {
  // A terminal has a scrollback of its own, and once it is big enough to read
  // it is a terminal rather than a tile: the wheel belongs to it. Zoomed out
  // far enough that nobody could read it, it is a tile again and the wheel
  // goes back to meaning zoom.
  if (zoom > 0.5 && e.target.closest('.termhost') && inInsert()) return;
  if (zoom > 0.3 && e.target.closest('.docwrap')) return;      // a document scrolls
  e.preventDefault();
  zoomAbout(zoom * Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY);
}, { passive: false });

// One pointer anywhere on the background carries the whole surface with it.
// This listens on the frame rather than on the canvas: the canvas is a 0x0
// element that its tiles simply overflow, so it has no background of its own
// to press — the empty space you are reaching for belongs to the frame.
// In INSERT the pointer outside the window you are typing into still carries
// the surface — the wheel already zooms there — while the active window and
// the other terminals keep their clicks, and a photograph is only surface.
function carries(e) {
  const tile = e.target.closest('.tile');
  if (!tile || !inInsert()) return !tile;
  return !tile.classList.contains('term') && tile !== document.activeElement.closest('.tile');
}

// A press anywhere but the window you are typing into lets go of the keyboard,
// back to NORMAL, and then counts as a NORMAL press: the background pans, a
// window is picked or dragged. Its mousedown is held back, so a terminal you
// pressed on cannot take the keyboard straight back.
$('#pan').addEventListener('pointerdown', e => {
  if (!inInsert()) return;
  const tile = e.target.closest('.tile');
  const here = document.activeElement || document.body;
  if (tile && tile === here.closest('.tile')) return;
  e.preventDefault();
  here.blur();
  showMode();                        // now, not after focusout's tick: the tile's
}, true);                            // own handler below has to see NORMAL

$('#pan').addEventListener('pointerdown', e => {
  if (!carries(e) || pointers.size > 1) return;   // one finger drags, two pinch
  const pan = $('#pan');
  let px = e.clientX, py = e.clientY;
  pan.classList.add('grabbing');
  const move = ev => { shift(ev.clientX - px, ev.clientY - py); px = ev.clientX; py = ev.clientY; };
  const done = () => {
    pan.classList.remove('grabbing');
    off();
    letGo = null;
  };
  letGo = done;
  const off = follow(window, move, done);
});

// two fingers pinch to zoom and slide to pan, the pair working as one gesture
const pointers = new Map();
let pinch = null;

function pair() {
  const [a, b] = [...pointers.values()];
  return { gap: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

$('#pan').addEventListener('pointerdown', e => {
  if (e.pointerType === 'mouse') return;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 2) {
    if (letGo) letGo();            // a second finger means pinch, not drag
    const p = pair();
    pinch = { gap: p.gap, from: zoom, x: p.x, y: p.y };
  }
}, true);

$('#pan').addEventListener('pointermove', e => {
  if (!pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size !== 2 || !pinch) return;
  e.preventDefault();
  const now = pair();
  shift(now.x - pinch.x, now.y - pinch.y);
  pinch.x = now.x;
  pinch.y = now.y;
  // measured against where the fingers started, so the zoom cannot drift
  if (pinch.gap > 24) zoomAbout(pinch.from * (now.gap / pinch.gap), now.x, now.y);
}, true);

function liftFinger(e) {
  pointers.delete(e.pointerId);
  if (pointers.size < 2) pinch = null;
}
addEventListener('pointerup', liftFinger, true);
addEventListener('pointercancel', liftFinger, true);

async function activate(id) {
  sel = id;
  const el = tileEls.get(id);
  if (el) $('#tiles').append(el);      // focusing it brings it to the front, as a drag does
  render();
  if (id.startsWith('link:')) {
    const w = data.windows.find(x => x.id === id);
    const dw = w && w.link.path && tileEls.get(id) && tileEls.get(id).querySelector('.docwrap');
    if (dw) dw.focus({ preventScroll: true });        // into the document: INSERT
    else if (w && w.link.url) window.open(w.link.url, '_blank', 'noopener');
    else if (w && w.link.image) window.open(imgSrc(w.link), '_blank', 'noopener');
    return;
  }
  if (id.startsWith('web:')) {
    // this one is already in front of you; focusing it means the keyboard
    const t = terms.get(id.slice(4));
    if (t) t.term.focus();
    return;
  }
  try { await fetch('/api/focus', { method: 'POST', body: JSON.stringify({ id }) }); }
  catch {}
  poll();
}

// ---- keyboard picking -----------------------------------------------------
function selected() {
  if (!data) return null;
  return data.windows.find(w => w.id === sel) || null;
}

function reveal() {
  if (!sel) return;
  const w = data.windows.find(x => x.id === sel);
  const pan = $('#pan');
  if (!w || !pan.clientWidth) return;
  const [x, y] = seatOf(w);                       // bring the pick to the middle
  origin = [pan.clientWidth / 2 - (x + w.w / 2) * zoom,
            pan.clientHeight / 2 - (y + w.h / 2) * zoom];
  store.set('origin', origin);
  $('#canvas').style.transform = `translate(${origin[0]}px,${origin[1]}px)`;
  markEdges();
}

function move(dx, dy) {
  const match = visible();
  const pick = data.windows.filter(match);
  if (!pick.length) return;
  const cur = selected();
  if (!cur) { sel = pick[0].id; return (render(), reveal()); }

  if (dy && !dx) {                       // within a workspace, then on to the next one
    const here = ordered(cur.desktop).filter(match);
    const at = here.findIndex(w => w.id === cur.id);
    if (at + dy >= 0 && at + dy < here.length) { sel = here[at + dy].id; return (render(), reveal()); }
  }
  // the desktop's own grid is not what is on screen — the seating plan is, and
  // it has a cell for the terminals, which no workspace layout would ever hold
  const p = plan(), cells = [...p.at.keys()], n = cells.length;
  let i = Math.max(0, cells.indexOf(cur.desktop));
  for (let step = 0; step < n; step++) {
    i += dx + dy * p.cols;
    if (i < 0) i += n;
    if (i >= n) i -= n;
    const there = ordered(cells[i]).filter(match);
    if (there.length) { sel = there[dy > 0 ? 0 : there.length - 1].id; return (render(), reveal()); }
  }
}

// Two modes, as in vi: NORMAL, where the keys move about the surface, and
// INSERT, where a terminal has them all. Which one you are in is just where
// the keyboard is, so it is read from the focus rather than kept alongside it.
function showMode() {
  const typing = !!(document.activeElement && document.activeElement.closest('.termhost, .docwrap'));
  $('#mode').textContent = editing ? editing.toUpperCase() : typing ? 'INSERT' : 'NORMAL';
  $('#mode').classList.toggle('insert', typing && !editing);
  document.body.classList.toggle('insert', typing);
  $('#mode').classList.toggle('grid', !!editing);
}

// Moving and resizing from the keyboard are modes of their own inside NORMAL:
// hjkl step the picked window one grid cell, Enter or Esc leaves. Only a
// terminal has a size to change, so r does nothing on a photograph.
let editing = null;       // 'move' | 'resize' | null
function edit(how) {
  const w = selected();
  const t = w && w.term && terms.get(w.term.session);
  if (!w || (how === 'resize' && !(t && t.cell && w.term.alive))) return;
  editing = how;
  showGrid(true);
  showMode();
}
function endEdit() {
  editing = null;
  showGrid(false);
  saveLayout();
  showMode();
  poll();
}
function nudge(dx, dy) {
  const w = selected(), el = w && tileEls.get(w.id);
  if (!el) return endEdit();
  const [x, y] = seatOf(w);
  if (editing === 'move') {
    layout[w.id] = [dx ? stepTo(x, dx) : snap(x), dy ? stepTo(y, dy) : snap(y)];
    place(el, w);
    return;
  }
  const t = terms.get(w.term.session);
  if (!t) return endEdit();
  // the edge sits half a character either side of a grid line, so the next
  // line can be too close to change the count: keep going until it does
  let edge = [x + w.w, y + w.h];
  for (let i = 0; i < 8; i++) {
    edge = [dx ? stepTo(edge[0], dx) : edge[0], dy ? stepTo(edge[1], dy) : edge[1]];
    if (resizeTo(w, el, t, edge)) break;
  }
}
document.addEventListener('focusin', showMode);
document.addEventListener('focusout', () => setTimeout(showMode));
showMode();

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'TEXTAREA') return;   // a terminal has the keyboard
  const doc = e.target.closest && e.target.closest('.docwrap');
  if (doc) {                         // a document has it: it scrolls, Esc leaves
    if (e.key === 'Escape' || (e.code === 'Space' && e.ctrlKey)) { e.preventDefault(); doc.blur(); return; }
    const by = { j: 40, k: -40, d: doc.clientHeight / 2, u: -doc.clientHeight / 2 }[e.key];
    if (by && !e.ctrlKey && !e.altKey && !e.metaKey) { e.preventDefault(); doc.scrollBy(0, by); }
    return;                          // arrows, PgUp/PgDn and Space scroll on their own
  }
  if (e.target.tagName === 'INPUT') {
    if (e.key === 'Escape') { e.target.value = ''; e.target.blur(); sel = null; render(); }
    return;
  }
  const k = e.key;
  if (helpbox.open) {
    if (e.key === '?') { e.preventDefault(); helpbox.close(); }
    return;
  }
  if (archbox.open) return;
  if (editing) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    e.preventDefault();
    if (k === 'Escape' || k === 'Enter') return endEdit();
    const step = { ArrowUp: [0, -1], k: [0, -1], ArrowDown: [0, 1], j: [0, 1],
                   ArrowLeft: [-1, 0], h: [-1, 0], ArrowRight: [1, 0], l: [1, 0] }[k];
    if (step) nudge(...step);
    return;
  }
  // the page's own keys are bare letters: anything held with them is the browser's
  if (e.ctrlKey || e.altKey || e.metaKey) return;              // the dialog handles its own Esc
  if (k === 'a') { e.preventDefault(); return showArch(); }
  if (k === '?') { e.preventDefault(); return showHelp(); }
  if (k === '/') { e.preventDefault(); if (bare) setBare(false); $('#q').focus(); return; }
  if (k === 'Escape') {
    if ($('#q').value || sel) { $('#q').value = ''; sel = null; return render(); }
    return bare ? undefined : setBare(true);
  }
  if (k === 'm' || k === 'r') { e.preventDefault(); return edit(k === 'm' ? 'move' : 'resize'); }
  if (k === 'b') { e.preventDefault(); return setBare(!bare); }
  if (k === 't') { e.preventDefault(); return void newTerm(); }
  if (k === 'u') { e.preventDefault(); return askLink(); }
  if (k === 'o') { e.preventDefault(); return askDoc(); }
  if (k === 'p') { e.preventDefault(); return askImage(); }
  if (k === 'g') { e.preventDefault(); return newGroup(); }
  if (k === '1') { e.preventDefault(); return actualSize(); }
  if (k === 'z') { e.preventDefault(); return setLens(!lensOn); }
  if (k === 'Enter' || k === ' ') { const w = selected(); if (w) { e.preventDefault(); activate(w.id); } return; }
  const moves = { ArrowUp: [0, -1], k: [0, -1], ArrowDown: [0, 1], j: [0, 1],
                  ArrowLeft: [-1, 0], h: [-1, 0], ArrowRight: [1, 0], l: [1, 0] };
  if (moves[k]) { e.preventDefault(); move(...moves[k]); }
});

setBare(bare);
setLens(lensOn);
render();
poll();
setInterval(poll, 2000);
askGitHub();
setInterval(askGitHub, 60000);
readDocs();
setInterval(readDocs, 2000);
