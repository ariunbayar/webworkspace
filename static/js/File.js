var File = Backbone.Model.extend({

    urlRoot: '/file',  // generates '/file/<id>'

    defaults: {
        id: null,
        top: 0,
        left: 0,
        width: 150,
        height: 200,
        filename: '',
        isActive: false
    },

    initialize: function(attributes, options) {
        if (this.get('filename').substr(-2) == 'js') {  // TODO all type of files
            this.initView();
        }
    },

    init: function () {

        this.on('change', this.changeOccured, this);

    },

    changeOccured: function () {

        // silent option makes sure this.save won't trigger another change
        var options = {silent: true, patch: true, wait: true};

        var allowedFields = ['top', 'left', 'width', 'height', 'isActive'];
        attrs = _.pick(this.changedAttributes(), allowedFields);

        this.save(attrs, options);

    },

    initView: function () {

        if (!this.view) {
            this.view = new FileView({model: this});
        }
        return this.view;

    }

});

var FileCollection = Backbone.Collection.extend({

    url: '/files',

    model: File,

    initialize: function () {
    },

    init: function () {

        this.each(function(file){
            // TODO can we listen changes in collection?
            file.init();
        });
    },

    setEditMode: function (isTurnOn) {
        this.each(function(file){
            // TODO not only JS files but all type of files
            if (file.view) {
                file.view.setEditMode(isTurnOn);
            }
        });
    },

});

var FileView = Backbone.View.extend({

    events: {},

    initialize: function() {

        this.listenTo(this.model, 'change', this.render);

        this.render(false);

    },

    render: function render(_model) {

        var isInitial = _model === false;
        var model = this.model;
        var isAttributeChanged = function (attrs) {
            return _.intersection(attrs, _.keys(model.changedAttributes())).length > 0;
        }

        if (!isInitial && isAttributeChanged(['top', 'left'])) {
            this.daMoveFileBox(model.get('left'), model.get('top'), true);
        }

        if (!isInitial && isAttributeChanged(['width', 'height'])) {
            this.daResizeFileBox(model.get('width'), model.get('height'), true);
        }

        if (!isInitial && isAttributeChanged(['isActive'])) {
            // TODO
            model.get('isActive');
        }

        if (isInitial) {
            var img = new Image();
            img.onload = _.bind(this.daAddFileBox, this, img);
            img.src = '/thumbnail/' + model.get('id');
        }

    },

    snapTo: function (n) {
        return Math.round(n / 10) * 10;
    },

    daAddFileBox: function areaAddFile(img) {
        var model = this.model;

        var container = window.drawingArea.container;
        var outlines = window.drawingArea.outlines;

        var numItems = outlines.numChildren / 3;
        var _addOutline = function(layer_index) {
            var outline = new createjs.Shape();
            outlines.addChild(outline);
            outlines.setChildIndex(outline, (numItems + 1) * layer_index - 1);
            return outline;
        }

        this.outline1 = _addOutline(1);
        this.outline2 = _addOutline(2);
        this.outline3 = _addOutline(3);

        this.border = new createjs.Shape();
        this.label = new createjs.Text(model.get('filename'), "bold 12px Monospace", "rgb(101, 123, 131)");
        this.thumbnail = new createjs.Bitmap(img).set({cursor: 'pointer'});
        this.thumbnail.mask = new createjs.Shape();
        this.resizer = new createjs.Shape();

        this.file = new createjs.Container();

        this.file.addChild(this.border, this.label, this.thumbnail, this.resizer);
        container.addChild(this.file);

        this.daMoveFileBox(model.get('left'), model.get('top'));
        this.daResizeFileBox(model.get('width'), model.get('height'));

        window.drawingArea.updateables.updateOnce = true;
    },

    daHandleDrag: function daHandleDrag(e) {
        var container = window.drawingArea.container;
        var thumbnail = this.thumbnail;
        var self = this;

        var local = container.globalToLocal(e.stageX, e.stageY);
        var offset = {x: local.x - self.file.x, y: local.y - self.file.y};

        thumbnail.on('pressmove', function(event) {
            var local = container.globalToLocal(event.stageX, event.stageY);
            var x = self.snapTo(local.x - offset.x);
            var y = self.snapTo(local.y - offset.y);
            self.model.set('left', x);
            self.model.set('top', y);
        });

        thumbnail.on('pressup', function(event){
            thumbnail.removeAllEventListeners('pressup');
            thumbnail.removeAllEventListeners('pressmove');
        });
    },

    setEditMode: function setEditMode(isTurnOn) {
        if (isTurnOn) {
            this.listenerHandleDrag = this.thumbnail.on('mousedown', this.daHandleDrag, this);
        } else {
            this.thumbnail.off('mousedown', this.listenerHandleDrag);
        }
    },

    daMoveFileBox: function daMoveFileBox(x, y, autoupdate) {
        this.outline1.x = this.outline2.x = this.outline3.x = x;
        this.outline1.y = this.outline2.y = this.outline3.y = y;
        this.file.x = x;
        this.file.y = y;

        window.drawingArea.updateables.updateOnce = autoupdate === true;
    },

    daResizeFileBox: function daResizeFileBox(w, h, autoupdate) {
        this.outline1.graphics.c().f('#073642').rr(-85, -85, w + 2 * 85, h + 2 * 85, 65);
        this.outline2.graphics.c().f('#ffffff').rr(-80, -80, w + 2 * 80, h + 2 * 80, 60);
        this.outline3.graphics.c().f('#ddeeff').rr(-60, -60, w + 2 * 60, h + 2 * 60, 40);
        this.border.graphics.c().s("#073642").ss(12).dr(6, 6, w - 12, h - 12);
        this.thumbnail.x = 1;
        this.thumbnail.y = 12;
        this.thumbnail.mask.graphics.c().dr(1, 12, w - 2, h - 13);
        this.resizer.graphics.c().s("#FFFF00").ss(1).r(w - 0.5, h - 0.5, 20, 20);
        this.resizer.graphics.s("#073642").ss(1).r(w + 0.5, h + 0.5, 18, 18);

        window.drawingArea.updateables.updateOnce = autoupdate === true;
    }

});
