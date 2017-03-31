(function () {

    var isEditMode = false;

    function initKeyBindings() {
        document.addEventListener('keydown', function(e){
            var isBrowserKey = _.any([
                e.ctrlKey && e.key == 'r',  // browser Refresh
                e.key == 'F5',  // browser Refresh
                e.key == 'F12',  // inspector
                e.ctrlKey && e.key == 'I',  // inspector
                e.ctrlKey && e.key == 'l',  // focus to navbar
            ]);
            if (isBrowserKey) {
                return false;  // don't intercept browser shortcuts
            }
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
            e.preventDefault();
        });
        document.addEventListener('mousewheel', function(e){
            e.preventDefault();
        });
    }

    var drawingArea = window.drawingArea = new DrawingArea('canvas');

    var files = new FileCollection();
    files.fetch().then(function(){
        files.init();
        initKeyBindings();
    });

})();
