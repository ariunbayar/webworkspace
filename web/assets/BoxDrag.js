// Mouse/touch drag-to-move and corner-resize for workspace boxes.
// Uses Pointer Events (mouse + touch + pen). On release, positions/sizes snap
// to the grid and are written to the Backbone model, which autosaves.
$(function () {

    var GRID = (window.Constants && Constants.gridSize) || 30;
    var HANDLE = 18;            // bottom-right region (px) that starts a resize
    var THRESHOLD = 3;          // movement under this counts as a click, not a drag
    var MIN_W = 60, MIN_H = 40;
    var topZ = 100;
    var drag = null;

    function snap(v) { return Math.round(v / GRID) * GRID; }

    // the Backbone model whose rendered box is this DOM element
    function modelForBox(boxEl) {
        if (!window.mainCollection) { return null; }
        return mainCollection.find(function (m) {
            return m.view && m.view.$el && m.view.$el[0] === boxEl;
        });
    }

    $(document).on('pointerdown', '.box', function (e) {
        var oe = e.originalEvent;
        if (oe.button && oe.button !== 0) { return; }   // primary button / touch only
        var boxEl = e.currentTarget;
        var model = modelForBox(boxEl);
        if (!model) { return; }

        var rect = boxEl.getBoundingClientRect();
        var isResize = (oe.clientX - rect.left) >= rect.width - HANDLE
                    && (oe.clientY - rect.top) >= rect.height - HANDLE;

        drag = {
            model: model, el: boxEl, resize: isResize, moved: false,
            startX: oe.clientX, startY: oe.clientY,
            top: model.get('top'), left: model.get('left'),
            width: model.get('width'), height: model.get('height')
        };

        if (window.mainView && mainView.switchTo) { mainView.switchTo(model); }
        boxEl.style.zIndex = ++topZ;
        boxEl.classList.add('dragging');
        try { boxEl.setPointerCapture(oe.pointerId); } catch (err) {}
        e.preventDefault();
    });

    $(document).on('pointermove', function (e) {
        if (!drag) { return; }
        var oe = e.originalEvent;
        var dx = oe.clientX - drag.startX;
        var dy = oe.clientY - drag.startY;
        if (!drag.moved && Math.abs(dx) + Math.abs(dy) > THRESHOLD) { drag.moved = true; }
        if (!drag.moved) { return; }

        if (drag.resize) {
            drag.el.style.width  = Math.max(MIN_W, snap(drag.width  + dx)) + 'px';
            drag.el.style.height = Math.max(MIN_H, snap(drag.height + dy)) + 'px';
        } else {
            drag.el.style.left = snap(drag.left + dx) + 'px';
            drag.el.style.top  = snap(drag.top  + dy) + 'px';
        }
    });

    $(document).on('pointerup pointercancel', function (e) {
        if (!drag) { return; }
        var d = drag;
        drag = null;
        d.el.classList.remove('dragging');

        if (!d.moved) { return; }   // a click: selection already handled, don't move

        var oe = e.originalEvent;
        var dx = oe.clientX - d.startX;
        var dy = oe.clientY - d.startY;
        if (d.resize) {
            d.model.set({
                width:  Math.max(MIN_W, snap(d.width  + dx)),
                height: Math.max(MIN_H, snap(d.height + dy))
            });
        } else {
            d.model.set({ left: snap(d.left + dx), top: snap(d.top + dy) });
        }
    });

});
