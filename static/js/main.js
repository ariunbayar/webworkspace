(function () {

    window.drawingArea = new DrawingArea('canvas');

    var files = new FileCollection();
    files.fetch().then(function(){
        files.init();
    });

})();
