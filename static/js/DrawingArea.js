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

    var scaler = new (function Scaler(){
        var zoomLevels = [1 / 25, 1 / 10, 1 / 5, 1 / 2, 1, 1 * 4, 1 * 6, 1 * 8];
        var n = 4;
        var self = this;
        this.scale = zoomLevels[n];
        this.zoomIn = function zoomIn() {
            n = Math.min(zoomLevels.length - 1, n + 1);
            self.scale = zoomLevels[n];
        };
        this.zoomOut = function zoomOut() {
            n = Math.max(0, n - 1);
            self.scale = zoomLevels[n];
        };
    });

    function zoom(is_zoom_in) {
        is_zoom_in ? scaler.zoomIn() : scaler.zoomOut();

        var local = container.globalToLocal(stage.mouseX, stage.mouseY);
        container.regX = local.x;
        container.regY = local.y;
        container.x = stage.mouseX;
        container.y = stage.mouseY;

        var props = {scaleX: scaler.scale, scaleY: scaler.scale}
        createjs.Tween.get(container, {override: true}).to(props, 200).call(updateables.decr);
        updateables.incr();
    }

    function tick(event) {
        if (updateables.exist() || updateables.updateOnce == true) {
            updateables.updateOnce = false;
            stage.update(event);
            fpsLabel.text = Math.round(createjs.Ticker.getMeasuredFPS()) + " fps";
        }
    }

    function initElements() {
        stage = new createjs.Stage(canvas);
        container = new createjs.Container();
        outlines = new createjs.Container();

        fpsLabel = new createjs.Text("-- fps", "12px Monospace", "#777");
        fpsLabel.x = 350;
        fpsLabel.y = 200;

        indicatorEditMode = new createjs.Shape();
        indicatorEditMode.graphics.ss(20).s('#FF0000').r(10, 10, canvas.width - 20, canvas.height - 20);
        indicatorEditMode.visible = false;

        container.addChild(outlines);
        stage.addChild(container, fpsLabel, indicatorEditMode);
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

    // XXX disabled as key D and F are being user for zoom
    //stage.canvas.addEventListener('DOMMouseScroll', handleScroll, false);
    //stage.canvas.addEventListener('mousewheel',     handleScroll, false);
    //var delta = event.wheelDelta ? event.wheelDelta / 40 : event.detail ? -event.detail : 0;
    //if (delta) {
        //var is_zoom_in = Math.max(-1, Math.min(1, delta)) > 0;
    //}
    //return event.preventDefault() && false;
}
