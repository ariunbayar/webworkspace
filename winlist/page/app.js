const COLORS = { "Google Chrome":"#4285f4", "Claude Code":"#c96442", "Vim":"#019833",
  "Neovim":"#019833", "Viber":"#7360f2", "Firefox":"#ff7139", "memmon":"#7a5cd6",
  "Terminal":"#5a5852", "VS Code":"#0078d4", "Files":"#77767b", "Slack":"#4a154b" };
const PALETTE = ["#2f7d8c","#a8642b","#7a5cd6","#3f7d3f","#94566f","#736b5e"];
// an app not named above gets a colour from its name, so it keeps it across reloads
const colorOf = a => COLORS[a] || (COLORS[a] = PALETTE[[...String(a)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % PALETTE.length]);
const SHELL_NAMES = new Set(['bash', 'sh', 'zsh', 'fish', 'dash', 'tmux', 'screen']);
const baseName = p => String(p).split(/[?#]/)[0].replace(/\/+$/, '').split('/').pop() || String(p);
const shortPath = p => String(p || '').replace(/^\/home\/[^/]+/, '~').replace(/^(~\/|\/)(?:[^/]+\/){2,}([^/]+\/[^/]+)$/, '$1…/$2');
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
// a zoom kept from before snapping near 1:1 existed is snapped now: see zoomAbout
if (zoom && zoom !== 1 && Math.abs(zoom - 1) <= 0.1) zoom = 1;
let origin = store.get('origin', [0, 0]);  // where the surface sits in the frame
// The cards on the board live on the server, so every browser shows the same
// board: where one sits and how big it is go back to it.
let links = [];
const pend = new Map();      // card id -> {card, seq, doneAt}: told the server, not yet seen back
const knownAt = new Map();   // card id -> 'x,y' the server last had
let editSeq = 0;
function sendCard(l, fields) {             // fields that changed; null takes it off the board
  const seq = ++editSeq;
  pend.set(l.id, { card: fields && l, seq, doneAt: 0 });
  fetch('/api/links/' + encodeURIComponent(l.id),
        fields ? { method: 'PATCH', body: JSON.stringify(fields) } : { method: 'DELETE' })
    .catch(() => {})
    .finally(() => { const p = pend.get(l.id); if (p && p.seq === seq) p.doneAt = Date.now(); });
}
// Groups, where the windows' tiles sit and how much their photos are scaled
// live on the server too. A save waits a moment, since a drag saves often, and
// a poll never undoes what this page has sent and not yet seen back.
let arrangeKnown = false;    // the first poll has said whether the server has one
let arrangeAt = '';          // what the server last had
let arrangeTimer = 0, arrangeBusy = 0, arrangeDone = 0;
const arrangeNow = () => JSON.stringify({ groups,   // the server's key order, so an echo compares equal
  layout: Object.fromEntries(Object.entries(layout).filter(([k]) => !k.startsWith('link:'))), scales });
const arrangeOf = a => JSON.stringify({ groups: a.groups, layout: a.layout, scales: a.scales });
// the browser's own copy goes to one backup key, not away, in case the server's is wrong
function backupLocal() {
  const had = Object.fromEntries(['groups', 'layout', 'scales'].map(k => [k, store.get(k, null)]).filter(([, v]) => v));
  if (!Object.keys(had).length) return;
  if (!store.get('arrangement.backup', null)) store.set('arrangement.backup', { ...had, at: new Date().toISOString() });
  Object.keys(had).forEach(k => { try { localStorage.removeItem('winlist.' + k); } catch {} });
}
function saveArrange() {
  if (!arrangeKnown) return;           // not yet known whether the server's wins
  clearTimeout(arrangeTimer);
  arrangeTimer = setTimeout(sendArrange, 400);
}
async function sendArrange() {
  arrangeTimer = 0;
  const body = arrangeNow();
  arrangeBusy++;
  try {
    const r = await fetch('/api/arrangement', { method: 'PUT', body });
    if (r.ok) {
      arrangeAt = body;
      backupLocal();
    }
  } catch {}
  arrangeBusy--;
  arrangeDone = Date.now();
}
// what the server holds, unless this page has a change of its own on the way,
// is under the pointer, or is being typed into
function takeArrange(a, asked) {
  if (!arrangeKnown) {
    arrangeKnown = true;
    if (!a) {                          // none yet: this browser's is the first, if it has one
      if (groups.length || Object.keys(scales).length || Object.keys(layout).some(k => !k.startsWith('link:'))) return sendArrange();
      return;
    }
  } else if (!a || arrangeTimer || arrangeBusy || arrangeDone >= asked
             || document.querySelector('.dragging') || document.activeElement?.isContentEditable) return;
  if (arrangeOf(a) === arrangeAt) return;
  arrangeAt = arrangeOf(a);
  groups = a.groups;
  scales = a.scales;
  const cards = Object.entries(layout).filter(([k]) => k.startsWith('link:'));
  layout = { ...a.layout, ...Object.fromEntries(cards) };
  backupLocal();
}
const saveLayout = () => {
  saveArrange();
  for (const l of links) {
    const at = layout['link:' + l.id];
    if (!at || (at[0] === l.x && at[1] === l.y)) continue;
    [l.x, l.y] = at;
    knownAt.set(l.id, at + '');
    sendCard(l, { x: l.x, y: l.y });
  }
};
let toastTimer = 0;
function toast(html, ms = 2600) {
  const t = $('#toast');
  t.innerHTML = html;
  t.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('on'), ms);
}

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
// zoomed out to a quarter or less a cell is a few screen px, too fine to step
// across with the keyboard, so the grid doubles there
const gridStep = () => zoom <= 0.25 ? GRID * 2 : GRID;
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
    const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ from: 'page', url }) });
    const l = await r.json();
    if (r.ok) addCard(l);
  } catch {}
});

// p asks for a picture: a file on this machine or an image on the web
const imgbox = $('#imgbox');
function askImage(msg) {
  if (imgbox.open) return;
  $('#imgsrc').value = '';
  $('#imgsrc').placeholder = msg || 'Path to an image, or an image URL';
  if (msg) toast(esc(msg), 4000);     // a placeholder is faint, and gone at the first key
  imgbox.returnValue = '';
  imgbox.showModal();
  $('#imgsrc').focus();
}
imgbox.addEventListener('close', async () => {
  const image = $('#imgsrc').value.trim();
  if (imgbox.returnValue !== 'add' || !image) return;
  try {
    const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ from: 'page', image }) });
    const l = await r.json();
    if (!r.ok) return askImage('Could not open it: ' + (l.error || 'unknown error'));
    addCard(l);
  } catch {}
});
// o asks for a text file; the server checks it is one before it is shown
const docbox = $('#docbox'), docHint = $('#docpath').placeholder;
function askDoc() {
  if (docbox.open) return;
  $('#docpath').value = '';
  $('#docpath').placeholder = docHint;
  docbox.returnValue = '';
  docbox.showModal();
  $('#docpath').focus();
}
docbox.addEventListener('close', async () => {
  const path = $('#docpath').value.trim();
  if (docbox.returnValue !== 'add' || !path) return;
  try {
    const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ from: 'page', path }) });
    const l = await r.json();
    if (!r.ok) return alertDoc(l.error);
    addCard(l);
  } catch {}
});
// a file dropped on the box fills in its path: a file manager hands it over as
// a file:// URI, a terminal or an editor as plain text. A browser keeps the
// path of a bare File to itself (Chrome does so even from a file manager), so
// the server looks for one of that name, size and time under home
function droppedPath(dt) {
  const s = (dt.getData('text/uri-list') || dt.getData('text/plain') || '')
    .split(/\r?\n/).map(l => l.trim()).find(l => l && !l.startsWith('#'));
  if (!s) return null;
  if (!s.startsWith('file://')) return s;
  try { return decodeURIComponent(new URL(s).pathname); } catch { return null; }
}
docbox.addEventListener('dragover', e => { e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = 'copy'; });
async function foundPath(f) {
  if (!f) return null;
  try {
    const q = new URLSearchParams({ name: f.name, size: f.size, mtime: f.lastModified });
    const r = await fetch('/api/find?' + q);
    return r.ok ? ((await r.json()).paths || [])[0] || null : null;
  } catch { return null; }
}
docbox.addEventListener('drop', async e => {
  e.preventDefault();
  e.stopPropagation();
  const file = e.dataTransfer.files[0];
  let path = droppedPath(e.dataTransfer);
  if (!path && file) {
    $('#docpath').value = '';
    $('#docpath').placeholder = 'Looking for ' + file.name + '…';
    path = await foundPath(file);
  }
  if (!path) return toast('Could not find ' + esc(file ? file.name : 'that file') + ' under home: paste its path instead', 4000);
  $('#docpath').value = path;
  docbox.close('add');
});
// A file dragged over the page shows where it can go, and dropped anywhere it
// opens as a card right there, if the text viewer can read it; else it says so
const carriesFile = dt => [...dt.types].some(t => t === 'Files' || t === 'text/uri-list');
let dragDepth = 0;
const dropzone = on => { if (!on) dragDepth = 0; $('#dropzone').hidden = !on; };
window.addEventListener('dragenter', e => {
  if (!carriesFile(e.dataTransfer) || docbox.open) return;
  dragDepth++;
  dropzone(true);
});
window.addEventListener('dragleave', () => { if (dragDepth && --dragDepth === 0) dropzone(false); });
window.addEventListener('dragover', e => {
  if (!carriesFile(e.dataTransfer)) return;
  e.preventDefault();                // else the browser leaves the board to show the file
  e.dataTransfer.dropEffect = 'copy';
});
window.addEventListener('drop', async e => {
  if (!carriesFile(e.dataTransfer)) return;
  e.preventDefault();
  dropzone(false);
  const file = e.dataTransfer.files[0], name = file ? file.name : 'that file';
  const box = $('#pan').getBoundingClientRect();
  const at = [(e.clientX - box.left - origin[0]) / zoom, (e.clientY - box.top - origin[1]) / zoom];
  const path = droppedPath(e.dataTransfer) || await foundPath(file);
  if (!path) return toast('Could not find ' + esc(name) + ' under home, so it cannot be opened', 4000);
  try {
    const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ from: 'page', path }) });
    const l = await r.json();
    if (!r.ok) return toast('The text viewer cannot open ' + esc(name) + ': ' + esc(l.error || 'unknown error'), 4000);
    const w = linkWin(l);
    addCard(l, [at[0] - w.w / 2, at[1] - w.h / 2]);
  } catch {}
});
function alertDoc(msg) {            // said where you were typing, not in a modal
  askDoc();
  $('#docpath').value = '';
  $('#docpath').placeholder = 'Could not open it: ' + (msg || 'unknown error');
  toast('Could not open it: ' + esc(msg || 'unknown error'), 4000);
}
const helpbox = $('#helpbox');
const showHelp = () => {
  if (helpbox.open) return;
  $('#helpq').value = '';
  filterHelp();
  helpbox.showModal();
  $('#helpq').focus();
};
// every word must turn up in the row, key or words; a section with none left goes
function filterHelp() {
  const words = $('#helpq').value.toLowerCase().split(/\s+/).filter(Boolean);
  helpbox.querySelectorAll('.helpbody section').forEach(s => {
    let any = false;
    s.querySelectorAll('tr').forEach(tr => {
      const hit = words.every(w => tr.textContent.toLowerCase().includes(w));
      tr.hidden = !hit;
      if (hit) markWords(tr, words);
      any = any || hit;
    });
    s.hidden = !any;
  });
}

// the row starts again from its own markup each time, then each text node has
// the words wrapped where they fall; kbd and the rest stay as they were
function markWords(tr, words) {
  if (tr.plain === undefined) tr.plain = tr.innerHTML;
  tr.innerHTML = tr.plain;
  if (!words.length) return;
  const re = new RegExp(words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'gi');
  const walk = document.createTreeWalker(tr, NodeFilter.SHOW_TEXT);
  const texts = [];
  while (walk.nextNode()) texts.push(walk.currentNode);
  texts.forEach(t => {
    if (!re.test(t.data)) return;
    re.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let at = 0;
    for (const m of t.data.matchAll(re)) {
      frag.append(t.data.slice(at, m.index));
      const mk = document.createElement('mark');
      mk.textContent = m[0];
      frag.append(mk);
      at = m.index + m[0].length;
    }
    frag.append(t.data.slice(at));
    t.replaceWith(frag);
  });
}
$('#helpq').oninput = filterHelp;
$('#helpclose').onclick = () => helpbox.close();

// ---- palette: one box to find an action, a tile or a group (:) -------------
const palbox = $('#palbox');
const ACTIONS = [
  ['New terminal', 't', () => newTerm()],
  ['Claude Code', 'c', () => newTerm({ claude: true })],
  ['Link card', 'u', () => askLink()],
  ['Picture', 'p', () => askImage()],
  ['Markdown file', 'o', () => askDoc()],
  ['Copy ref for Claude', 'y', () => copyRef()],
  ['Group', 'g', () => newGroup()],
  ['Actual size', '1', () => actualSize()],
  ['Loupe', 'z', () => setLens(!lensOn)],
  ['Map of the surface', 'm', () => setMap(!mapPinned)],
  ['Top bar', 'b', () => setBare(!bare)],
  ['Filter', '/', () => { openQ(); }],
  ['Architecture', 'a', () => showArch()],
  ['Keys help', '?', () => showHelp()],
  ['Move/size picked tile', 'Super+Enter', () => {
    const w = selected() || data && data.windows.find(x => x.focused && visible()(x));
    if (w) startTile(w);
    else toast('Pick a window first: <kbd>↑↓←→</kbd>, then <kbd>Super+Enter</kbd>');
  }],
  ['Reset layout', '', () => {     // it asks twice, so the button is left armed
    if (bare) setBare(false);
    $('#reset').click();
    toast('Click <b>Reset layout</b> again to confirm');
  }],
].map(([name, key, run]) => ({ kind: 'action', name, key, extra: '', run }));
let palRows = [], palAt = 0;

