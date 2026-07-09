function DrawingArea(canvas_element_id) {

    var canvas = document.getElementById(canvas_element_id);
    var stage, container, outlines, fpsLabel, indicatorEditMode;
    var listenerHandleMove;

    var updateables = new (function Updateable() {
        var n = 0;
        this.updateOnce = false;
        this.incr = function incr(){ n += 1 };
        this.decr = function decr(){ n -= 1 };
        this.exist = function exist(){ return n > 0 };
    });

    var MIN_SCALE = 1 / 25;
    var MAX_SCALE = 4;
    var currentScale = 1;

    function clampScale(s) {
        return Math.max(MIN_SCALE, Math.min(MAX_SCALE, s));
    }

    // Continuous zoom by `factor`, keeping the global point (gx, gy) — a
    // canvas-relative pixel — pinned under itself (Google-Maps style).
    function zoomAt(factor, gx, gy) {
        var newScale = clampScale(currentScale * factor);
        if (newScale === currentScale) {
            return;
        }

        var local = container.globalToLocal(gx, gy);
        container.regX = local.x;
        container.regY = local.y;
        container.x = gx;
        container.y = gy;

        currentScale = newScale;
        container.scaleX = container.scaleY = newScale;
        updateables.updateOnce = true;
    }

    // d / f keys: step zoom centred on the current pointer position.
    function zoom(is_zoom_in) {
        zoomAt(is_zoom_in ? 1.3 : 1 / 1.3, stage.mouseX, stage.mouseY);
    }

    function tick(event) {
        if (updateables.exist() || updateables.updateOnce == true) {
            updateables.updateOnce = false;
            stage.update(event);
            fpsLabel.text = Math.round(createjs.Ticker.getMeasuredFPS()) + " fps at " + (+new Date() / 1000);
        }
    }

    function initElements() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        stage = new createjs.Stage(canvas);
        container = new createjs.Container();
        outlines = new createjs.Container();

        fpsLabel = new createjs.Text("-- fps", "12px Monospace", "#777");
        fpsLabel.x = canvas.width - 200;
        fpsLabel.y = canvas.height - 16;

        indicatorEditMode = new createjs.Shape();
        indicatorEditMode.graphics.ss(20).s('#FF0000').r(10, 10, canvas.width - 20, canvas.height - 20);
        indicatorEditMode.visible = false;

        container.addChild(outlines);
        stage.addChild(container, indicatorEditMode, fpsLabel);
    }

    function handleMove(event) {
        var offset = {x: container.x - event.stageX, y: container.y - event.stageY};

        stage.on('stagemousemove', function(event) {
            container.x = event.stageX + offset.x;
            container.y = event.stageY + offset.y;
            updateables.updateOnce = true;
        });

        stage.on('stagemouseup', function(){
            stage.removeAllEventListeners('stagemouseup');
            stage.removeAllEventListeners('stagemousemove');
        });
    }

    function setPanZoom(isTurnOn) {
        if (isTurnOn) {
            listenerHandleMove = stage.on('stagemousedown', handleMove);
            indicatorEditMode.visible = false;
        } else {
            stage.off('stagemousedown', listenerHandleMove);
            indicatorEditMode.visible = true;
        }
        updateables.updateOnce = true;
    }

    initElements();
    this.container = container;
    this.outlines = outlines;
    this.updateables = updateables;
    this.setPanZoom = setPanZoom;
    this.zoom = zoom;

    stage.enableDOMEvents(true);
    stage.enableMouseOver(5);
    stage.mouseMoveOutside = true; // keep tracking the mouse even when it leaves the canvas
    createjs.Touch.enable(stage);

    createjs.Ticker.setFPS(60);
    createjs.Ticker.addEventListener("tick", tick);

    setPanZoom(true);

    // --- Google-Maps-style zoom: wheel + pinch, both zoom toward the pointer ---

    function canvasPoint(clientX, clientY) {
        var rect = canvas.getBoundingClientRect();
        return {x: clientX - rect.left, y: clientY - rect.top};
    }

    canvas.addEventListener('wheel', function (event) {
        event.preventDefault();
        var p = canvasPoint(event.clientX, event.clientY);
        // smooth, delta-proportional factor; deltaY < 0 (scroll up) => zoom in
        zoomAt(Math.pow(1.0015, -event.deltaY), p.x, p.y);
    }, {passive: false});

    var pinchDist = null;

    function touchDistMid(touches) {
        var a = touches[0], b = touches[1];
        var dx = a.clientX - b.clientX, dy = a.clientY - b.clientY;
        return {
            dist: Math.sqrt(dx * dx + dy * dy),
            mid: canvasPoint((a.clientX + b.clientX) / 2, (a.clientY + b.clientY) / 2)
        };
    }

    canvas.addEventListener('touchstart', function (event) {
        if (event.touches.length === 2) {
            pinchDist = touchDistMid(event.touches).dist;
            // cancel any in-progress single-touch pan so it doesn't fight the pinch
            stage.removeAllEventListeners('stagemousemove');
            stage.removeAllEventListeners('stagemouseup');
        }
    }, {passive: false});

    canvas.addEventListener('touchmove', function (event) {
        if (event.touches.length === 2 && pinchDist !== null) {
            event.preventDefault();  // suppress native page zoom
            var t = touchDistMid(event.touches);
            zoomAt(t.dist / pinchDist, t.mid.x, t.mid.y);
            pinchDist = t.dist;
        }
    }, {passive: false});

    function endPinch(event) {
        if (event.touches.length < 2) {
            pinchDist = null;
        }
    }
    canvas.addEventListener('touchend', endPinch);
    canvas.addEventListener('touchcancel', endPinch);
}
