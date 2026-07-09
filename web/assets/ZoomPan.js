// Mouse-wheel + pinch zoom (toward the pointer) and drag-to-pan for the canvas.
// The whole page body is the canvas: transform = translate(pan) scale(zoom).
// BoxDrag reads window.canvasScale to keep box dragging correct while zoomed.
$(function () {

    var MIN = 0.2, MAX = 3;
    var scale = 1, panX = 0, panY = 0;
    var body = document.body;

    function clamp(s) { return Math.max(MIN, Math.min(MAX, s)); }

    function apply() {
        body.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + scale + ')';
        window.canvasScale = scale;
    }
    body.style.transformOrigin = '0 0';
    window.canvasScale = 1;
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

    document.addEventListener('wheel', function (e) {
        e.preventDefault();
        zoomAt(Math.pow(1.0015, -e.deltaY), e.clientX, e.clientY);
    }, { passive: false });

    // pinch to zoom toward the midpoint of two touches
    var pinch = null;
    function twoTouch(t) {
        var a = t[0], b = t[1], dx = a.clientX - b.clientX, dy = a.clientY - b.clientY;
        return { dist: Math.sqrt(dx * dx + dy * dy),
                 x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    }
    document.addEventListener('touchstart', function (e) {
        if (e.touches.length === 2) { pinch = twoTouch(e.touches); }
    }, { passive: false });
    document.addEventListener('touchmove', function (e) {
        if (e.touches.length === 2 && pinch) {
            e.preventDefault();
            var t = twoTouch(e.touches);
            zoomAt(t.dist / pinch.dist, t.x, t.y);
            pinch = t;
        }
    }, { passive: false });
    document.addEventListener('touchend', function (e) { if (e.touches.length < 2) { pinch = null; } });

    // drag empty space to pan (drags that start on a box move the box instead)
    var pan = null;
    $(document).on('pointerdown', function (e) {
        var oe = e.originalEvent;
        if (oe.button && oe.button !== 0) { return; }
        if (e.target.closest && e.target.closest('.box')) { return; }
        pan = { x: oe.clientX, y: oe.clientY, panX: panX, panY: panY };
        body.style.cursor = 'grabbing';
    });
    $(document).on('pointermove', function (e) {
        if (!pan || pinch) { return; }        // don't pan while pinch-zooming
        var oe = e.originalEvent;
        panX = pan.panX + (oe.clientX - pan.x);
        panY = pan.panY + (oe.clientY - pan.y);
        apply();
    });
    $(document).on('pointerup pointercancel', function () {
        if (pan) { pan = null; body.style.cursor = ''; }
    });

});