// the groups and tiles as they are right now, so the list is never stale
function palItems() {
  const gs = groups.map(g => ({ kind: 'group', name: g.name, key: '', extra: g.dir || '',
    run: () => fitGroup(g) }));
  const ws = (data ? data.windows : []).map(w => {
    const t = w.term && terms.get(w.term.session);
    return { kind: kindOf(w.id) === 'term' ? 'terminal' : kindOf(w.id), key: '',
      name: w.title || (t && t.title) || w.app || '', extra: haystack(w),
      run: () => { sel = w.id; render(); reveal(); } };
  });
  return [...ACTIONS, ...gs, ...ws];
}

// bring the group to fill the frame, as fitAll does for everything
function fitGroup(g) {
  const pan = $('#pan'), pad = 24;
  zoom = clamp(Math.min((pan.clientWidth - pad * 2) / g.w, (pan.clientHeight - pad * 2) / g.h));
  origin = [(pan.clientWidth - g.w * zoom) / 2 - g.x * zoom,
            (pan.clientHeight - g.h * zoom) / 2 - g.y * zoom];
  store.set('zoom', zoom);
  store.set('origin', origin);
  render();
}

// every word must be somewhere; a name that starts with it beats one that has
// it at a word start, which beats one that has it inside a word
function palScore(it, words) {
  const name = it.name.toLowerCase(), all = name + ' ' + it.extra.toLowerCase();
  let s = 0;
  for (const w of words) {
    if (name.startsWith(w)) s += 4;
    else if (name.includes(' ' + w)) s += 3;
    else if (name.includes(w)) s += 2;
    else if (all.includes(' ' + w)) s += 1;
    else if (!all.includes(w)) return -1;
  }
  return s;
}

const KIND_ORDER = { action: 0, group: 1 };
function palFind() {
  const words = $('#palq').value.toLowerCase().split(/\s+/).filter(Boolean);
  let rows = palItems();
  if (!words.length) rows = rows.filter(r => r.kind === 'action' || r.kind === 'group');
  else {
    rows.forEach(r => { r.score = palScore(r, words); });
    rows = rows.filter(r => r.score >= 0)
      .sort((a, b) => b.score - a.score || (KIND_ORDER[a.kind] ?? 2) - (KIND_ORDER[b.kind] ?? 2));
  }
  palRows = rows;
  palAt = 0;
  const list = $('#pallist');
  list.textContent = '';
  rows.forEach((r, i) => {
    const el = document.createElement('div');
    el.className = 'palrow';
    el.setAttribute('role', 'option');
    el.innerHTML = `<span class="palkind">${r.kind}</span><span class="palname">${esc(r.name)}</span>`
      + (r.key ? `<kbd>${esc(r.key)}</kbd>` : '');
    if (words.length) markWords(el.querySelector('.palname'), words);
    el.onmousemove = () => palPick(i, false);
    el.onclick = () => runPal(r);
    list.append(el);
  });
  if (!rows.length) list.innerHTML = '<div class="palnone">Nothing matches</div>';
  palPick(0);
}
function palPick(i, scroll = true) {
  palAt = i;
  [...$('#pallist').children].forEach((el, j) => el.classList.toggle('on', j === i));
  const el = $('#pallist').children[i];
  if (scroll && el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
}
// closed first, so a dialog the action opens does not land under this one
function runPal(r) {
  palbox.close();
  r.run();
}
const showPalette = () => {
  if (palbox.open) return;
  $('#palq').value = '';
  palFind();
  palbox.showModal();
  $('#palq').focus();
};
$('#palq').oninput = palFind;
palbox.addEventListener('keydown', e => {
  e.stopPropagation();               // none of these are the page's keys
  const n = palRows.length;
  const step = e.key === 'ArrowDown' || (e.ctrlKey && e.key === 'n') ? 1
    : e.key === 'ArrowUp' || (e.ctrlKey && e.key === 'p') ? -1 : 0;
  if (step) { e.preventDefault(); if (n) palPick((palAt + step + n) % n); }
  else if (e.key === 'Enter') { e.preventDefault(); if (palRows[palAt]) runPal(palRows[palAt]); }
});
// squared, so the slider gives fine control down at the small end where the
// whole surface lives and still reaches far enough in to read a window
$('#zoom').addEventListener('input', () => {
  setZoom(MAX_ZOOM * Math.pow($('#zoom').value / 100, 2));
});
// 1:1 is the one zoom where a terminal is not scaled at all, so its text lands
// on whole pixels; held about the picked tile, or the middle with none picked
// A second 1 goes back to where the first one came from, unless you have
// panned or zoomed since: the way back is one step, kept across a reload, and
// any move of your own forgets it (see leftBack).
let backView = store.get('back', null), moving = false;
function actualSize() {
  if (backView) {
    const b = backView;
    setBack(null);
    moving = true;
    zoom = b.zoom;
    origin = b.origin;
    store.set('zoom', zoom);
    store.set('origin', origin);
    render();
    moving = false;
    stirMap();
    return toast('back to ' + Math.round(zoom * 100) + '%', 1400);
  }
  const was = { zoom, origin: [...origin] };
  const el = sel && tileEls.get(sel);
  moving = true;
  if (!el) setZoom(1);
  else {
    const r = el.getBoundingClientRect();
    zoomAbout(1, r.left + r.width / 2, r.top + r.height / 2);
  }
  wholePixels();
  moving = false;
  if (was.zoom !== 1) setBack(was);
}
function setBack(v) { backView = v; store.set('back', v); }
function leftBack() { if (backView && !moving) setBack(null); }
// and on whole screen pixels too: half a pixel off and the text smears
function wholePixels() {
  const box = $('#pan').getBoundingClientRect();
  shift(Math.round(box.left + origin[0]) - box.left - origin[0],
        Math.round(box.top + origin[1]) - box.top - origin[1]);
}
// the whole arrangement goes, so it asks once more: a second click within 3s
let resetArmed = 0;
$('#reset').onclick = () => {
  const b = $('#reset');
  if (!resetArmed) {
    b.textContent = 'Click again to reset';
    resetArmed = setTimeout(() => { resetArmed = 0; b.textContent = 'Reset layout'; }, 3000);
    return;
  }
  clearTimeout(resetArmed);
  resetArmed = 0;
  b.textContent = 'Reset layout';
  layout = {};
  scales = {};
  saveLayout();
  render();
};
addEventListener('resize', render);
// the frame can change size without a window resize (bar folded, layout settled): the edge marks are measured against it
new ResizeObserver(markEdges).observe($('#pan'));
// overflow:hidden still lets the browser scroll the frame to bring a focused
// terminal into view, and everything inside it, edge marks too, slides off
// its place. The surface is placed by origin, never scrolled: put it back
$('#pan').addEventListener('scroll', e => {
  e.target.scrollTop = 0;
  e.target.scrollLeft = 0;
  markEdges();
});
$('#q').addEventListener('input', () => { sel = null; render(); });
// hidden until asked for (/ or the palette); stays while it holds text, folds when it empties and loses focus
const openQ = () => { if (bare) setBare(false); $('#q').classList.add('on'); $('#q').focus(); };
const foldQ = () => { if (!$('#q').value) $('#q').classList.remove('on'); };
$('#q').addEventListener('blur', foldQ);

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
    if (here.has(id) || (id.startsWith('husk:') && husks.has(id.slice(5))) || (ptyDown && id.startsWith('web:'))) return missing.delete(id);
    const n = (missing.get(id) || 0) + 1;
    missing.set(id, n);
    if (n >= 30) { delete layout[id]; delete scales[id]; missing.delete(id); changed = true; }
  });
  if (changed) saveLayout();
}

async function poll() {
  const asked = Date.now();
  try {
    // asking for screens is what keeps the grabber awake
    const r = await fetch('/api/windows?screens=1');
    const got = await r.json();
    // an error answer is no picture of the desktop: keep the last good one
    if (!r.ok || !Array.isArray(got.windows)) throw new Error(got.error || r.status);
    data = got;
    takeArrange(got.arrange, asked);
    data.windows.forEach(w => { if (scales[w.id]) { w.w *= scales[w.id]; w.h *= scales[w.id]; } });
    takePings(data.pings || [], asked);
    cstate = data.claude || {};
    takeLinks(data.links || [], asked);
    if (links.some(l => l.diff && !diffs.has(l.diff))) readDiffs();   // a diff card from before a reload
    data.windows.push(...links.map(linkWin));
    // one sent from outside — a shell, an agent — is placed by the first page to see it, in the Inbox
    links.filter(l => l.x == null && !pend.has(l.id)).forEach(l => l.origin === 'api' ? arrivedCard(l) : addCard(l, null, true));
    forgetGone();
    tellTerms();
    failures = 0;
    // restarted from its terminal: the page it served is the old one
    if (started !== null && data.started !== started) return location.reload();
    started = data.started;
  } catch { failures++; }
  render();
}

// every word has to be somewhere in what the tile is: its title, app, the
// program and folder of a terminal, a card's address, its workspace as ws2
function haystack(w) {
  const t = w.term && terms.get(w.term.session);
  return [w.title, w.app, w.cls, t && t.title, w.term && w.term.running, w.term && w.term.cwd,
          w.link && (w.link.url || w.link.path || w.link.image || w.link.tool || w.link.diff || w.link.text),
          w.desktop !== null && w.desktop !== undefined ? 'ws' + (w.desktop + 1) : ''
         ].filter(Boolean).join(' ').toLowerCase();
}
function visible() {
  const words = $('#q').value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return w => !words.length || words.every(q => haystack(w).includes(q));
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
let groups = store.get('groups', []);   // [{id, name, x, y, w, h, dir?}] in surface px; dir is where its new terminals start
const groupEls = new Map();

function newGroup() {
  const w = 1600, h = 1000, [cx, cy] = viewCenter();
  const [x, y] = clearSpot([cx - w / 2, cy - h / 2]);
  // numbered, and named straight away: a group called Group says nothing
  const used = new Set(groups.map(g => g.name));
  let n = 1;
  while (used.has(n === 1 ? 'Group' : 'Group ' + n)) n++;
  const g = { id: newId(), name: n === 1 ? 'Group' : 'Group ' + n, x, y, w, h };
  groups.push(g);
  saveGroups();
  render();
  const el = groupEls.get(g.id);
  if (el) rename(g, el.querySelector('.gname'));
}

const saveGroups = saveArrange;

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

// the tools chip: what the group's folder can run, from its tmp/ scripts and
// its .winlist-tools file, read afresh each time it is opened
async function showTools(g, chip) {
  closeTools();
  const res = await fetch('/api/tools?dir=' + encodeURIComponent(g.dir))
    .then(r => r.json()).catch(() => null);
  if (!res || !res.tools) return void toast('Could not read the tools: ' + esc((res && res.error) || 'no answer from the server'), 4000);
  if (!res.tools.length) return void toast(`No tools in ${esc(shortPath(g.dir))}: add executable <code>tmp/*.sh</code> scripts, or <code>Name: command</code> lines in <code>.winlist-tools</code>`, 6000);
  const menu = document.createElement('div');
  menu.id = 'tools';
  menu.setAttribute('role', 'menu');
  res.tools.forEach((t, i) => {
    const b = document.createElement('button');
    b.setAttribute('role', 'menuitem');
    b.title = t.cmd;
    b.innerHTML = `<kbd>${i + 1}</kbd><span><b>${esc(t.name)}</b>${t.about ? `<small>${esc(t.about)}</small>` : ''}</span>`;
    b.onclick = () => { closeTools(); toolButton(g, t); };
    menu.append(b);
  });
  const r = chip.getBoundingClientRect();
  menu.style.left = Math.max(4, Math.min(r.left, innerWidth - 340)) + 'px';
  menu.style.top = r.bottom + 4 + 'px';
  document.body.append(menu);
  const items = [...menu.children];
  items[0].focus();
  menu.addEventListener('keydown', e => {
    e.stopPropagation();
    const at = items.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); return closeTools(); }
    if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); items[(at + 1) % items.length].focus(); }
    if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); items[(at - 1 + items.length) % items.length].focus(); }
    const n = +e.key;
    if (n >= 1 && n <= items.length) { e.preventDefault(); items[n - 1].click(); }
  });
  setTimeout(() => addEventListener('pointerdown', outside), 0);
}
function outside(e) { if (!e.target.closest('#tools')) closeTools(); }

// picking a tool puts its button on the surface, in the group; pressing that
// is what runs it, so a server you start every morning is one click away
async function toolButton(g, t) {
  const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ tool: t.name, dir: g.dir, from: 'page' }) })
    .catch(() => null);
  const l = r && await r.json().catch(() => null);
  if (!r || !r.ok || !l) return void toast('Could not add the button: ' + esc((l && l.error) || 'no answer from the server'), 4000);
  const w = linkWin(l);
  let at = dropAt(w.w, w.h);
  if (!inGroup(g, [at[0] + w.w / 2, at[1] + w.h / 2])) at = [g.x + GRID, g.y + 2 * GRID];
  addCard(l, at);
}

// a tool is run afresh each press, in a new terminal beside its button, with
// whatever the script or .winlist-tools says now
async function runTool(l, w) {
  const res = await fetch('/api/tools?dir=' + encodeURIComponent(l.dir)).then(r => r.json()).catch(() => null);
  const t = res && res.tools && res.tools.find(t => t.name === l.tool);
  if (!t) return void toast(`No tool ${esc(l.tool)} in ${esc(shortPath(l.dir))} any more`, 4000);
  const [x, y] = seatOf(w);
  newTerm({ argv: t.argv, cwd: l.dir, corner: [x + w.w + GRID, y] });
}
function closeTools() {
  removeEventListener('pointerdown', outside);
  const m = $('#tools');
  if (m) m.remove();
}

