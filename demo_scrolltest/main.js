var container = $('.wrapper');
var pointer = $('.pointer');

// XXX yeah we probably won't need 1/25 scale
var zoomLevels = [1 / 25, 1 / 10, 1 / 5, 1, 1 * 4];
var curZoomIndex = 3;
var curZoom = 1;
var curTransformOrigin = {x: 0, y: 0};
var curTranslate = {x: 0, y: 0};

function zoomSet(newZoom, pointerX, pointerY) {
    if (newZoom <= 0.001) return;

    var is_pointer_moved = pointerX != parseInt(curTransformOrigin.x + curTranslate.x) || pointerY != parseInt(curTransformOrigin.y + curTranslate.y);

    if (is_pointer_moved) {
        var oldOffsetX = (curZoom - 1) * curTransformOrigin.x;
        var oldOffsetY = (curZoom - 1) * curTransformOrigin.y;

        var transformOriginX = (pointerX + oldOffsetX - curTranslate.x) / curZoom;
        var transformOriginY = (pointerY + oldOffsetY - curTranslate.y) / curZoom;
        curTranslate.x += transformOriginX * (curZoom - 1) - oldOffsetX;
        curTranslate.y += transformOriginY * (curZoom - 1) - oldOffsetY;

        curTransformOrigin.x = transformOriginX;
        curTransformOrigin.y = transformOriginY;
    }
    var transform = '';

    transform += 'translate(' + curTranslate.x + 'px,' + curTranslate.y + 'px)';
    transform += ' scale(' + newZoom + ')';

    container.css('transform', transform);
    container.css('transform-origin', transformOriginX + 'px ' + transformOriginY + 'px');

    curZoom = newZoom;
    $('#zoomlevel').html('Zoom level: ' + (newZoom * 100) + '%');
}

function scrollTo(_x, _y) {
    var x = $(document).scrollLeft();
    var y = $(document).scrollTop();
    console.log(x, y);
    $(document).scrollLeft(x + _x);
    $(document).scrollTop(y + _y);
}

$(document).on('mousewheel', function(e){
    var is_zoom_in = e.ctrlKey == true && e.deltaY == 1;
    var is_zoom_out = e.ctrlKey == true && e.deltaY == -1;

    if (is_zoom_in) {
        e.preventDefault();
        if (curZoomIndex < zoomLevels.length - 1) {
            curZoomIndex += 1;
            zoomSet(zoomLevels[curZoomIndex], e.pageX, e.pageY);
            //zoomSet(curZoom * 1.1, e.pageX, e.pageY);
        }
    } else if (is_zoom_out) {
        e.preventDefault();
        if (curZoomIndex > 0) {
            curZoomIndex -= 1;
            // focus to center of window when zooming out
            var w = $(window);
            //zoomSet(curZoom * 0.9, w.width() / 2, w.height() / 2);  // 5% smaller
            zoomSet(zoomLevels[curZoomIndex], w.width() / 2, w.height() / 2);  // 5% smaller
        }
    } else {
        if (e.deltaX == 1) {
            console.log('right');
        }
        if (e.deltaX == -1) {
            console.log('left');
        }
        if (e.deltaY == 1) {
            console.log('up');
        }
        if (e.deltaY == -1) {
            console.log('down');
        }
    }
    // XXX e.deltaFactor: do we & how we need it?
});
