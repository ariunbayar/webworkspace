function DrawingArea(canvas_element_id) {

    var canvas = document.getElementById(canvas_element_id);
    var stage, container, outlines, fpsLabel;

    var updateables = new (function Updateable() {
        var n = 0;
        this.updateOnce = false;
        this.incr = function incr(){ n += 1 };
        this.decr = function decr(){ n -= 1 };
        this.exist = function exist(){ return n > 0 };
    });

    var scaler = new (function Scaler(){
        var zoomLevels = [1 / 25, 1 / 10, 1 / 5, 1 / 2, 1, 1 * 4];
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

    function handleScroll(event) {
        var delta = event.wheelDelta ? event.wheelDelta / 40 : event.detail ? -event.detail : 0;
        if (delta) {
            var is_zoom_in = Math.max(-1, Math.min(1, delta)) > 0;
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
        return event.preventDefault() && false;
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

        container.addChild(outlines);
        stage.addChild(container, fpsLabel);
    }

    initElements();
    this.container = container;
    this.outlines = outlines;
    this.updateables = updateables;
    this.dragMode = 'global';  // global, box

    stage.enableDOMEvents(true);
    stage.enableMouseOver(5);
    stage.mouseMoveOutside = true; // keep tracking the mouse even when it leaves the canvas
    createjs.Touch.enable(stage);

    createjs.Ticker.setFPS(60);
    createjs.Ticker.addEventListener("tick", tick);

    stage.canvas.addEventListener('DOMMouseScroll', handleScroll, false);
    stage.canvas.addEventListener('mousewheel',     handleScroll, false);

    stage.on('stagemousedown', function(event) {
        if (this.dragMode != 'global') return;
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
    }, this);

    $(document).keydown(_.bind(function(e){
        var key = (65 <= e.which && e.which <= 90) ? String.fromCharCode(e.which) : '';
        if (key == 'E') {
            if (this.dragMode == 'global') {
                this.dragMode = 'box';
            } else {
                this.dragMode = 'global';
            }
        }
    }, this));
}