// the folder chip: click, type a path, Enter; empty clears it. A group still
// called Group takes the folder's name, as it would have been named after it
function setDir(g, chip) {
  chip.contentEditable = 'true';
  chip.textContent = g.dir || '';
  chip.focus();
  getSelection().selectAllChildren(chip);
  chip.addEventListener('blur', async () => {
    chip.contentEditable = 'false';
    const dir = chip.textContent.trim().replace(/(.)\/+$/, '$1') || undefined;
    if (dir) {                       // a folder that is not there would start nothing
      const ok = await fetch('/api/dir?path=' + encodeURIComponent(dir))
        .then(r => r.ok).catch(() => false);
      if (!ok) { toast('No such folder: ' + esc(dir), 4000); return render(); }
    }
    g.dir = dir;
    const base = g.dir && g.dir.split('/').pop();
    if (base && base !== '~' && /^Group( \d+)?$/.test(g.name)) g.name = base;
    saveGroups();
    render();
  }, { once: true });
  chip.onkeydown = ev => {
    ev.stopPropagation();
    if (ev.key === 'Enter' || ev.key === 'Escape') { ev.preventDefault(); chip.blur(); }
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
      el.innerHTML = `<div class="gcap"><span class="gname" title="Double-click to rename"></span><span class="gcount"></span>`
        + `<span class="gdir" title="Folder new terminals start in (click to set)"></span>`
        + `<span class="gtools" title="Put a button for one of this project's tools in the group">▸ tools</span>`
        + `<span class="shut" title="Remove the group (its windows stay)">✕</span></div>`
        + `<div class="grip" title="Drag to resize this group"></div>`;
      const cap = el.querySelector('.gcap'), name = el.querySelector('.gname');
      const dir = el.querySelector('.gdir'), tools = el.querySelector('.gtools');
      cap.addEventListener('pointerdown', e => {
        if (name.isContentEditable || dir.isContentEditable || e.target === dir || e.target === tools) return e.stopPropagation();
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
      dir.addEventListener('click', () => { if (!dir.isContentEditable) setDir(el.group, dir); });
      tools.addEventListener('click', () => showTools(el.group, tools));
      el.querySelector('.grip').addEventListener('pointerdown', e => sizeGroup(e, el.group, el));
      groupEls.set(g.id, el);
      $('#groups').append(el);
    }
    el.group = g;
    if (!el.querySelector('.gname').isContentEditable) el.querySelector('.gname').textContent = g.name;
    const dir = el.querySelector('.gdir');
    if (!dir.isContentEditable) {
      dir.textContent = g.dir ? shortPath(g.dir) : '+ folder';
      dir.classList.toggle('unset', !g.dir);
    }
    el.querySelector('.gtools').hidden = !g.dir;
    const n = data ? members(g).length : 0;
    el.querySelector('.gcount').textContent = n ? '· ' + n : '';
    placeGroup(el, g);
  });
  groupEls.forEach((el, id) => { if (!live.has(id)) { el.remove(); groupEls.delete(id); } });
}

// said over the surface, where it is seen, not only in the bar that is folded
// away — and before the first answer too, when there is nothing else to show
function showTrouble() {
  const lost = restoring ? [] : (data && data.lost) || [];
  const trouble = failures >= 2 ? `Lost the server — retrying. Is it running? <code>python3 winlist/winlist_server.py</code>`
    : data && data.error ? esc(data.error)
    : lost.length ? `${lost.length} terminal${lost.length > 1 ? 's' : ''} did not survive the restart. `
      + `<button data-act="restore">Restore ${lost.length > 1 ? 'all' : ''}</button> <button data-act="dismiss">Dismiss ${lost.length > 1 ? 'all' : ''}</button>`
    : restoreNote;
  if ($('#banner').innerHTML !== trouble) $('#banner').innerHTML = trouble;   // not under a click
  $('#banner').classList.toggle('on', !!trouble);
}

// Terminals a reboot took are remembered on the server (data.lost) and come
// back as husks (see renderHusks): each can be restored or closed, or all at
// once from the bar. A restored one starts in the same folder, where its tile was.
let restoring = false, restoreNote = '';
const going = new Set();            // husks being restored or closed right now
const pendingOut = new Map();       // new session id -> the old one's output, for mount()
const savedOuts = new Map();        // old session id -> promise of its saved output
const savedOut = id => savedOuts.get(id) || savedOuts.set(id, fetch('/api/terminals/' + id + '/scrollback')
  .then(r => r.ok ? r.arrayBuffer() : new ArrayBuffer(0)).then(b => new Uint8Array(b))
  .catch(() => new Uint8Array(0))).get(id);
// whatever the old screen left switched on (full screen, hidden cursor), off again
const OUT_END = '\x1b[?1049l\x1b[?25h\x1b[0m\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l';   // and mouse reporting
async function restoreTerm(r, keep) {
  going.add(r.id);
  renderHusks();
  let moved = 0;
  const out = keep ? await savedOut(r.id) : null;
  if (keep) {
    const body = { cols: r.cols, rows: r.rows };
    if (r.cwd_ok) body.cwd = r.cwd;
    if (r.claude) body.argv = r.session ? ['claude', '--resume', r.session] : ['claude'];
    const made = await fetch('/api/terminals', { method: 'POST', body: JSON.stringify(body) })
      .then(x => x.json()).catch(() => null);
    if (!made || !made.id) {
      toast('Could not restore one: ' + esc((made && made.error) || 'no answer from the server'), 4000);
      going.delete(r.id);
      return 0;                     // stays a husk, to try again
    }
    const at = layout['husk:' + r.id] || r.at;     // where the husk was dragged to
    if (at) layout['web:' + made.id] = at;
    if (r.face) faces[made.id] = r.face;
    if (out.length) pendingOut.set(made.id, out);
    if (!r.cwd_ok) moved++;
  }
  await fetch('/api/terminals/' + r.id, { method: 'DELETE' }).catch(() => {});   // forgets it
  savedOuts.delete(r.id);
  delete layout['husk:' + r.id];
  going.delete(r.id);
  store.set('faces', faces);
  saveLayout();
  poll();
  return moved;
}
async function restoreTerms(keep) {
  restoring = true;
  showTrouble();
  let moved = 0;
  for (const r of (data.lost || []).slice()) moved += await restoreTerm(r, keep);
  restoreNote = moved ? `${moved} folder${moved > 1 ? 's are' : ' is'} gone: started in ~ instead.` : '';
  if (restoreNote) setTimeout(() => { restoreNote = ''; showTrouble(); }, 8000);
  restoring = false;
  poll();
}
$('#banner').addEventListener('click', e => {
  const act = e.target.dataset.act;
  if (act) restoreTerms(act === 'restore');
});

// A terminal the restart took stays on the surface as a husk: its old spot and
// size, its last title, its last commands and its last output, dimmed and
// read-only. Restore starts a shell in its folder; Close forgets it.
const husks = new Map();            // old session id -> {el, t, term, key}
function renderHusks() {
  const lost = ((data && data.lost) || []).filter(r => !going.has(r.id));
  const live = new Set(lost.map(r => r.id));
  lost.forEach(r => {
    let h = husks.get(r.id);
    if (!h) {
      const el = document.createElement('div');
      el.className = 'tile husk';
      el.innerHTML = `<div class="cap"><span class="dot"></span><span class="t2"></span><span class="note"></span></div>`
        + `<div class="termbody"><div class="termwrap"><div class="termhost"></div></div>`
        + `<div class="hover"><div class="hcmds"></div>`
        + `<div class="hbtn"><button data-act="restore">Restore</button><button data-act="close">Close</button></div></div></div>`;
      // buttons are answered in pointerdown, before a drag takes the pointer
      // captive; the caption is the handle, as on a terminal
      el.addEventListener('pointerdown', e => {
        const act = e.target.dataset.act, cur = (data.lost || []).find(x => x.id === r.id) || r;
        if (act) { e.preventDefault(); return restoreTerm(cur, act === 'restore'); }
        if (e.target.closest('.cap')) drag(e, husks.get(r.id).w, el);
      });
      const ps = profiles(), face = ps.find(p => p.name === (faces[r.id] || r.face)) || ps[0] || { font: look().font, size: look().size };
      const term = new Terminal({
        cols: r.cols, rows: r.rows, theme: termTheme(), fontFamily: termFont(face.font),
        fontSize: face.size || 13, lineHeight: 1.125, disableStdin: true, cursorBlink: false,
        scrollback: 65536, convertEol: false,       // the whole of the 64 KB saved
      });
      $('#tiles').append(el);
      term.open(el.querySelector('.termhost'));
      h = { el, term, w: { id: 'husk:' + r.id, husk: r.id, w: 0, h: 0 }, t: { term, wrap: el.querySelector('.termwrap'), cap: el.querySelector('.cap') } };
      husks.set(r.id, h);
      // the output can come back after the husk has gone (restored, or closed):
      // a disposed xterm.js throws on a write or a scroll, so it is left alone
      savedOut(r.id).then(out => {
        if (h.dead) return;
        if (out.length) term.write(out);
        term.write(OUT_END + '\x1b[?25l', () => h.dead || term.scrollToBottom());
      });
    }
    const { el, t } = h, key = JSON.stringify([r.title, r.cwd, r.cmds]);
    if (h.key !== key) {                  // as text: titles and commands are whatever a program printed
      h.key = key;
      el.querySelector('.t2').textContent = r.title || (r.claude ? 'claude' : 'shell');
      el.querySelector('.note').textContent = shortPath(r.cwd) + ' · gone';
      el.querySelector('.dot').style.background = colorOf('Terminal');
      el.title = r.cwd || '';
      el.querySelector('.hcmds').replaceChildren(...(r.cmds || []).map(c => {
        const d = document.createElement('div');
        d.textContent = '$ ' + c;
        return d;
      }));
    }
    measure(t);
    Object.assign(h.w, { at: r.at || [0, 0], w: t.natural[0], h: t.natural[1] });
    place(el, h.w);
  });
  husks.forEach((h, id) => {
    if (live.has(id)) return;
    h.el.remove();
    h.dead = true;
    h.term.dispose();
    husks.delete(id);
  });
}

// The page knows where a terminal's tile sits and which face it has; the
// server keeps them with the terminal, for after a reboot. Told when they change.
const toldTerm = new Map();       // session id -> what the server was last told
function tellTerms() {
  husks.forEach((h, id) => {      // a husk dragged somewhere new
    const at = layout[h.w.id];
    if (!at) return;
    const was = JSON.stringify({ at: at.map(Math.round) }), k = 'husk:' + id;
    if (toldTerm.get(k) === was) return;
    toldTerm.set(k, was);
    fetch('/api/terminals/' + id, { method: 'PATCH', body: was }).then(r => { if (!r.ok) toldTerm.delete(k); }).catch(() => toldTerm.delete(k));
  });
  data.windows.forEach(w => {
    if (!w.term || !w.term.alive) return;
    const id = w.term.session, at = seatOf(w).map(Math.round), face = (profiles()[0] || {}).name;
    const body = { at, face: faces[id] || face };
    if (!body.face) delete body.face;
    const was = JSON.stringify(body);
    if (toldTerm.get(id) === was) return;
    toldTerm.set(id, was);
    fetch('/api/terminals/' + id, { method: 'PATCH', body: was }).then(r => { if (!r.ok) toldTerm.delete(id); }).catch(() => toldTerm.delete(id));
  });
}

function render() {
  if (!data) return showTrouble();
  const match = visible(), q = $('#q').value.trim();
  renderGroups();
  renderCanvas(match);
  renderHusks();
  drawMark();
  status(match, q);
  syncLens();
}

