(function () {


    function loadFiles(area) {
        Backbone.ajax({
            method: 'GET',
            url: '/files',
            data: {},
            success: function (rsp) {
                _.each(rsp, function(file){
                    if (file.filename.substr(-2) == 'js') {  // TODO all type of files
                        file.thumbnail = new Image();
                        file.thumbnail.onload = function() {
                            area.addFile(file.thumbnail, file.filename, file.left, file.top, file.width, file.height);
                        };
                        file.thumbnail.src = '/thumbnail/' + file.id;
                    }
                });
            }
        });
    }

    var files = [];  // TODO probably gonna be a managable global within individual project item
    var area = new DrawingArea('canvas');

    loadFiles(area);

})();
