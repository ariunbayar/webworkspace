(function () {

    function DrawingArea(canvas_element_id) {
        var redraw = function redraw(){
            // Clear the entire canvas
            var p1 = ctx.transformedPoint(0,0);
            var p2 = ctx.transformedPoint(canvas.width,canvas.height);
            ctx.clearRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y);

            ctx.save();
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.restore();

            function drawOutline(i, color) {
                ctx.fillStyle = color;
                _.each(files, function(file){
                    ctx.fillRect(file.left - i, file.top - i, file.width + i * 2, file.height + i * 2);
                });
            }
            drawOutline(160, '#073642');
            drawOutline(156, '#ffffff');
            drawOutline(120, '#ddeeff');

            // draws file boxes
            _.each(files, function(file){
                ctx.drawImage(file.thumbnail, 0, 0, file.width, file.height, file.left, file.top, file.width, file.height);

                ctx.strokeStyle = '#073642';

                ctx.beginPath();
                ctx.moveTo(file.left + file.width + 0.5, file.top);
                ctx.lineTo(file.left + file.width + 0.5, file.top + file.height + 0.5);
                ctx.lineTo(file.left - 0.5, file.top + file.height + 0.5);
                ctx.lineTo(file.left - 0.5, file.top);
                ctx.lineWidth = 1;
                ctx.stroke();

                ctx.beginPath();
                ctx.moveTo(file.left - 1, file.top - 5);
                ctx.lineTo(file.left + file.width + 1, file.top - 5);
                ctx.lineWidth = 10;
                ctx.stroke();

                ctx.font = "bold 12px monospace";
                ctx.fillStyle = 'rgb(101, 123, 131)';
                ctx.fillText(file.filename, file.left, file.top);

            });

            ctx.beginPath();
            ctx.moveTo(-4, 0.5);
            ctx.lineTo(5, 0.5);
            ctx.moveTo(0.5, -4);
            ctx.lineTo(0.5, 5);
            ctx.strokeStyle = '#f00';
            ctx.lineWidth = 1;
            ctx.stroke();
        }

        // Adds ctx.getTransform() - returns an SVGMatrix
        // Adds ctx.transformedPoint(x,y) - returns an SVGPoint
        var trackTransforms = function (){
            var svg = document.createElementNS("http://www.w3.org/2000/svg", 'svg');
            var xform = svg.createSVGMatrix();
            ctx.getTransform = function(){ return xform; };

            var savedTransforms = [];
            var save = ctx.save;
            ctx.save = function(){
                savedTransforms.push(xform.translate(0,0));
                return save.call(ctx);
            };

            var restore = ctx.restore;
            ctx.restore = function(){
                xform = savedTransforms.pop();
                return restore.call(ctx);
            };

            var scale = ctx.scale;
            ctx.scale = function(sx, sy){
                if (sx < 1) {
                    if (curZoomIndex > 0) {
                        curZoomIndex -= 1;
                    }
                } else {
                    if (curZoomIndex < zoomLevels.length - 1) {
                        curZoomIndex += 1;
                    }
                }
                sx = zoomLevels[curZoomIndex] / xform.a;
                sy = zoomLevels[curZoomIndex] / xform.d;
                xform = xform.scaleNonUniform(sx, sy);
                return scale.call(ctx, sx, sy);
            };

            var rotate = ctx.rotate;
            ctx.rotate = function(radians){
                xform = xform.rotate(radians * 180 / Math.PI);
                return rotate.call(ctx, radians);
            };

            var translate = ctx.translate;
            ctx.translate = function(dx,dy){
                xform = xform.translate(dx, dy);
                return translate.call(ctx, dx, dy);
            };

            var transform = ctx.transform;
            ctx.transform = function(a, b, c, d, e, f){
                var m2 = svg.createSVGMatrix();
                m2.a = a; m2.b = b; m2.c = c; m2.d = d; m2.e = e; m2.f = f;
                xform = xform.multiply(m2);
                return transform.call(ctx, a, b, c, d, e, f);
            };

            var setTransform = ctx.setTransform;
            ctx.setTransform = function(a, b, c, d, e, f){
                xform.a = a;
                xform.b = b;
                xform.c = c;
                xform.d = d;
                xform.e = e;
                xform.f = f;
                return setTransform.call(ctx, a, b, c, d, e, f);
            };

            var pt  = svg.createSVGPoint();
            ctx.transformedPoint = function(x, y){
                pt.x = x; pt.y = y;
                return pt.matrixTransform(xform.inverse());
            }
        }

        var zoom = function(clicks){
            var pt = ctx.transformedPoint(lastX, lastY);
            // TODO confirm this fix
            //pt.x = Math.round(pt.x);
            //pt.y = Math.round(pt.y);
            ctx.translate(pt.x, pt.y);
            var scaleFactor = 1.1;
            var factor = Math.pow(scaleFactor, clicks);
            ctx.scale(factor, factor);
            ctx.translate(-pt.x, -pt.y);
            redraw();
        }

        var handleScroll = function (evt){
            // WARNING! scope is canvas object
            var delta = evt.wheelDelta ? evt.wheelDelta / 40 : evt.detail ? -evt.detail : 0;
            if (delta) zoom(delta);
            return evt.preventDefault() && false;
        }

        var canvas = document.getElementById(canvas_element_id);
        var ctx = canvas.getContext('2d');

        var lastX = canvas.width / 2,
            lastY = canvas.height / 2;

        var dragStart, dragged;

        var zoomLevels = [1 / 25, 1 / 10, 1 / 5, 1 / 2, 1, 1 * 4];
        var curZoomIndex = 4;


        canvas.addEventListener('mousedown', function(evt){
            lastX = evt.offsetX || (evt.pageX - canvas.offsetLeft);
            lastY = evt.offsetY || (evt.pageY - canvas.offsetTop);
            dragStart = ctx.transformedPoint(lastX, lastY);
            dragged = false;
        }, false);

        canvas.addEventListener('mousemove', function(evt){
            lastX = evt.offsetX || (evt.pageX - canvas.offsetLeft);
            lastY = evt.offsetY || (evt.pageY - canvas.offsetTop);
            dragged = true;
            if (dragStart){
                var pt = ctx.transformedPoint(lastX, lastY);
                ctx.translate(pt.x - dragStart.x, pt.y - dragStart.y);
                redraw();
            }
        }, false);

        canvas.addEventListener('mouseup', function(evt){
            dragStart = null;
            if (!dragged) {
                zoom(evt.shiftKey ? -1 : 1);
            }
        }, false);

        canvas.addEventListener('DOMMouseScroll', handleScroll, false);
        canvas.addEventListener('mousewheel',     handleScroll, false);

        trackTransforms();
        redraw();

        this.canvas = canvas;
    }

    function loadFiles(callback) {
        Backbone.ajax({
            method: 'GET',
            url: '/files',
            data: {},
            success: function (rsp) {
                var num_files_loaded = 0;
                var num_files = 0;
                _.each(rsp, function(file){
                    if (file.filename.substr(-2) == 'js') {  // TODO all type of files
                        num_files += 1;
                        file.thumbnail = new Image();
                        file.thumbnail.onload = function() {
                            num_files_loaded += 1;
                            files.push(file);
                            if (num_files_loaded == num_files) {
                                callback();
                            }
                        };
                        file.thumbnail.src = '/thumbnail/' + file.id;
                    }
                });
            }
        });
    }

    var files = [];  // TODO probably gonna be a managable global within individual project item

    loadFiles(function(){
        var area = new DrawingArea('canvas');
    });

})();