function status(match, q) {
  const hits = data.windows.filter(w => !w.link && match(w));
  const ours = data.windows.filter(w => w.term).length;
  const desks = new Set(data.windows.filter(w => !w.term).map(w => w.desktop)).size;
  const shown = data.windows.filter(match).length;
  $('#nomatch').classList.toggle('on', !!q && !shown);
  if (q && !shown) $('#nomatch').innerHTML = `Nothing matches “${esc(q)}” — <kbd>Esc</kbd> clears`;
  $('#stat').textContent = `${hits.length - ours}${q ? " of " + (data.windows.length - links.length - ours) : ""} windows · `
    + (ours ? `${ours} terminal${ours > 1 ? 's' : ''} of our own · ` : '')
    + `${data.grid.cols}×${data.grid.rows} workspaces · ${desks} in use`;
  showTrouble();
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
const seatOf = w => layout[w.id] || (w.husk ? w.at : seat(w));

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

// The surface moves by whole screen pixels, wherever the frame itself sits:
// half a pixel off and every glyph is drawn across two, which blurs the text
function placeCanvas() {
  const b = $('#pan').getBoundingClientRect();
  $('#canvas').style.transform = `translate(${Math.round(b.left + origin[0]) - b.left}px,` +
    `${Math.round(b.top + origin[1]) - b.top}px)`;
}
function shift(dx, dy) {          // slide the whole surface, no edges to run into
  origin = [origin[0] + dx, origin[1] + dy];
  leftBack();
  store.set('origin', origin);
  placeCanvas();
  markEdges();
  stirMap();
}

// The whole surface small, in the corner, with the view as a frame on it:
// shown while you pan or zoom and gone a moment after, or kept with m. A press
// or a drag on it carries the view there.
let mapPinned = store.get('map', false), mapHide = 0, mapFit = null;
if (mapPinned) $('#map').classList.add('on');
function stirMap() {
  $('#map').classList.add('on');
  clearTimeout(mapHide);
  if (!mapPinned) mapHide = setTimeout(() => $('#map').classList.remove('on'), 1200);
}
function setMap(v) {
  mapPinned = v;
  store.set('map', v);
  track('map', { on: v });
  clearTimeout(mapHide);
  $('#map').classList.toggle('on', v);
  markEdges();
}
function drawMap(W, H) {
  const cv = $('#map'), on = cv.classList.contains('on');
  if (!on || !data || !W || !H) return;
  const dpr = devicePixelRatio || 1, MW = 220, MH = 150;
  if (cv.width !== MW * dpr) { cv.width = MW * dpr; cv.height = MH * dpr; }
  // what there is and what you see, whichever is bigger; held while you drag
  // the map, or the ground would move under the pointer
  if (!mapFit || !mapFit.held) {
    const [b0, b1, b2, b3] = bounds(), v = [-origin[0] / zoom, -origin[1] / zoom];
    const x0 = Math.min(b0, v[0]), y0 = Math.min(b1, v[1]);
    const x1 = Math.max(b2, v[0] + W / zoom), y1 = Math.max(b3, v[1] + H / zoom);
    const pad = 0.04 * Math.max(x1 - x0, y1 - y0);
    const k = Math.min(MW / (x1 - x0 + 2 * pad), MH / (y1 - y0 + 2 * pad));
    mapFit = { k, x: x0 - pad - (MW / k - (x1 - x0 + 2 * pad)) / 2, y: y0 - pad - (MH / k - (y1 - y0 + 2 * pad)) / 2 };
  }
  const { k, x, y } = mapFit, c = cv.getContext('2d'), css = getComputedStyle(cv);
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, MW, MH);
  const match = visible();
  data.windows.forEach(w => {
    const [wx, wy] = seatOf(w);
    c.globalAlpha = match(w) ? 0.85 : 0.2;
    c.fillStyle = pings.has(w.id) ? '#f2a516' : colorOf(w.app);
    c.fillRect((wx - x) * k, (wy - y) * k, Math.max(2, w.w * k), Math.max(2, w.h * k));
    if (w.id === sel) {
      c.globalAlpha = 1;
      c.strokeStyle = css.color;
      c.lineWidth = 1.5;
      c.strokeRect((wx - x) * k, (wy - y) * k, Math.max(2, w.w * k), Math.max(2, w.h * k));
    }
  });
  c.globalAlpha = 1;
  c.strokeStyle = css.getPropertyValue('--accent').trim() || '#e0875c';
  c.lineWidth = 1.5;
  c.strokeRect((-origin[0] / zoom - x) * k, (-origin[1] / zoom - y) * k, W / zoom * k, H / zoom * k);
}
$('#map').addEventListener('pointerdown', e => {
  if (e.button) return;
  e.preventDefault();
  e.stopPropagation();                 // the map, not the surface under it
  const cv = $('#map');
  cv.setPointerCapture(e.pointerId);
  if (mapFit) mapFit.held = true;
  const go = ev => {
    if (!mapFit) return;
    const r = cv.getBoundingClientRect(), pan = $('#pan');
    const wx = mapFit.x + (ev.clientX - r.left) / mapFit.k, wy = mapFit.y + (ev.clientY - r.top) / mapFit.k;
    shift(pan.clientWidth / 2 - wx * zoom - origin[0], pan.clientHeight / 2 - wy * zoom - origin[1]);
  };
  go(e);
  const off = follow(cv, go, () => { off(); if (mapFit) mapFit.held = false; markEdges(); });
});

// A triangle on the frame's edge for windows wholly out of view, on the line from
// the frame's middle to the window's. Nearby ones share a triangle, and a window
// the search has ruled out gets none.
// A window that wants you — Claude finished in it — pings: its triangle bobs
// toward it, or the tile itself pulses if it is in view, until it has been in
// view for two seconds, half of it at least, big enough to read.
let cstate = {};             // window id -> {state, at}: what Claude is doing there
const pings = new Set(), inViewSince = new Map();
const unpinged = new Map();   // window id -> when the server was told it is seen; 0 while in flight
function seenPing(id) {
  pings.delete(id);
  unpinged.set(id, 0);
  fetch('/api/ping/' + encodeURIComponent(id), { method: 'DELETE' })
    .catch(() => {})
    .finally(() => unpinged.set(id, Date.now()));
}
// what the server holds, less what this page cleared since the poll set out
function takePings(list, asked) {
  for (const [id, at] of unpinged) if (at && at < asked) unpinged.delete(id);
  pings.clear();
  list.forEach(id => { if (!unpinged.has(id)) pings.add(id); });
}
function lookedAt(w, px, py, pw, ph, W, H) {
  const ox = Math.min(px + pw, W) - Math.max(px, 0), oy = Math.min(py + ph, H) - Math.max(py, 0);
  return ox > 0 && oy > 0 && ox * oy >= pw * ph / 2 && pw >= 300;
}

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
    const match = visible(), cx = W / 2, cy = H / 2, inset = 8, now = Date.now();
    let seen = false;
    data.windows.forEach(w => {
      if (!match(w)) return;
      const [x, y] = seatOf(w);
      const px = origin[0] + x * zoom, py = origin[1] + y * zoom;
      const pw = w.term || isCard(w) ? w.w * zoom : Math.max(90, w.w * zoom);
      const ph = w.term || isCard(w) ? w.h * zoom : Math.max(60, w.h * zoom);
      const arrived = arrivals.has(w.id), ping = pings.has(w.id) || arrived;
      // a new card is small: wholly in view is enough, whatever the zoom
      const looked = arrived ? px >= 0 && py >= 0 && px + pw <= W && py + ph <= H : lookedAt(w, px, py, pw, ph, W, H);
      if (ping && looked) {
        if (!inViewSince.has(w.id)) inViewSince.set(w.id, now);
        else if (now - inViewSince.get(w.id) >= 2000) {
          if (arrived) { arrivals.delete(w.id); saveArrivals(); } else seenPing(w.id);
          seen = true;
        }
      } else inViewSince.delete(w.id);
      if (px < W && px + pw > 0 && py < H && py + ph > 0) return;   // some of it shows
      const dx = px + pw / 2 - cx, dy = py + ph / 2 - cy;
      const k = Math.min((cx - inset) / Math.abs(dx || 1e-9), (cy - inset) / Math.abs(dy || 1e-9));
      const ex = cx + dx * k, ey = cy + dy * k, key = Math.round(ex / 40) + ',' + Math.round(ey / 40);
      spots.set(key, [ex, ey, Math.atan2(dy, dx), ping ? w.id : (spots.get(key) || [])[3]]);
    });
    if (seen) render();
    // the tile pulses while you look; the look counts once the poll comes round
    if (inViewSince.size) setTimeout(markEdges, 2100);
  }
  const list = [...spots.values()];
  while (box.children.length < list.length) {
    const d = document.createElement('div');
    d.className = 'edge';
    // a pinging one is a way there: a click brings its window to the middle
    d.addEventListener('pointerdown', e => e.stopPropagation());
    d.addEventListener('click', () => d.ping && goToPing(d.ping));
    box.append(d);
  }
  while (box.children.length > list.length) box.lastChild.remove();
  list.forEach(([ex, ey, a, ping], i) => {
    const d = box.children[i], s = d.style;
    d.ping = ping;
    d.classList.toggle('ping', !!ping);
    s.left = ex + 'px';
    s.top = ey + 'px';
    s.setProperty('--a', a + 'rad');
  });
  drawMap(W, H);
}

// to the window, picked, and near enough to read: the look that clears the ping
function goToPing(id) {
  const w = data && data.windows.find(v => v.id === id), pan = $('#pan');
  if (!w) return;
  sel = id;
  render();
  reveal();
  if (w.w * zoom < 300) setZoom(Math.min(0.8 * pan.clientWidth / w.w, 0.8 * pan.clientHeight / w.h));
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
  leftBack();
  store.set('zoom', zoom);
  store.set('origin', origin);
  render();
  stirMap();
  // a rest within a tenth of 1:1 is taken to mean 1:1: anywhere else every
  // glyph is resampled and the text goes soft. Not while fingers still pinch
  clearTimeout(snapRest);
  if (zoom !== 1 && Math.abs(zoom - 1) <= 0.1) snapRest = setTimeout(function snap() {
    if (pointers.size) return (snapRest = setTimeout(snap, 300));
    zoomAbout(1, cx, cy);
    wholePixels();
  }, 300);
}
let snapRest = 0;

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

// ---- drop point: where a new card or terminal is centred ------------------
// A click on the background picks it; until then, or once you have panned or
// zoomed it out of view, it is the middle of what you are looking at.
let anchor = null;                 // [x, y] on the surface
let markTimer = null;

function dropAt(w, h) {
  const pan = $('#pan'), W = pan.clientWidth, H = pan.clientHeight;
  let c = viewCenter();
  if (anchor) {
    const px = origin[0] + anchor[0] * zoom, py = origin[1] + anchor[1] * zoom;
    if (px >= 0 && px <= W && py >= 0 && py <= H) c = anchor;
  }
  return [c[0] - w / 2, c[1] - h / 2];
}

function drawMark() {
  if (!anchor) return;
  const s = $('#mark').style;
  s.left = anchor[0] * zoom + 'px';
  s.top = anchor[1] * zoom + 'px';
}

function setAnchor(cx, cy) {
  const box = $('#pan').getBoundingClientRect();
  anchor = [(cx - box.left - origin[0]) / zoom, (cy - box.top - origin[1]) / zoom];
  drawMark();
  const m = $('#mark');
  m.classList.add('on');
  clearTimeout(markTimer);
  markTimer = setTimeout(() => m.classList.remove('on'), 1200);
}

// ---- links: a page you mean to come back to, kept as a card ---------------
// what the server holds, with what this page told it since the poll set out
function takeLinks(list, asked) {
  for (const [id, p] of pend) if (p.doneAt && p.doneAt < asked) pend.delete(id);
  const byId = new Map(list.map(l => [l.id, l]));
  for (const [id, p] of pend) if (p.card) byId.set(id, p.card); else byId.delete(id);
  links = [...byId.values()];
  for (const l of links) if (noteText.has(l.id)) l.text = noteText.get(l.id);
  // moved on another page: follow it, but never undo a drag under way here
  for (const l of links) {
    if (l.x == null || knownAt.get(l.id) === l.x + ',' + l.y) continue;
    layout['link:' + l.id] = [l.x, l.y];
    knownAt.set(l.id, l.x + ',' + l.y);
  }
}

// Cards were once kept by each browser. Hand this one's to the server, where
// it sat and how big, and drop what the server still had waiting from then:
// this browser carded those already.
async function moveCardsOut() {
  const old = store.get('links', null);
  if (!old) return;
  let ok = true;
  for (const l of old) {
    const at = layout['link:' + l.id] || [];
    try {
      const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify(
        { title: l.title, keep: { ...l, x: at[0], y: at[1] } }) });
      const got = await r.json();
      if (!r.ok) { ok = false; continue; }
      delete layout['link:' + l.id];
      if (at.length) layout['link:' + got.id] = at;
    } catch { ok = false; }
  }
  for (const id of store.get('taken', [])) {
    try { await fetch('/api/links/' + encodeURIComponent(id), { method: 'DELETE' }); } catch {}
  }
  store.set('layout', layout);
  if (ok) ['links', 'taken'].forEach(k => localStorage.removeItem('winlist.' + k));
}

// a card with no name of its own is called what it points at: the file's name,
// or the site and the last part of the address
function cardTitle(l) {
  if (l.title) return l.title;
  if (l.path || l.image) return baseName(l.path || l.image);
  try {
    const u = new URL(l.url), last = baseName(u.pathname);
    return u.host.replace(/^www\./, '') + (u.pathname.length > 1 ? '/' + last : '');
  } catch { return l.url || ''; }
}
function cardHost(url) {
  try { return new URL(url).host.replace(/^www\./, ''); } catch { return 'Link'; }
}
const isCard = w => w.link && !w.link.image && !w.link.path && !w.link.note && !w.link.diff;   // link or tool card
function linkWin(l) {
  return { id: 'link:' + l.id, link: l, title: cardTitle(l),
           app: l.tool ? 'Tool' : l.diff ? 'Diff' : l.image ? 'Image' : l.path ? (isMdPath(l.path) ? 'Markdown' : 'Text') : l.note ? 'Note' : cardHost(l.url),
           w: l.w || (l.image ? 640 : l.path || l.diff ? 720 : l.tool ? 240 : l.note ? 360 : 320),
           h: l.h || (l.image ? 480 : l.path || l.diff ? 900 : l.tool ? 96 : l.note ? 300 : 76),
           x: 0, y: 0, z: 1e9, desktop: null };
}

