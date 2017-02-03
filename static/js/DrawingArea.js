function DrawingArea(canvas_element_id) {

    var canvas = document.getElementById(canvas_element_id);
    var stage = new createjs.Stage(canvas);

    var updateables = new (function Updateable() {
        var n = 0;
        this.manual = false;
        this.incr = function incr(){ n += 1 };
        this.decr = function decr(){ n -= 1 };
        this.exist = function exist(){ return n > 0 };
    });
    this.updateables = updateables;

    var fpsLabel;
    var outlines;
    var container;

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

            var local  =  container.globalToLocal(stage.mouseX, stage.mouseY);
            container.regX = local.x;
            container.regY = local.y;
            container.x = stage.mouseX;
            container.y = stage.mouseY;

            var props = {scaleX: scaler.scale, scaleY: scaler.scale}
            var easing = createjs.Ease.linear;
            createjs.Tween.get(container, {override: true}).to(props, 200, easing).call(updateables.decr);
            updateables.incr();
        }
        return event.preventDefault() && false;
    }

    function tick(event) {
        if (updateables.exist() || updateables.manual == true) {
            updateables.manual = false;
            stage.update(event);
            fpsLabel.text = Math.round(createjs.Ticker.getMeasuredFPS()) + " fps";
        }
    }

    this.addFile = function addFile(img, filename, x, y, w, h) {
        var file = new createjs.Container();
        container.addChild(file);

        var numItems = outlines.numChildren / 3;

        var outline1 = new createjs.Shape();
        outlines.addChild(outline1);
        outlines.setChildIndex(outline1, numItems * 3);

        var outline2 = new createjs.Shape();
        outlines.addChild(outline2);
        outlines.setChildIndex(outline2, numItems * 2);

        var outline3 = new createjs.Shape();
        outlines.addChild(outline3);
        outlines.setChildIndex(outline3, numItems);

        var border = new createjs.Shape();
        file.addChild(border)

        var label = new createjs.Text(filename, "bold 12px Monospace", "rgb(101, 123, 131)");
        file.addChild(label);

        var thumbnail = new createjs.Bitmap(img).set({cursor: 'pointer'});
        thumbnail.mask = new createjs.Shape();
        file.addChild(thumbnail);

        var fileUpdateable = function fileUpdateable(x, y, w, h){
            outline1.graphics.c().f('#ddeeff').rr(x - 60, y - 60, w + 2 * 60, h + 2 * 60, 40);
            outline2.graphics.c().f('#ffffff').rr(x - 80, y - 80, w + 2 * 80, h + 2 * 80, 60);
            outline3.graphics.c().f('#073642').rr(x - 85, y - 85, w + 2 * 85, h + 2 * 85, 65);
            file.x = x;
            file.y = y;
            border.graphics.c().s("#073642").ss(12).dr(6, 6, w - 12, h - 12);
            thumbnail.x = 1;
            thumbnail.y = 12;
            thumbnail.mask.graphics.c().dr(1, 12, w - 2, h - 13);
            updateables.manual = true;
        }
        fileUpdateable(x, y, w, h);

        return fileUpdateable;
    }

    function initElements() {
        container = new createjs.Container();
        container.x = 0;
        container.y = 0;
        stage.addChild(container);

        outlines = new createjs.Container();
        outlines.x = 0;
        outlines.y = 0;
        container.addChild(outlines);

        fpsLabel = new createjs.Text("-- fps", "12px Monospace", "#777");
        fpsLabel.x = 350;
        fpsLabel.y = 200;
        stage.addChild(fpsLabel);
    }

    initElements();

    stage.enableDOMEvents(true);
    stage.enableMouseOver(5);
    //stage.mouseMoveOutside = true; // keep tracking the mouse even when it leaves the canvas
    createjs.Touch.enable(stage);

    createjs.Ticker.setFPS(60);
    createjs.Ticker.addEventListener("tick", tick);

    stage.canvas.addEventListener('DOMMouseScroll', handleScroll, false);
    stage.canvas.addEventListener('mousewheel',     handleScroll, false);

    stage.addEventListener('stagemousedown', function(event) {
        var offset = {x: container.x - event.stageX, y: container.y - event.stageY};

        stage.addEventListener('stagemousemove', function(event) {
            container.x = event.stageX + offset.x;
            container.y = event.stageY + offset.y;
            updateables.manual = true;
        });

        stage.addEventListener('stagemouseup', function(){
            stage.removeAllEventListeners('stagemousemove');
        });
    });
}
