(function () {

    window.area = new DrawingArea('canvas');

    var files = new FileCollection();
    files.fetch().then(function(){
        files.init();
    });

})();