// ---- docs: a text file kept on the surface, read again when it changes -------
const isMdPath = p => /\.(md|markdown)$/i.test(p);
const docs = new Map();             // path -> {mtime, html, md, at} or {error}
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
    if (had && had.at && Date.now() - had.at < 1000) continue;   // a busy file is redrawn once a second at most
    const q = 'path=' + encodeURIComponent(l.path) + (had && had.mtime ? '&since=' + had.mtime : '');
    try {
      const r = await fetch('/api/file?' + q), d = await r.json();
      if (!r.ok) {
        if (!had || !had.error) { docs.set(l.path, { error: d.error }); changed = true; }
      } else if ('text' in d) {
        const isMd = d.kind ? d.kind === 'md' : isMdPath(l.path);
        docs.set(l.path, { mtime: d.mtime, md: isMd, at: Date.now(),
                           html: isMd ? md.parse(d.text) : `<pre class="txt">${esc(d.text)}</pre>` });
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
  const old = pic.querySelector('.docwrap'), top = old ? old.scrollTop : 0, left = old ? old.scrollLeft : 0;
  const inside = old && old.contains(document.activeElement);
  const d = docs.get(w.link.path);
  pic.className = 'pic card doc';
  pic.style.cssText = '';
  pic.innerHTML = `<div class="docwrap" tabindex="-1"><div class="md"></div></div>`;
  const body = pic.querySelector('.md');
  if (d && !d.error && !d.md) body.className = 'txtwrap';
  body.innerHTML = !d ? '<p>Reading…</p>'
    : d.error ? `<p class="gone">${esc(w.link.path)}: ${esc(d.error)}</p>` : d.html;
  Object.assign(pic.querySelector('.docwrap'), { scrollTop: top, scrollLeft: left });   // a save keeps your place
  if (inside) pic.querySelector('.docwrap').focus({ preventScroll: true });
}

// ---- diffs: what a PR changes, drawn on a card of its own beside the PR's ---
const diffs = new Map();            // PR url -> {sha, files, text, cut} or {error}
let diffBusy = false;
async function readDiffs(only) {    // only: the one just asked for; else every diff card, as the PR polls do
  if (diffBusy) return;
  diffBusy = true;
  let changed = false;
  for (const l of links) {
    if (!l.diff || (only && l.diff !== only)) continue;
    const had = diffs.get(l.diff);
    try {
      const d = await (await fetch('/api/diff?url=' + encodeURIComponent(l.diff)
        + (had && had.sha ? '&since=' + had.sha : ''))).json();
      if (d.same) continue;
      if (!had || had.sha !== d.sha || had.error !== d.error) { diffs.set(l.diff, d); changed = true; }
    } catch {}
  }
  diffBusy = false;
  if (changed) render();
}
const diffKey = w => 'diff ' + (diffs.has(w.link.diff) ? diffs.get(w.link.diff).sha || diffs.get(w.link.diff).error : '');

function diffCard(pic, w) {
  const old = pic.querySelector('.docwrap'), top = old ? old.scrollTop : 0, left = old ? old.scrollLeft : 0;
  const inside = old && old.contains(document.activeElement);
  const d = diffs.get(w.link.diff);
  pic.className = 'pic card doc';
  pic.style.cssText = '';
  pic.innerHTML = `<div class="docwrap" tabindex="-1"><div class="diff"></div></div>`;
  const body = pic.querySelector('.diff');
  if (!d || d.error) body.innerHTML = `<p class="gone">${d ? esc(d.error) : 'Reading…'}</p>`;
  else {
    const add = d.files.reduce((n, f) => n + f.additions, 0), del = d.files.reduce((n, f) => n + f.deletions, 0);
    body.innerHTML = `<div class="dfiles"><b>${d.files.length} file${d.files.length === 1 ? '' : 's'} changed</b> `
      + `<span class="dadd">+${add}</span> <span class="ddel">−${del}</span>`
      + d.files.map(f => `<div><span class="dadd">+${f.additions}</span> <span class="ddel">−${f.deletions}</span> ${esc(f.path)}</div>`).join('')
      + `</div>` + d.text.split('\n').map(ln => {
        const c = /^(\+\+\+|---) /.test(ln) || /^(diff |index |new file|deleted file|similarity|rename |old mode|new mode)/.test(ln) ? 'dmeta'
          : ln[0] === '+' ? 'dadd' : ln[0] === '-' ? 'ddel' : ln[0] === '@' ? 'dhunk' : '';
        return `<div class="dl ${c}">${esc(ln) || ' '}</div>`;
      }).join('')
      + (d.cut ? `<p class="gone">Cut at 1 MB: the rest of the diff is on GitHub.</p>` : '');
  }
  Object.assign(pic.querySelector('.docwrap'), { scrollTop: top, scrollLeft: left });   // a new commit keeps your place
  if (inside) pic.querySelector('.docwrap').focus({ preventScroll: true });
}

// the Diff button on a PR card: a diff card beside it, or the one already there
function openDiff(w) {
  const had = links.find(l => l.diff === w.link.url);
  if (had) { sel = 'link:' + had.id; render(); return void toast('Its diff is already on the board'); }
  fetch('/api/links', { method: 'POST', body: JSON.stringify({ diff: w.link.url, from: 'page' }) })
    .then(r => r.json().then(l => ({ ok: r.ok, l })))
    .then(({ ok, l }) => {
      if (!ok) return toast('Could not add the diff: ' + esc(l.error || 'unknown error'), 4000);
      const [x, y] = seatOf(w);
      addCard(l, [x + w.w + GRID, y]);
      readDiffs(l.diff);
    })
    .catch(() => toast('Could not add the diff: no answer from the server', 4000));
}

// ---- notes: markdown typed on the card itself, kept with the cards ----------
let noteEdit = null;                // id of the note being typed into
const noteSave = new Map();         // card id -> timer of the text not yet sent
const noteText = new Map();         // card id -> that text: a poll swaps the card objects, never this
function sendNote(id) {
  clearTimeout(noteSave.get(id)); noteSave.delete(id);
  const l = links.find(v => v.id === id), text = noteText.get(id);
  noteText.delete(id);
  if (l && text != null) { l.text = text; sendCard(l, { text }); }
}
function leaveNote(id) {
  if (noteEdit !== id) return;      // a redraw drops the textarea and blurs it too
  noteEdit = null;
  if (noteSave.has(id)) sendNote(id);
  if (tileEls.has(id)) render();     // closed: render is what is taking it off, and blurred it
}
function editNote(id) {
  noteEdit = id;
  render();
  const ta = tileEls.get(id) && tileEls.get(id).querySelector('.notetxt');
  if (ta) { ta.focus({ preventScroll: true }); ta.setSelectionRange(ta.value.length, ta.value.length); }
}
// y hands the picked tile to Claude: a link it can ask winlist about, which
// says what the tile is and how to get at it (a note's text and how to change
// it, a file's path, a terminal's folder and output, a window's process)
function refOf(id) {
  if (id.startsWith('link:')) {
    const l = links.find(v => 'link:' + v.id === id);
    if (!l) return null;
    const kind = l.note ? 'note' : l.path ? 'doc' : l.image ? 'img' : l.tool ? 'tool' : l.diff ? 'diff' : 'url';
    return `wl:${kind}:${l.id}`;
  }
  if (id.startsWith('web:')) return 'wl:term:' + id.slice(4);
  return /^0x[0-9a-f]+$/i.test(id) ? 'wl:win:' + id : null;
}
async function copyRef() {
  const ref = sel && refOf(sel);
  if (!ref) return toast('Pick a tile first, then <kbd>y</kbd> copies its ref for Claude');
  const text = `${location.origin}/api/what?ref=${ref}`;
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied for Claude: ' + esc(text), 3000);
  } catch {
    toast('Copy this for Claude: ' + esc(text), 8000);
  }
  track('ref.copy', { kind: ref.split(':')[1] });
}
async function newNote() {
  try {
    const r = await fetch('/api/links', { method: 'POST', body: JSON.stringify({ note: true, from: 'page' }) });
    const l = await r.json();
    if (!r.ok) return;
    addCard(l);
    editNote('link:' + l.id);
  } catch {}
}
function noteCard(pic, w) {
  const id = w.link.id;
  pic.className = 'pic card doc';
  pic.style.cssText = '';
  if (noteEdit !== 'link:' + id) {
    pic.innerHTML = `<div class="docwrap" tabindex="-1"><div class="md"></div></div>`;
    pic.querySelector('.md').innerHTML = w.link.text ? md.parse(w.link.text)
      : '<p class="gone">Empty note — Enter to write</p>';
    return;
  }
  pic.innerHTML = `<div class="docwrap" tabindex="-1"><textarea class="notetxt" spellcheck="false"></textarea></div>`;
  const ta = pic.querySelector('.notetxt');
  ta.value = w.link.text || '';
  const fit = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
  requestAnimationFrame(() => {      // grown once it is on the page; keep the caret in sight
    fit();
    if (document.activeElement === ta) ta.parentNode.scrollTop = ta.parentNode.scrollHeight;
  });
  ta.addEventListener('input', () => {
    fit();
    // the poll may have swapped the card for the server's copy: write to the live one
    noteText.set(id, ta.value);
    (links.find(v => v.id === id) || w.link).text = ta.value;
    clearTimeout(noteSave.get(id));
    noteSave.set(id, setTimeout(() => sendNote(id), 600));
  });
  ta.addEventListener('keydown', e => {
    if (e.key === 'Escape' || (e.code === 'Space' && e.ctrlKey)) { e.preventDefault(); ta.blur(); }
  });
  ta.addEventListener('blur', () => leaveNote('link:' + id));
}


// a closed issue was finished, so it is purple; a closed PR was given up, so red
const ghColor = gh => ({ open: '#1f883d', merged: '#8250df', 'not planned': '#59636e',
                         closed: gh.pr ? '#cf222e' : '#8250df' })[gh.state] || '#59636e';
const ghStates = new Map();        // card url -> {state, pr}, asked of the server
const ghOf = w => w.link.url && ghStates.get(w.link.url);

const GH_URL = /^https:\/\/github\.com\/[^/]+\/[^/]+\/(pull|issues)\/(\d+)/;

// an issue and a PR are told apart by name and number, ahead of GitHub's own
// title — which stands in for a bare host, or for the page's "… · GitHub" one
function shownTitle(w) {
  const m = w.link && GH_URL.exec(w.link.url || '');
  if (!m) return w.title;
  const gh = ghOf(w), n = '#' + m[2], kind = m[1] === 'pull' ? 'PR' : 'Issue';
  const t = w.link.title || '';
  const base = gh && gh.title && (!t || t === cardHost(w.link.url) || / · GitHub$/.test(t))
    ? gh.title : w.title;
  return new RegExp(n + '(?!\\d)').test(base) ? base : `${kind} ${n} · ${base}`;
}

async function askGitHub() {
  for (const l of links) {
    if (!GH_URL.test(l.url || '')) continue;
    try {
      const r = await fetch('/api/ghstate?url=' + encodeURIComponent(l.url));
      const st = await r.json();
      if (st) ghStates.set(l.url, st);
    } catch {}
  }
  readDiffs();                     // a PR with a new commit gets its diff again
  render();
}

// what a card shows; it is drawn again only when this changes
function cardKey(w) {
  const gh = ghOf(w);
  return w.link.tool ? 'tool ' + w.link.tool + ' ' + w.link.dir
    : w.link.image ? w.link.image
    : w.link.note ? 'note ' + (noteEdit === w.id ? 'edit' : w.link.text || '')
    : w.link.diff ? diffKey(w)
    : w.link.path ? docKey(w) : w.link.url + (gh ? ' ' + gh.state : '') + ' ' + shownTitle(w);
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
    sendCard(l, { w: l.w, h: l.h });
    w.w = l.w; w.h = l.h;
    render();
  };
  img.src = imgSrc(w.link);
}


// a tool's card is its button: press it to run the tool beside it
function toolCard(pic, w) {
  pic.className = 'pic card tool';
  pic.style.cssText = '';
  pic.innerHTML = `<button class="runbtn" title="Run ${esc(w.link.tool)} in a new terminal (or Enter)">▶ <span></span></button>`
    + `<div class="url"></div>`;
  pic.querySelector('.runbtn span').textContent = w.link.tool;
  pic.querySelector('.url').textContent = [shortPath(w.link.dir), w.link.about].filter(Boolean).join(' · ');
}

function card(pic, w) {
  if (w.link.tool) return toolCard(pic, w);
  if (w.link.image) return imgCard(pic, w);
  if (w.link.path) return docCard(pic, w);
  if (w.link.diff) return diffCard(pic, w);
  if (w.link.note) return noteCard(pic, w);
  pic.className = 'pic card';
  pic.style.cssText = '';
  // a kind this page does not know (from a newer branch) is just its title:
  // throwing here would stop every render, and with it the way into a terminal
  let u;
  try { u = new URL(w.link.url); } catch {
    pic.innerHTML = `<div class="ttl"><span></span></div>`;
    pic.querySelector('.ttl span').textContent = w.link.title || 'Card';
    return;
  }
  pic.innerHTML = `<div class="ttl"><img alt=""><span></span></div><div class="url"></div>`;
  const img = pic.querySelector('img');
  img.onerror = () => img.remove();
  img.src = u.origin + '/favicon.ico';
  pic.querySelector('.ttl span').textContent = shownTitle(w);
  pic.querySelector('.url').textContent = u.host + u.pathname;
  const gh = ghOf(w);
  if (gh) {
    const b = document.createElement('span');
    b.className = 'gh';
    b.textContent = gh.state;
    b.style.background = ghColor(gh);
    pic.querySelector('.url').prepend(b);
  }
  if (/^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+/.test(w.link.url)) {
    const b = document.createElement('button');
    b.className = 'diffbtn';
    b.title = 'Show what this PR changes, on a card beside it';
    b.textContent = 'Diff';
    pic.append(b);
  }
}

// a card the server just made, dropped at the drop point, in view, so you see
// it arrive
function addCard(l, at, placed) {      // placed: found on the server, not added here
  const w = linkWin(l);
  if (!links.includes(l)) links.push(l);
  layout[w.id] = clearSpot(at || dropAt(w.w, w.h), w.id);
  saveLayout();
  // picked if the keyboard is the page's; a terminal you are typing in keeps it
  if (!inInsert()) sel = w.id;
  if (data && !data.windows.some(v => v.id === w.id)) data.windows.push(w);
  if (l.path) readDocs();
  render();
}

// Cards that just arrived from outside pulse, and so does their mark on the
// edge, until you have had them in view for a moment, as a ping does. Kept in
// the browser, so a reload does not stop them before you have seen them.
const arrivals = new Set(store.get('arrivals', []));
const saveArrivals = () => store.set('arrivals', [...arrivals]);
function announce(id) {
  arrivals.add(id);
  saveArrivals();
}

