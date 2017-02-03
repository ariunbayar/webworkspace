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
        })
    }

});

var FileView = Backbone.View.extend({

    events: {},

    initialize: function() {

        this.listenTo(this.model, 'change', this.render);

        this.render(false);

    },

    render: function(_model) {

        var isInitial = _model === false;
        var model = this.model;
        var isAttributeChanged = function (attrs) {
            return _.intersection(attrs, _.keys(model.changedAttributes())).length > 0;
        };

        if (!isInitial && isAttributeChanged(['top', 'left', 'width', 'height'])) {
            this.updateable(
                model.get('left'), model.get('top'),
                model.get('width'), model.get('height')
            );
        }

        if (!isInitial && isAttributeChanged(['isActive'])) {
            // TODO
            this.model.get('isActive');
        }

        if (isInitial) {
            var img = new Image();
            img.onload = _.bind(function(){
                this.updateable = window.area.addFile(
                    img,
                    model.get('filename'),
                    model.get('left'), model.get('top'),
                    model.get('width'), model.get('height')
                );
            }, this);
            img.src = '/thumbnail/' + model.get('id');
        }

    }

});
