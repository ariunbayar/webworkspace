var Browser = Backbone.Model.extend({

    urlRoot: '/browser',

    defaults: {
        id: null,
        top: 0,
        left: 0,
        width: 150,
        height: 200,
        isActive: false,
        tree: {}
    },

    initialize: function(attributes, options) {

    },

    init: function () {

        this.on('change', this.changeOccured, this);

    },

    changeOccured: function () {

        // silent option make sure this.save won't trigger another change
        var options = {silent: true};

        this.save(null, options);

    },

    getView: function () {

        if (!this.view) {
            this.view = new BrowserView({model: this});
        }
        return this.view;

    }

});

var BrowserCollection = Backbone.Collection.extend({

    url: '/browser',

    model: Browser,

    initialize: function () {
    },

    init: function () {

        this.each(function(browser){
            // TODO can we listen changes in collection?
            browser.init();
        })
    }

});

var BrowserView = Backbone.View.extend({

    tagName: 'div',

    className: 'box browser',

    events: {},

    initialize: function() {

        this.$el.appendTo('body');

        this.listenTo(this.model, 'change', this.render);

        this.render(false);

    },

    template: _.template($('#template-browser').html()),

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
                tree: this.model.get('tree')
            }));
        }

    },

    keyAction: function(key) {

        var keyMap = {
            'K': this.navUp,
            'J': this.navDown,
            'Enter': this.openFileWidgetOrToggleDir
        }
        keyMap[key] && keyMap[key].apply(this);

    },

    openFileWidgetOrToggleDir: function() {

        console.log(this.model.get('tree'));
        if (this.currentItem == 'FILE') {
            this.openFileWidget();
        }
        if (this.currentItem == 'DIR') {
            this.toggleDir();
        }

    },

    openFileWidget: function () {

        console.log('openFileWidget');

    },

    toggleDir: function () {

        console.log('toggleDir');

    },

    navUp: function() {

        console.log('navUp');

    },

    navDown: function() {

        console.log('navDown');

    },

});