// A card sent from outside names where it came from, or is left in the Inbox:
// beside the terminal it says (WINLIST_TERM), else in the group whose folder
// holds its cwd, the deepest folder first. Either way the view is not moved.
function arrivedCard(l) {
  const w = linkWin(l);
  const t = l.term && data.windows.find(v => v.term && v.term.session === l.term);
  const dir = p => String(p || '').replace(/\/+$/, '');
  const cwd = dir(l.cwd);
  const g = !t && cwd && groups.filter(v => v.dir && (cwd === dir(v.dir) || cwd.startsWith(dir(v.dir) + '/')))
    .sort((a, b) => dir(b.dir).length - dir(a.dir).length)[0];
  if (!t && !g) return inboxCard(l);
  if (!data.windows.some(v => v.id === w.id)) data.windows.push(w);
  let to = g, at;
  if (t) {
    const [x, y] = seatOf(t);
    to = groups.findLast(v => inGroup(v, [x, y]));
    at = [x + t.w + GRID, y];
  } else at = [g.x + GRID, g.y + GRID * 2];     // the caption takes the top row
  layout[w.id] = clearSpot(at, w.id);
  saveLayout();
  announce(w.id);
  toast(`New card ${t ? 'beside its terminal' : 'in'}${to ? ' in ' + esc(to.name) : ''}: ${esc(cardTitle(l))}`);
  if (l.path) readDocs();
  render();
}

// A card sent from outside lands in the Inbox group, newest at the top left, so
// it never covers your work. Only cards still inside it are arranged: one you
// dragged out stays where you put it. The view is not moved; a toast says so.
function inboxCard(l) {
  const w = linkWin(l);
  let g = groups.find(v => v.name === 'Inbox');
  if (!g) {
    const [, y0, x1] = bounds();
    g = { id: newId(), name: 'Inbox', x: snap(x1 + GRID * 2), y: snap(y0), w: GRID * 36, h: GRID * 12 };
    groups.push(g);
  }
  if (!data.windows.some(v => v.id === w.id)) data.windows.push(w);
  const age = v => links.findIndex(k => 'link:' + k.id === v.id);
  const mine = [w, ...members(g).filter(v => v.id !== w.id && v.link && v.link.origin === 'api')]
    .sort((a, b) => age(b) - age(a));
  let x = g.x + GRID, y = g.y + GRID * 2, row = 0;   // the caption takes the top row
  for (const v of mine) {
    if (x > g.x + GRID && x + v.w > g.x + g.w - GRID) { x = g.x + GRID; y += row + GRID; row = 0; }
    layout[v.id] = [x, y];
    x = snap(x + v.w + GRID - 1);
    row = Math.max(row, snap(v.h + GRID - 1) - GRID);
  }
  g.h = Math.max(g.h, snap(y + row + GRID * 2 - g.y));
  saveGroups();
  saveLayout();
  announce(w.id);
  toast('New card in Inbox: ' + esc(cardTitle(l)));
  if (l.path) readDocs();
  render();
}

function closeLink(id) {
  const l = links.find(v => 'link:' + v.id === id);
  if (l) sendCard(l, null);
  links = links.filter(v => v !== l);
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
      : data.shots_on ? `not photographed yet — visit workspace ${w.desktop + 1} to fill it in` : '';
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
  el.style.left = Math.round(x * zoom) + 'px';      // on whole pixels, as the surface is
  el.style.top = Math.round(y * zoom) + 'px';
  const scaled = zoom === 1 ? '' : `scale(${zoom})`;  // at 1:1 nothing is resampled at all
  if (w.husk) {                      // drawn at its saved size, scaled like a terminal
    const h = husks.get(w.husk), cap = h.t.capH;
    el.style.width = w.w * zoom + 'px';
    el.style.height = (w.h - cap) * zoom + cap + 'px';
    h.t.wrap.style.transform = scaled;
    return;
  }
  if (w.term) {
    // a terminal is drawn at its own size and scaled to match the surface, so
    // it cannot be given a floor the way a photograph can: the tile is exactly
    // as big as what is inside it
    const t = terms.get(w.term.session);
    // the caption is the one part left at screen size
    const cap = t && t.cap ? t.capH : 0;
    el.style.width = w.w * zoom + 'px';
    el.style.height = (w.h - cap) * zoom + cap + 'px';
    if (t && t.wrap) t.wrap.style.transform = scaled;
    return;
  }
  // a link card is exactly its saved size at any zoom: no screen-px floor
  const fl = isCard(w) ? 0 : 1;
  el.style.width = Math.max(90 * fl, w.w * zoom) + 'px';
  el.style.height = Math.max(60 * fl, w.h * zoom) + 'px';
  const dw = w.link && (w.link.path || w.link.note || w.link.diff) && el.querySelector('.docwrap');
  if (dw) {                          // the caption stays at screen size
    dw.style.width = w.w + 'px';
    dw.style.height = Math.max(0, Math.max(60, w.h * zoom) - CAP_H) / zoom + 'px';
    dw.style.transform = scaled;
  }
}

// The grid is only there while a window is being moved or resized. It is a
// repeating background laid over the frame, lined up with the surface's origin.
function showGrid(on) {
  const g = $('#grid');
  g.classList.toggle('on', on);
  if (!on) return;
  const step = gridStep() * zoom;
  g.style.backgroundSize = `${step}px ${step}px`;
  // a dot sits in the middle of its cell, so shift half a cell to put it on the line
  g.style.backgroundPosition = `${origin[0] - step / 2}px ${origin[1] - step / 2}px`;
}
const snap = v => Math.round(v / gridStep()) * gridStep();
// one grid line on in a direction; from a spot between lines, the next one that way
const stepTo = (v, dir) => dir > 0 ? (Math.floor(v / gridStep()) + 1) * gridStep()
                                   : (Math.ceil(v / gridStep()) - 1) * gridStep();

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
      toFront(el);                     // the one you just touched belongs on top
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
    if (moved && settle) {           // let go: its size settles on the grid too
      track('drag', { kind: kindOf(w.id) });
      fitGrid(w, el);
      place(el, w);
    }
    if (moved) { saveLayout(); if (w.husk) tellTerms(); }
    if (!settle) return;
    if (w.husk) return;              // nothing to pick or type into
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
// the face each terminal was switched to, by name, so a reload of the page or
// a restart of this server puts it back: the session outlives both, in pty_server
const faces = store.get('faces', {});   // session id -> profile name
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
    if (typeof e.data !== 'string' && !t.dead) t.term.write(new Uint8Array(e.data));
  };
  ws.onopen = () => {
    if (t.early) t.early.forEach(d => ws.send(utf8.encode(d)));
    t.early = null;
  };
  ws.onclose = () => { if (t.ws === ws) t.ws = null; };
  ws.onerror = () => { if (t.ws === ws) t.ws = null; };
}

function mount(w) {
  const id = w.term.session;
  let t = terms.get(id);
  if (t) return t;
  const l = look();
  // a profile since taken out of ~/.Xresources falls back to the default
  const prof = Math.max(0, profiles().findIndex(p => p.name === faces[id]));
  const face = profiles()[prof] || { font: l.font, size: l.size };
  const term = new Terminal({
    cols: w.term.cols, rows: w.term.rows, theme: termTheme(),
    fontFamily: termFont(face.font),
    fontSize: face.size || 13,
    // xterm.js clips each row to its cell, and a tight face like Pragmata
    // draws capitals above its own line box: at 1.0 the bar of a T is cut off
    lineHeight: 1.125,
    cursorBlink: l.blink === undefined ? true : l.blink,
    scrollback: l.scrollback || 4000,
    drawBoldTextInBrightColors: l.bold_bright === undefined ? true : l.bold_bright,
    convertEol: false, macOptionIsMeta: true,
  });
  t = { term, ws: null, wrap: null, cap: null, capH: 0, natural: null, cell: null, pad: [0, 0], read: false, title: '', prof };
  terms.set(id, t);
  // a restored terminal opens on what the old one said, then a line, then the new prompt
  const old = pendingOut.get(id);
  if (old) {
    pendingOut.delete(id);
    term.write(old);
    term.write(OUT_END + '\r\n\x1b[2m' + '─'.repeat(Math.min(w.term.cols, 40)) + ' restored\x1b[0m\r\n');
  }
  // the title the shell sets (OSC 0/2) is what a desktop terminal shows, and
  // xterm.js hears it as it streams by, well before the next poll would
  term.onRender(() => termDrew(id));
  term.onTitleChange(s => {
    t.title = s;
    if (t.cap && s) t.cap.querySelector('.t2').textContent = s;
  });
  // what you type goes straight down the socket; nothing is echoed locally,
  // because the far end is what decides what a keystroke looks like
  // keys typed before the socket is open wait for it (see connect)
  term.onData(d => {
    if (t.ws && t.ws.readyState === 1) t.ws.send(utf8.encode(d));
    else (t.early || (t.early = [])).push(d);
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
    // Super+Enter is the page's: it tiles this terminal, see tileKey
    if (tileKey(e)) return false;
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
  faces[id] = ps[t.prof].name;
  store.set('faces', faces);
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

// the state chip sits in the caption after the title, added once and then kept
function chip(el, c) {
  const cap = el.querySelector('.cap');
  let b = cap && cap.querySelector('.csb');
  if (!c) return b && b.remove();
  if (cap && !b) {
    b = document.createElement('span');
    b.className = 'csb';
    cap.querySelector('.t2').after(b);
  }
  if (b) b.textContent = c.state;
}

function projectOf(w) {
  const s = seatOf(w), c = [s[0] + w.w / 2, s[1] + w.h / 2];
  const g = groups.findLast(g => inGroup(g, c));
  if (g) return g.name;
  const last = shortPath(w.term.cwd).split('/').pop();
  return last === '~' ? '' : last;           // home says nothing about a project
}
function dressTerm(el, w) {
  const t = mount(w), id = w.term.session;
  if (!t.wrap) {
    el.innerHTML = `<div class="cap"><span class="dot"></span><span class="pre"></span><span class="app"></span><span class="t2"></span>` +
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
  const title = t.title || w.term.title || w.term.running || w.title;
  cap.querySelector('.t2').textContent = title;
  // which project it is, said for you: its group's name, else its folder's
  // last part. Worked out each render, so a tile carried into a group follows
  const pre = projectOf(w);
  cap.querySelector('.pre').textContent = pre && !title.toLowerCase().startsWith(pre.toLowerCase()) ? pre : '';
  // what is running, unless the title already says so: a shell says nothing
  const run = w.term.running || '';
  cap.querySelector('.app').textContent = run && !SHELL_NAMES.has(run)
    && !title.toLowerCase().includes(run.toLowerCase()) ? run : '';
  const note = cap.querySelector('.note');
  note.title = w.term.cwd || '';
  note.textContent = w.term.alive
    ? shortPath(w.term.cwd)
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
    if (l) { l.w = w.w; l.h = w.h; sendCard(l, { w: l.w, h: l.h }); }
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

// A new terminal opens at the drop point, and the view stays where it is: you
// zoomed in there to work there.
// Inside a group that has a folder, it starts there. With claude, the tile
// goes when Claude exits, as any ended terminal does (see the 'gone' branch above).
// A project tool brings its own command and group: it opens in the middle of
// that group unless the drop point is already inside it.
const inGroup = (g, [x, y]) => x >= g.x && x <= g.x + g.w && y >= g.y && y <= g.y + g.h;
// A tool's button says exactly where: cwd and the new tile's top-left corner.
// Anything you do while one is starting counts: a key or a press after t means
// you have moved on, and the new terminal must not take the keyboard from it.
let doneSince = 0;
addEventListener('keydown', () => doneSince++, true);
addEventListener('pointerdown', () => doneSince++, true);
async function newTerm({ claude, argv, group, cwd, corner } = {}) {
  const asked = doneSince;
  let at = corner || dropAt(0, 0);
  if (group && !inGroup(group, at)) at = [group.x + group.w / 2, group.y + group.h / 2];
  const g = group || groups.findLast(g => inGroup(g, at));
  const body = { cols: termCols(), rows: termRows() };
  if (g && g.dir) body.cwd = g.dir;
  if (cwd) body.cwd = cwd;
  if (claude) body.argv = ['claude'];
  if (argv) body.argv = argv;
  const made = await fetch('/api/terminals', { method: 'POST', body: JSON.stringify(body) })
    .then(r => r.json()).catch(() => null);
  if (!made || !made.id) return void toast('Could not start the terminal: ' + esc((made && made.error) || 'no answer from the server'), 4000);
  // the new one is picked, brought to the front and typed into at once, as a
  // new terminal window is; one a tool started is only picked: it runs its own
  // command, to be watched rather than typed into
  const pickIt = () => {
    sel = 'web:' + made.id;
    const el = tileEls.get(sel);
    if (el) $('#tiles').append(el);
    render();
    if (!argv && doneSince === asked) activate(sel);
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
  layout[w.id] = clearSpot(corner || [at[0] - w.w / 2, at[1] - w.h / 2], w.id);
  saveLayout();
  pickIt();
}

// The X answers a click, not a press: a press that moves is a pan or a drag
// that happened to start on it, and a second finger makes it a pinch. Either
// way nothing closes. Pressing it twice in a row is still a quick close.
function pressShut(e, then) {
  e.preventDefault();
  if (e.button || pointers.size > 1) return;
  const sx = e.clientX, sy = e.clientY;
  const done = ev => {
    off();
    if (letGo === done) letGo = null;
    if (ev && ev.type === 'pointerup' && Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) < 5
        && pointers.size < 2 && ev.target.closest && ev.target.closest('.shut')) then();
  };
  const move = ev => { if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) >= 5) done(); };
  const off = follow(window, move, done);
  letGo = done;                      // a pinch beginning calls it off
}

// Closing a terminal that is running something (Claude, an editor, a server)
// asks first, on the caption itself: a second click on the X, or Enter, closes;
// Esc, a click elsewhere or four seconds keep it. An idle shell closes at once.
let asking = null;
function askClose(w, el) {
  const id = w.term.session, run = w.term.running || '';
  const busy = w.term.alive && (cstate[w.id] || (run && !SHELL_NAMES.has(run)));
  if (!busy || (asking && asking.id === id)) { if (asking) asking.end(); return closeTerm(id); }
  if (asking) asking.end();
  const shut = el.querySelector('.shut');
  shut.textContent = `Close ${cstate[w.id] ? 'Claude' : run}? ✕`;
  shut.classList.add('asking');
  const key = e => {
    if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); end(); closeTerm(id); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); end(); }
  };
  const away = e => { if (!(e.target.closest && e.target.closest('.shut') === shut)) end(); };
  const timer = setTimeout(() => end(), 4000);
  const end = () => {
    clearTimeout(timer);
    removeEventListener('keydown', key, true);
    removeEventListener('pointerdown', away, true);
    shut.textContent = '✕';
    shut.classList.remove('asking');
    if (asking && asking.id === id) asking = null;
  };
  addEventListener('keydown', key, true);
  addEventListener('pointerdown', away, true);
  asking = { id, end };
}

