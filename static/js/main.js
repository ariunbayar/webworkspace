(function () {

    var isEditMode = false;

    function initKeyBindings() {
        $(document).keydown(function(e){
            if (isEditMode == false && e.key == 'd') {  // zoom out
                drawingArea.zoom(false);
            }
            if (isEditMode == false && e.key == 'f') {  // zoom in
                drawingArea.zoom(true);
            }
            if (e.key == 'e') {
                isEditMode = !isEditMode;
                drawingArea.setPanZoom(isEditMode == false);
                files.setEditMode(isEditMode);
            }
        });
    }

    var drawingArea = window.drawingArea = new DrawingArea('canvas');

    var files = new FileCollection();
    files.fetch().then(function(){
        files.init();
        initKeyBindings();
    });

})();
