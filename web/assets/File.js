var File = Backbone.Model.extend({

    url: '/file',

    defaults: {
        id: null,
        top: 0,
        left: 0,
        width: 0,
        height: 0,
        filename: '',
        content: '',
        numLines: 0,
        isActive: false
    },

    initialize: function(attributes, options) {

        // TODO save changes
        //this.fetch().then(_.bind(function(){
            //this.on('change', this.changeOccured, this);
        //}, this));

    },

    changeOccured: function () {

        // silent option make sure this.save won't trigger another change
        var options = {silent: true};

        if (this.hasChanged('directory')) {
            // directory change must refresh the page
            // TODO update changes to related boxes without refresh
            options.success = function() { window.location.reload(); }
        }

        this.save(null, options);

    },

    getView: function () {

        if (!this.view) {
            this.view = new FileView({model: this});
        }
        return this.view;

    }

});

var FileCollection = Backbone.Collection.extend({

    url: '/file',

    model: File,

    initialize: function () {
    },

});

var FileView = Backbone.View.extend({

    tagName: 'div',

    className: 'box watch',

    events: {},

    initialize: function() {

        this.$el.appendTo('body');

        this.listenTo(this.model, 'change', this.render);

        this.render(false);

    },

    template: _.template($('#template-file').html()),

    render: function(_model) {

        var isInitial = _model === false;
        var model = this.model;
        var isAttributeChanged = function (attrs) {
            return _.intersection(attrs, _.keys(model.changedAttributes())).length > 0;
        };

        if (isInitial || isAttributeChanged(['top', 'left', 'width', 'height'])) {
            this.$el.css({
                top    : this.model.get('top'),
                left   : this.model.get('left'),
                width  : this.model.get('width'),
                height : this.model.get('height')
            });
        }

        if (isInitial || isAttributeChanged(['isActive'])) {
            this.$el.toggleClass('active', this.model.get('isActive'));
        }

        if (isInitial) {
            this.$el.html(this.template({
                filename: this.model.get('filename'),
                content: this.model.get('content'),
                numLines: this.model.get('numLines')
            }));
        }

    },

    keyAction: function(key) {
        var keyMap = {
        }
        keyMap[key] && keyMap[key].apply(this);
    }

});