async function closeTerm(id) {
  await fetch('/api/terminals/' + id, { method: 'DELETE' }).catch(() => {});
  delete faces[id];                          // gone for good: nothing to put back
  store.set('faces', faces);
  const t = terms.get(id);
  if (t && t.ws) t.ws.close();
  poll();
}

function renderCanvas(match) {
  if (!zoom) fitAll();                 // the first time only: after that the view is yours
  $('#zoom').value = Math.round(Math.sqrt(zoom / MAX_ZOOM) * 100);
  $('#zpct').textContent = Math.round(zoom * 100) + '%';
  placeCanvas();
  markEdges();

  const live = new Set();
  // windows that would read the same are numbered, in id order so a number
  // stays with its window from one poll to the next
  const same = new Map(), twins = new Map();
  data.windows.forEach(w => {
    if (w.term) return;
    const k = w.app + '\n' + w.title;
    same.set(k, [...(same.get(k) || []), w.id]);
  });
  same.forEach(ids => {
    if (ids.length > 1) ids.sort().forEach((id, i) => twins.set(id, '#' + (i + 1)));
  });
  data.windows.slice().sort((a, b) => a.z - b.z).forEach(w => {
    live.add(w.id);
    let el = tileEls.get(w.id);
    if (!el) {
      el = document.createElement('div');
      if (!w.term) {
        el.innerHTML = `<div class="cap"><span class="dot"></span><span class="app"></span><span class="t2"></span><span class="ord"></span>`
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
        // answered here for the same reason as a terminal's close button below
        if (e.target.closest('.runbtn')) { e.preventDefault(); e.stopPropagation(); return runTool(win.link, win); }
        if (e.target.closest('.diffbtn')) { e.preventDefault(); e.stopPropagation(); return openDiff(win); }
        if (win.term) {
          // the drag takes the pointer captive, and a captured pointer's click
          // is delivered to the tile rather than to what was under it — so the
          // close button has to be answered here, before any of that
          if (e.target.closest('.shut')) return pressShut(e, () => askClose(tileEls.get(w.id).win, el));
          if (e.target.closest('.prof')) { e.preventDefault(); return swapFace(win.term.session); }
          if (e.target.closest('.grip')) return grab(e, win, el);
          // a terminal is for typing into, so only its caption is a handle;
          // a photograph has nothing to click, so all of it is
          // — except in NORMAL, where the mouse moves windows and never types
          if (inInsert() && !e.target.closest('.cap')) return;
        } else if (win.link && e.target.closest('.grip')) {
          return grabLink(e, win, el);
        } else if (win.link && e.target.closest('.shut')) {
          return pressShut(e, () => closeLink(win.id));
        } else if (inInsert()) {
          return;                // in INSERT a photograph is just more surface: it pans
        }
        drag(e, win, el);
      });
      if (w.link) el.addEventListener('dblclick', e => {
        if (!e.target.closest('.shut, .grip')) activate(w.id);
      });
      // a terminal is typed into on a double click, as Enter does: the one
      // click only picks it. Once it has the keyboard, a double click in it
      // is xterm's again, to select a word
      if (w.term) el.addEventListener('dblclick', e => {
        if (!inInsert() && !e.target.closest('.shut, .grip, .prof')) activate(w.id);
      });
      tileEls.set(w.id, el);
      $('#tiles').append(el);
    }
    el.win = w;                       // the drag handler always wants the fresh one
    el.className = 'tile' + (w.term ? ' term' : '') + (w.link ? ' link' : '') + (w.focused ? ' focused' : '')
      + (match(w) ? '' : ' off') + (w.id === sel ? ' sel' : '') + (pings.has(w.id) ? ' ping' : '') + (arrivals.has(w.id) ? ' arrive' : '')
      + (cstate[w.id] ? ' cs-' + cstate[w.id].state : '');
    if (w.term) {
      el.title = [w.term.running, w.term.cwd, w.title].filter(Boolean).join(' — ') + ` · pid ${w.pid}`;
      dressTerm(el, w);
    } else {
      el.title = `${w.app} — ${w.title} · workspace ${w.desktop + 1}`;
      el.querySelector('.dot').style.background = colorOf(w.app);
      el.querySelector('.t2').textContent = shownTitle(w);
      // the app is named in words, not only by the dot's colour — unless the
      // title says it already, or it is a card, whose title is what it is
      el.querySelector('.app').textContent = !w.link && w.app
        && !w.title.toLowerCase().startsWith(w.app.toLowerCase()) ? w.app : '';
      el.querySelector('.ord').textContent = twins.get(w.id) || '';
      if (w.link) {
        el.title = w.link.url || w.link.path || w.link.image || w.link.diff || 'Tool: ' + w.link.tool;
        const gh = ghOf(w), key = cardKey(w);
        if (gh) el.querySelector('.dot').style.background = ghColor(gh);
        const pic = el.children[1];          // the grip comes after it
        if (pic.dataset.key !== key) {
          card(pic, w);
          pic.dataset.key = key;
        }
      } else dress(el.lastElementChild, w);
    }
    chip(el, cstate[w.id]);          // after dressing: a new terminal has no caption before
    place(el, w);
  });
  tileEls.forEach((el, id) => {
    if (live.has(id)) return;
    tileEls.delete(id);               // first: removing it can blur a note, which renders again
    el.remove();
    const t = terms.get(id.slice(4));         // a session that has gone for good
    if (id.startsWith('web:') && t) {
      // bytes already on their way still arrive after close(), and a write
      // to a disposed xterm.js throws once it tries to scroll
      t.dead = true;
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
  syncLens();
  aimLens();
}

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
  if (zoom > 0.3 && e.target.closest('.docwrap, .husk .termhost')) return;   // a document, or a husk's output, scrolls
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
  if (!inInsert() || e.target.closest('#map')) return;   // the map keeps your place
  const tile = e.target.closest('.tile');
  const here = document.activeElement || document.body;
  if (tile && tile === here.closest('.tile')) return;
  e.preventDefault();
  here.blur();
  showMode();                        // now, not after focusout's tick: the tile's
}, true);                            // own handler below has to see NORMAL

