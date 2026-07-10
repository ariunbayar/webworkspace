// Mouse-wheel + pinch zoom (toward the pointer) and drag-to-pan for the canvas.
// The whole page body is the canvas: transform = translate(pan) scale(zoom).
// BoxDrag reads window.canvasScale to keep box dragging correct while zoomed.
$(function () {

    var MIN = 0.2, MAX = 3;
    var GRID = (window.Constants && Constants.gridSize) || 30;
    var scale = 1, panX = 0, panY = 0;
    var body = document.body;

    function clamp(s) { return Math.max(MIN, Math.min(MAX, s)); }

    // Adaptive grid: cell size doubles/halves with zoom so the on-screen spacing
    // stays ~GRID px. gridStep = GRID * 2^round(log2(1/scale)). Snapping follows it.
    function gridStepFor(s) {
        var k = Math.round(Math.log(1 / s) / Math.LN2);
        return GRID * Math.pow(2, k);
    }

    // Live stats panel pinned to the viewport's bottom-right. It must live
    // outside the transformed <body> — position:fixed inside a transformed
    // ancestor is relative to that ancestor, not the viewport — so attach it to
    // <html>. Rows update from the zoom/pan math, pointer moves, and a
    // MutationObserver watching box style/class changes (move/resize/select).
    var ROWS = [
        ['zoom', 'zoom'], ['cursor', 'cursor'], ['mode', 'mode'],
        ['selected', 'file'], ['box', 'box'], ['action', 'action']
    ];
    var panel = document.createElement('div');
    panel.id = 'statsPanel';
    var cells = {};
    ROWS.forEach(function (r) {
        var row = document.createElement('div'); row.className = 'stat-row';
        var k = document.createElement('span'); k.className = 'stat-key'; k.textContent = r[1];
        var v = document.createElement('span'); v.className = 'stat-val'; v.textContent = '—';
        row.appendChild(k); row.appendChild(v); panel.appendChild(row);
        cells[r[0]] = v;
    });
    document.documentElement.appendChild(panel);
    function setStat(k, v) { if (cells[k]) { cells[k].textContent = v; } }

    function apply() {
        body.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + scale + ')';
        window.canvasScale = scale;
        var step = gridStepFor(scale);
        window.canvasGridStep = step;
        var grid = document.getElementById('dragGrid');
        if (grid) { grid.style.backgroundSize = step + 'px ' + step + 'px'; }
        setStat('zoom', Math.round(scale * 100) + '%');
    }
    body.style.transformOrigin = '0 0';
    window.canvasScale = 1;
    window.canvasGridStep = GRID;
    apply();

    // zoom by `factor`, keeping the screen point (cx, cy) pinned to its content
    function zoomAt(factor, cx, cy) {
        var ns = clamp(scale * factor);
        if (ns === scale) { return; }
        var contentX = (cx - panX) / scale;
        var contentY = (cy - panY) / scale;
        scale = ns;
        panX = cx - contentX * scale;
        panY = cy - contentY * scale;
        apply();
    }

    // hide the outline while interacting (pan/zoom), show it again at rest
    var mergeTimer = null;
    function pauseMerge() {
        if (window.Utility) { Utility.showOutline(false); }
        if (mergeTimer) { clearTimeout(mergeTimer); mergeTimer = null; }
    }
    function resumeMergeSoon() {
        if (mergeTimer) { clearTimeout(mergeTimer); }
        mergeTimer = setTimeout(function () {
            if (window.Utility) { Utility.showOutline(true); }
        }, 200);
    }

    document.addEventListener('wheel', function (e) {
        e.preventDefault();
        pauseMerge();
        zoomAt(Math.pow(1.0015, -e.deltaY), e.clientX, e.clientY);
        resumeMergeSoon();
    }, { passive: false });

    // pinch to zoom toward the midpoint of two touches
    var pinch = null;
    function twoTouch(t) {
        var a = t[0], b = t[1], dx = a.clientX - b.clientX, dy = a.clientY - b.clientY;
        return { dist: Math.sqrt(dx * dx + dy * dy),
                 x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    }
    document.addEventListener('touchstart', function (e) {
        if (e.touches.length === 2) { pinch = twoTouch(e.touches); pauseMerge(); }
    }, { passive: false });
    document.addEventListener('touchmove', function (e) {
        if (e.touches.length === 2 && pinch) {
            e.preventDefault();
            var t = twoTouch(e.touches);
            zoomAt(t.dist / pinch.dist, t.x, t.y);
            pinch = t;
        }
    }, { passive: false });
    document.addEventListener('touchend', function (e) {
        if (e.touches.length < 2) { pinch = null; resumeMergeSoon(); }
    });

    // drag empty space to pan (drags that start on a box move the box instead)
    var pan = null;
    $(document).on('pointerdown', function (e) {
        var oe = e.originalEvent;
        if (oe.button && oe.button !== 0) { return; }
        if (e.target.closest && e.target.closest('.box')) { return; }
        pan = { x: oe.clientX, y: oe.clientY, panX: panX, panY: panY };
        body.style.cursor = 'grabbing';
        pauseMerge();
    });
    $(document).on('pointermove', function (e) {
        if (!pan || pinch) { return; }        // don't pan while pinch-zooming
        var oe = e.originalEvent;
        panX = pan.panX + (oe.clientX - pan.x);
        panY = pan.panY + (oe.clientY - pan.y);
        apply();
    });
    $(document).on('pointerup pointercancel', function () {
        if (pan) { pan = null; body.style.cursor = ''; resumeMergeSoon(); }
    });

    // ---- live stats: mode, selection, and move/resize action ----
    var dragSnap = null;   // box geometry captured when a drag begins
    function refresh() {
        setStat('mode', (window.mainView && mainView.currentMode === 'MODE_EDIT') ? 'edit' : 'normal');

        // a box mid-drag reports live geometry from the DOM (the model only
        // updates on release), and whether it's moving or resizing
        var dragging = document.querySelector('.box.dragging');
        if (dragging) {
            var w = dragging.offsetWidth, h = dragging.offsetHeight;
            var x = dragging.offsetLeft, y = dragging.offsetTop;
            if (!dragSnap) { dragSnap = { w: w, h: h }; }
            setStat('action', (w !== dragSnap.w || h !== dragSnap.h) ? 'resizing' : 'moving');
            setStat('box', w + ' × ' + h + '  @ ' + x + ', ' + y);
            return;
        }
        dragSnap = null;
        setStat('action', 'idle');

        // at rest, report the selected box from its model
        var m = window.mainView && mainView.currentModel;
        if (m) {
            setStat('selected', m.get('filename') || '(browser)');
            setStat('box', Math.round(m.get('width')) + ' × ' + Math.round(m.get('height')) +
                           '  @ ' + Math.round(m.get('left')) + ', ' + Math.round(m.get('top')));
        } else {
            setStat('selected', 'none');
            setStat('box', '—');
        }
    }

    // cursor position in content coords (undo pan/zoom)
    document.addEventListener('mousemove', function (e) {
        setStat('cursor', Math.round((e.clientX - panX) / scale) + ', ' +
                          Math.round((e.clientY - panY) / scale));
    });

    // box style/class changes = move/resize/select/mode switch -> refresh
    new MutationObserver(refresh).observe(document.body, {
        attributes: true, attributeFilter: ['style', 'class'], subtree: true
    });
    refresh();

});
