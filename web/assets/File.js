var File = Backbone.Model.extend({

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

    },

    init: function () {

        this.on('change', this.changeOccured, this);

    },

    changeOccured: function () {

        // silent option make sure this.save won't trigger another change
        var options = {silent: true, patch: true};

        var allowedFields = ['top', 'left', 'width', 'height', 'isActive'];
        attrs = _.pick(this.changedAttributes(), allowedFields);

        this.save(attrs, options);

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

    init: function () {

        this.each(function(file){
            // TODO can we listen changes in collection?
            file.init();
        })
    }

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
            'K': this.scrollUp,
            'J': this.scrollDown,
            'H': this.scrollLeft,
            'L': this.scrollRight,
            'Enter': this.openFileInEditor
            // TODO G or gg to go to beginning or ending

        }
        keyMap[key] && keyMap[key].apply(this);

    },

    openFileInEditor: function() {

        // TODO pass scroll location to code editor
        Backbone.ajax({
            url: '/fileOpen/' + this.model.id,
        });

    },

    scrollUp: function () {

        var scrollTop = this.$el.scrollTop() - Constants.boxScroll;
        scrollTop = scrollTop < 0 ? 0 : scrollTop;
        this.$el.scrollTop(scrollTop);

    },

    scrollDown: function () {

        var scrollHeight = this.el.scrollHeight;
        var scrollTop = this.$el.scrollTop() + Constants.boxScroll;
        scrollTop = scrollTop > scrollHeight ? scrollHeight : scrollTop;
        this.$el.scrollTop(scrollTop);

    },

    scrollLeft: function () {

        var scrollLeft = this.$el.scrollLeft() - Constants.boxScroll;
        scrollLeft = scrollLeft < 0 ? 0 : scrollLeft;
        this.$el.scrollLeft(scrollLeft);

    },

    scrollRight: function () {

        var scrollWidth = this.el.scrollWidth;
        var scrollLeft = this.$el.scrollLeft() + Constants.boxScroll;
        scrollLeft = scrollLeft > scrollWidth ? scrollWidth : scrollLeft;
        this.$el.scrollLeft(scrollLeft);

    }

});