$('#pan').addEventListener('pointerdown', e => {
  if (!carries(e) || pointers.size > 1) return;   // one finger drags, two pinch
  const pan = $('#pan'), sx = e.clientX, sy = e.clientY;
  let px = sx, py = sy, far = false;
  pan.classList.add('grabbing');
  const move = ev => {
    if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) >= 5) far = true;
    shift(ev.clientX - px, ev.clientY - py); px = ev.clientX; py = ev.clientY;
  };
  // a press that did not carry the surface anywhere picks the drop point
  const done = ev => {
    if (ev && ev.type === 'pointerup' && !far && pointers.size < 2) setAnchor(ev.clientX, ev.clientY);
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

// to the front: moving a node in the document sets what scrolls inside it back
// to the top, so a document card keeps its place across the move (and is not
// moved at all when it is in front already)
function toFront(el) {
  const box = $('#tiles');
  if (!el || box.lastElementChild === el) return;
  const dw = el.querySelector('.docwrap'), at = dw && [dw.scrollTop, dw.scrollLeft];
  box.append(el);
  if (at) [dw.scrollTop, dw.scrollLeft] = at;
}

async function activate(id) {
  sel = id;
  toFront(tileEls.get(id));            // focusing it brings it to the front, as a drag does
  render();
  if (id.startsWith('link:')) {
    const w = data.windows.find(x => x.id === id);
    if (w && w.link.note) return editNote(id);
    const dw = w && (w.link.path || w.link.diff) && tileEls.get(id) && tileEls.get(id).querySelector('.docwrap');
    if (dw) dw.focus({ preventScroll: true });        // into the document: INSERT
    else if (w && w.link.tool) runTool(w.link, w);
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
  try {
    const r = await fetch('/api/focus', { method: 'POST', body: JSON.stringify({ id }) });
    const a = await r.json();
    const w = data.windows.find(x => x.id === id);
    if (!a.ok) toast(`Could not focus it: ${esc(a.msg || a.error || String(r.status))}`);
    else if (w && w.desktop !== data.current) toast(`Switched to workspace ${w.desktop + 1}`, 1500);
  } catch { toast('Could not reach the server to focus it'); }
  poll();
}

// ---- keyboard picking -----------------------------------------------------
// PgUp/PgDn read the picked tile without going into it: a terminal's
// scrollback, or a document, note or diff a page at a time
function scrollPicked(dir) {
  const w = selected();
  if (!w) return;
  const h = w.husk && husks.get(w.husk), t = w.term ? terms.get(w.term.session) : h && !h.dead ? h.t : null;
  if (t && t.term) return t.term.scrollPages(dir);
  const dw = tileEls.get(w.id) && tileEls.get(w.id).querySelector('.docwrap');
  if (dw) return dw.scrollBy(0, dir * dw.clientHeight * 0.9);
  if (!w.link) toast('A desktop window scrolls once it has the keyboard: <kbd>Enter</kbd>', 2000);
}
function selected() {
  if (!data) return null;
  return data.windows.find(w => w.id === sel) || null;
}

function reveal() {
  if (!sel) return;
  const w = data.windows.find(x => x.id === sel);
  const pan = $('#pan');
  if (!w || !pan.clientWidth) return;
  const [x, y] = seatOf(w);
  // already in view: leave the view alone, it is where you put it
  const l = origin[0] + x * zoom, t = origin[1] + y * zoom;
  if (l >= 0 && t >= 0 && l + w.w * zoom <= pan.clientWidth && t + w.h * zoom <= pan.clientHeight) return;
  // otherwise bring the pick to the middle
  origin = [pan.clientWidth / 2 - (x + w.w / 2) * zoom,
            pan.clientHeight / 2 - (y + w.h / 2) * zoom];
  store.set('origin', origin);
  placeCanvas();
  markEdges();
}

function move(dx, dy) {
  const match = visible();
  const pick = data.windows.filter(match);
  if (!pick.length) return;
  const cur = selected();
  // the first pick is the window you were last in, if it is one of these
  if (!cur) { sel = (pick.find(w => w.focused) || pick[0]).id; return (render(), reveal()); }

  if (dx && !dy) {                       // left and right: the nearest tile that way, as seen
    const mid = v => { const [x, y] = seatOf(v); return [x + v.w / 2, y + v.h / 2]; };
    const [cx, cy] = mid(cur);
    let best = null, score = Infinity;
    pick.forEach(v => {
      if (v.id === cur.id) return;
      const [x, y] = mid(v), ahead = (x - cx) * dx;
      if (ahead <= 1) return;
      const sc = ahead + 2 * Math.abs(y - cy);   // straight across beats nearer but off to the side
      if (sc < score) { score = sc; best = v; }
    });
    if (best) { sel = best.id; return (render(), reveal()); }
  }
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
  document.body.classList.toggle('tiling', editing === 'tile');
  // the keys of the mode you are in, on screen while you are in it
  const legend = editing ? '<kbd>←↑↓→</kbd> move a cell · <kbd>Shift</kbd>+arrows size · <kbd>Enter</kbd> / <kbd>Esc</kbd> done'
    : typing ? '<kbd>Ctrl+Space</kbd> back to the surface · <kbd>Super+Enter</kbd> move/size this one' : '';
  $('#legend').innerHTML = legend;
  $('#legend').classList.toggle('on', !!legend);
}

// Moving and sizing from the keyboard is a mode of its own inside NORMAL,
// entered with Super+Enter: hjkl step the picked window one grid cell, Shift
// with them sizes it, Enter or Esc leaves.
let editing = null;       // 'tile' | null
function edit(how) {
  if (!selected()) return;
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
  if (editBack) activate(editBack);
  editBack = null;
}
// Moved on the grid, by key or by drag, a tile takes the nearest size on it too, so its far
// edges line up with the next tile's as well as its corner: a card exactly, a
// terminal to the character, a photograph by its width, keeping its shape.
function fitGrid(w, el) {
  if (w.husk) return;                // its size is its old screen's
  const g = gridStep(), [x, y] = seatOf(w);
  const ww = Math.max(g, snap(w.w)), hh = Math.max(g, snap(w.h));
  if (w.link) {
    w.w = Math.max(90, ww);
    w.h = Math.max(60, hh);
    const l = links.find(v => 'link:' + v.id === w.id);
    if (l) { l.w = w.w; l.h = w.h; sendCard(l, { w: l.w, h: l.h }); }
  } else if (w.term) {
    const t = terms.get(w.term.session);
    if (t && t.cell && w.term.alive) resizeTo(w, el, t, [x + ww, y + hh]);
  } else {
    const s0 = scales[w.id] || 1, s = ww / (w.w / s0);
    w.w = w.w / s0 * s;
    w.h = w.h / s0 * s;
    if (Math.abs(s - 1) < 0.001) delete scales[w.id]; else scales[w.id] = s;
    saveArrange();
  }
}
function nudge(dx, dy, grow) {
  const w = selected(), el = w && tileEls.get(w.id);
  if (!el) return endEdit();
  const [x, y] = seatOf(w);
  if (!grow) {
    layout[w.id] = [dx ? stepTo(x, dx) : snap(x), dy ? stepTo(y, dy) : snap(y)];
    fitGrid(w, el);
    place(el, w);
    return;
  }
  if (!layout[w.id]) layout[w.id] = [x, y];   // sized where it stands, not re-seated
  if (w.link) {
    w.w = Math.max(90, dx ? stepTo(x + w.w, dx) - x : w.w);
    w.h = Math.max(60, dy ? stepTo(y + w.h, dy) - y : w.h);
    place(el, w);
    const l = links.find(v => 'link:' + v.id === w.id);
    if (l) { l.w = w.w; l.h = w.h; sendCard(l, { w: l.w, h: l.h }); }
    return;
  }
  if (!w.term) {                     // a photograph: the edge you step, the other follows
    const s0 = scales[w.id] || 1;
    const s = dx ? Math.max(90, stepTo(x + w.w, dx) - x) / (w.w / s0)
                 : Math.max(60, stepTo(y + w.h, dy) - y) / (w.h / s0);
    w.w = w.w / s0 * s;
    w.h = w.h / s0 * s;
    if (Math.abs(s - 1) < 0.001) delete scales[w.id]; else scales[w.id] = s;
    saveArrange();
    place(el, w);
    return;
  }
  const t = terms.get(w.term.session);
  if (!t || !t.cell || !w.term.alive) return;
  // the edge sits half a character either side of a grid line, so the next
  // line can be too close to change the count: keep going until it does
  let edge = [x + w.w, y + w.h];
  for (let i = 0; i < 8; i++) {
    edge = [dx ? stepTo(edge[0], dx) : edge[0], dy ? stepTo(edge[1], dy) : edge[1]];
    if (resizeTo(w, el, t, edge)) break;
  }
}
// pan, never zoom, just far enough that the tile in hand is back in the frame
function keepInView() {
  const w = selected(), pan = $('#pan');
  if (!w) return;
  const [x, y] = seatOf(w), m = GRID * zoom;
  const fit = (o, at, len, view) => {  // how far to slide along one axis
    const lo = o + at * zoom, hi = lo + len * zoom;
    return lo < m || hi + m > view && len * zoom + 2 * m > view ? m - lo
      : hi + m > view ? view - m - hi : 0;
  };
  const dx = fit(origin[0], x, w.w, pan.clientWidth), dy = fit(origin[1], y, w.h, pan.clientHeight);
  if (dx || dy) shift(dx, dy);
}
// Super+Enter moves and sizes, the way gTile's keys do: the arrows move the
// tile a grid cell, Shift with them sizes it, Enter or Esc leaves. Typing in a
// terminal or a document when you asked, you are handed back to it after.
let scales = store.get('scales', {});      // window id -> how much its photo is scaled
let editBack = null;                       // the tile to type into again once done
const tileKey = e => e.key === 'Enter' && e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey;
function startTile(w) {
  const typing = document.activeElement && document.activeElement.closest('.termhost, .docwrap');
  if (typing) typing.closest('.docwrap') ? document.activeElement.blur() : terms.get(w.id.slice(4))?.term.blur();
  sel = w.id;
  render();
  editBack = typing ? w.id : null;
  edit('tile');
}

document.addEventListener('focusin', showMode);
document.addEventListener('focusout', () => setTimeout(showMode));
showMode();

document.addEventListener('keydown', e => {
  if (tileKey(e)) {                  // the tile you are in, or the one picked
    const w = (e.target.closest && e.target.closest('.tile') || {}).win || selected();
    e.preventDefault();
    if (editing) return endEdit();
    const v = w || data && data.windows.find(x => x.focused && visible()(x));
    if (v) return startTile(v);
    return toast('Pick a window first: <kbd>↑↓←→</kbd>, then <kbd>Super+Enter</kbd>');
  }
  if (e.target.tagName === 'TEXTAREA') return;   // a terminal has the keyboard
  const doc = e.target.closest && e.target.closest('.docwrap');
  if (doc) {                         // a document has it: it scrolls, Esc leaves
    if (e.key === 'Escape' || (e.code === 'Space' && e.ctrlKey)) { e.preventDefault(); doc.blur(); return; }
    const by = { j: 40, k: -40, d: doc.clientHeight / 2, u: -doc.clientHeight / 2 }[e.key];
    // sideways for a long diff or code line, as in vi: hl a step, 0 $ the ends
    const across = { h: -80, l: 80 }[e.key], end = { 0: 0, $: doc.scrollWidth }[e.key];
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (by) { e.preventDefault(); doc.scrollBy(0, by); }
    else if (across) { e.preventDefault(); doc.scrollBy(across, 0); }
    else if (end !== undefined) { e.preventDefault(); doc.scrollLeft = end; }
    return;                          // arrows, PgUp/PgDn, Space and Shift+wheel scroll on their own
  }
  if (e.target.tagName === 'INPUT') {
    if (e.key === 'Escape') { e.target.value = ''; e.target.blur(); sel = null; render(); }
    if (e.key === 'Enter' && e.target.id === 'q') {     // to the first match, keys on the surface
      const first = data && data.windows.find(visible());
      e.target.blur();
      if (first) { sel = first.id; render(); reveal(); }
    }
    return;
  }
  const k = e.key;
  if (helpbox.open) {
    if (e.key === '?' && e.target.id !== 'helpq') { e.preventDefault(); helpbox.close(); }
    return;
  }
  if (archbox.open) return;
  if (editing) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    e.preventDefault();
    if (k === 'Escape' || k === 'Enter') return endEdit();
    const step = { ArrowUp: [0, -1], k: [0, -1], ArrowDown: [0, 1], j: [0, 1],
                   ArrowLeft: [-1, 0], h: [-1, 0], ArrowRight: [1, 0], l: [1, 0] }[k.length === 1 ? k.toLowerCase() : k];
    if (step) { nudge(...step, e.shiftKey); keepInView(); }
    return;
  }
  // the page's own keys are bare letters: anything held with them is the browser's
  if (e.ctrlKey || e.altKey || e.metaKey) return;              // the dialog handles its own Esc
  if (k === 'a') { e.preventDefault(); return showArch(); }
  if (k === '?') { e.preventDefault(); return showHelp(); }
  if (k === ':') { e.preventDefault(); return showPalette(); }
  if (k === '/') { e.preventDefault(); openQ(); return; }
  if (k === 'Escape') {
    if ($('#q').value || sel) { $('#q').value = ''; foldQ(); sel = null; return render(); }
    return bare ? undefined : setBare(true);
  }
  if (k === 'b') { e.preventDefault(); return setBare(!bare); }
  if (k === 't') { e.preventDefault(); return void newTerm(); }
  if (k === 'c') { e.preventDefault(); return void newTerm({ claude: true }); }
  if (k === 'u') { e.preventDefault(); return askLink(); }
  if (k === 'o') { e.preventDefault(); return askDoc(); }
  if (k === 'p') { e.preventDefault(); return askImage(); }
  if (k === 'n') { e.preventDefault(); return void newNote(); }
  if (k === 'y') { e.preventDefault(); return void copyRef(); }
  if (k === 'g') { e.preventDefault(); return newGroup(); }
  if (k === '1') { e.preventDefault(); return actualSize(); }
  if (k === 'z') { e.preventDefault(); return setLens(!lensOn); }
  if (k === 'm') { e.preventDefault(); return setMap(!mapPinned); }
  if (k === 'Enter' || k === ' ') { const w = selected(); if (w) { e.preventDefault(); activate(w.id); } return; }
  if (k === 'PageUp' || k === 'PageDown') { e.preventDefault(); return scrollPicked(k === 'PageUp' ? -1 : 1); }
  const moves = { ArrowUp: [0, -1], k: [0, -1], ArrowDown: [0, 1], j: [0, 1],
                  ArrowLeft: [-1, 0], h: [-1, 0], ArrowRight: [1, 0], l: [1, 0] };
  if (moves[k]) { e.preventDefault(); move(...moves[k]); }
});

setBare(bare);
setLens(lensOn);
render();
moveCardsOut().finally(() => { poll(); setInterval(poll, 2000); });
askGitHub();
setInterval(askGitHub, 60000);
readDocs();
setInterval(readDocs, 2000);

// ---- usage: what the page is used for, to tell whether a change helped ------
// Names and counts only: which action, on what kind of tile, in which mode —
// never a title, a URL, or anything typed into a terminal. Batched, and sent
// when the page is let go of, to /api/usage; usage_report.py reads it back.
const usage = [], session = newId();
const nolog = navigator.webdriver || /[?&]nolog\b/.test(location.search);    // a robot or ?nolog is not use
const kindOf = id => !id ? 'none' : id.startsWith('web:') ? 'term' : id.startsWith('husk:') ? 'husk'
  : id.startsWith('link:') ? 'card' : 'window';
function track(ev, props) {
  if (nolog) return;
  usage.push({ ev, t: Date.now(), s: session, ...props });
  if (usage.length >= 200) sendUsage();
}
function sendUsage(leaving) {
  if (!usage.length) return;
  const body = JSON.stringify(usage.splice(0));
  if (leaving && navigator.sendBeacon) navigator.sendBeacon('/api/usage', body);
  else fetch('/api/usage', { method: 'POST', body, keepalive: true }).catch(() => {});
}
setInterval(sendUsage, 30000);
addEventListener('pagehide', () => { track('close'); sendUsage(true); });
track('open', { vw: innerWidth, vh: innerHeight, bare, zoom: Math.round(zoom * 100) });

// the page's own keys, as the page has them: in a terminal or a box only the
// few that belong to the page are counted, never what is typed
// A key the page does nothing with is counted as 'other', with no character:
// a row of them would spell out whatever was being typed
const PAGE_KEYS = new Set(['a', '?', ':', '/', 'Escape', 'b', 't', 'c', 'u', 'o', 'p', 'n', 'y', 'g', '1', 'z', 'm',
  'Enter', ' ', 'h', 'j', 'k', 'l', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown']);
document.addEventListener('keydown', e => {
  // a box is anything that takes text: a group's name and folder are edited in
  // place (contenteditable), and a dialog's keys are its own
  const typing = e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' || !!e.target.isContentEditable
    || !!(e.target.closest && e.target.closest('.docwrap, [contenteditable=""], [contenteditable="true"], dialog[open], [role=dialog], [role=menu]'));
  const mods = (e.ctrlKey ? 'C-' : '') + (e.altKey ? 'A-' : '') + (e.metaKey ? 'S-' : '')
    + (e.shiftKey && e.key.length > 1 ? 's-' : '');
  const page = tileKey(e) || (e.code === 'Space' && e.ctrlKey) || (e.code === 'KeyF' && e.ctrlKey && e.altKey);
  if (typing && !page) return;
  if (!typing && (e.ctrlKey || e.altKey) && !page) return;      // the browser's
  if (['Shift', 'Control', 'Alt', 'Meta'].includes(e.key)) return;
  const k = page || PAGE_KEYS.has(e.key) ? mods + (e.key === ' ' ? 'Space' : e.key) : 'other';
  track('key', { k, mode: editing || (typing ? 'insert' : 'normal') });
}, true);

// each of these is a thing done, counted where it is done, whichever way it came
// (props may answer null: not one of yours, as the first fit is the page's own)
const counted = (ev, f, props) => function (...a) {
  const p = props ? props(...a) : {};
  if (p) track(ev, p);
  return f.apply(this, a);
};
activate = counted('activate', activate, id => ({ kind: kindOf(id) }));
newTerm = counted('term.new', newTerm);
closeTerm = counted('term.close', closeTerm);
// a card the poll finds unplaced is placed again every poll until the server holds it: not an add
addCard = counted('card.add', addCard, (f, at, placed) => placed ? null : { kind: f.image ? 'image' : f.path ? 'doc' : f.note ? 'note' : 'url' });
closeLink = counted('card.close', closeLink);
newGroup = counted('group.new', newGroup);
actualSize = counted('actual', actualSize);
setLens = counted('lens', setLens, v => ({ on: !!v }));
setBare = counted('bare', setBare, v => ({ on: !!v }));
swapFace = counted('face', swapFace);
runPal = counted('palette', runPal, r => ({ kind: r.kind }));
const nudged = { n: 0, grow: 0, at: 0 };
nudge = (f => function (dx, dy, grow) {      // counted into the tile.end it belongs to
  nudged.n++;
  if (grow) nudged.grow++;
  return f.apply(this, arguments);
})(nudge);
startTile = counted('tile.start', startTile, w => {
  Object.assign(nudged, { n: 0, grow: 0, at: Date.now() });
  return { kind: kindOf(w.id), from: inInsert() ? 'insert' : 'normal' };
});
endEdit = counted('tile.end', endEdit, () => ({ steps: nudged.n, grow: nudged.grow,
  ms: nudged.at ? Date.now() - nudged.at : 0 }));
// a zoom is a gesture, not each wheel notch: counted once it comes to rest
let zoomRest = 0;
zoomAbout = (f => function (...a) {
  clearTimeout(zoomRest);
  zoomRest = setTimeout(() => track('zoom', { z: Math.round(zoom * 100) }), 800);
  return f.apply(this, a);
})(zoomAbout);
let filterRest = 0;
$('#q').addEventListener('input', () => {
  clearTimeout(filterRest);
  filterRest = setTimeout(() => track('filter', { len: $('#q').value.length }), 1000);
});
[[helpbox, 'help'], [archbox, 'arch']].forEach(([box, ev]) => new MutationObserver(() => {
  if (box.open) track(ev);
}).observe(box, { attributes: true, attributeFilter: ['open'] }));
$('#reset').addEventListener('click', () => track('reset'));
