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

    items: null,
    curIndex: false,

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
            this.$el.html(this.template());

            var browserItems = this.items = new BrowserItemCollection();
            traverse = function (items, containerEl) {
                _.each(items, function(item) {
                    var model = browserItems.add(item);
                    var view = model.getView(containerEl);

                    var isDir = model.get('children') !== false;
                    if (isDir) {
                        traverse(model.get('children'), view.$el.find('ul'));
                    }
                });
            };
            traverse(this.model.get('tree'), this.$el.find('ul'));
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

        var isDir = this.items.at(this.curIndex).get('children') !== false;

        if (isDir) {
            this.toggleDir();
        } else {
            this.openFileWidget();
        }

    },

    openFileWidget: function () {

        console.log('openFileWidget');

    },

    toggleDir: function () {

        var collapsed = this.items.at(this.curIndex).get('collapsed');
        this.items.at(this.curIndex).set('collapsed', !collapsed);

    },

    updateActiveItemByIndex: function (nextIndexAt) {

        if (nextIndexAt === false) {
            return;
        }

        if (this.curIndex !== false) {
            this.items.at(this.curIndex).set('isActive', false);
        }
        this.items.at(nextIndexAt).set('isActive', true);
        this.curIndex = nextIndexAt;

    },

    navUp: function() {

        var nextIndexAt = false;
        var startSearchAt = this.curIndex === false ? this.items.length - 1 : this.curIndex - 1;

        for (var i = startSearchAt; i >= 0; --i) {
            if (this.items.at(i).getView().$el.is(':visible')) {
                nextIndexAt = i;
                break;
            }
        }

        this.updateActiveItemByIndex(nextIndexAt);

    },

    navDown: function() {

        var nextIndexAt = false;
        var startSearchAt = this.curIndex === false ? 0 : this.curIndex + 1;

        for (var i = startSearchAt; i < this.items.length; ++i) {
            if (this.items.at(i).getView().$el.is(':visible')) {
                nextIndexAt = i;
                break;
            }
        }

        this.updateActiveItemByIndex(nextIndexAt);

    },

});



var BrowserItem = Backbone.Model.extend({

    defaults: {
        id: null,
        name: '',
        isActive: false,
        collapsed: true,
        children: false
    },

    initialize: function(attributes, options) {

    },

    getView: function (parent) {

        if (!this.view) {
            this.view = new BrowserItemView({model: this, parent: parent});
        }
        return this.view;

    }

});

var BrowserItemCollection = Backbone.Collection.extend({

    model: BrowserItem,

});

var BrowserItemView = Backbone.View.extend({

    tagName: 'li',

    className: '',

    events: {},

    initialize: function(options) {

        this.$el.appendTo(options.parent);

        this.listenTo(this.model, 'change', this.render);

        this.render(false);

    },

    template: _.template($('#template-browser-item').html()),

    render: function(_model) {

        var isInitial = _model === false;
        var model = this.model;
        var $el = this.$el;
        var isDir = model.get('children') !== false;
        var isAttributeChanged = function (attrs) {
            return _.intersection(attrs, _.keys(model.changedAttributes())).length > 0;
        };

        if (isInitial || isAttributeChanged(['isActive', 'collapsed'])) {
            $el.toggleClass('active', model.get('isActive'));
            if (isDir) {
                $el.toggleClass('collapsed', model.get('collapsed'));
            }
        }

        if (isInitial) {

            $el.html(this.template({
                name      : model.get('name'),
                isDir     : isDir,
                collapsed : model.get('collapsed')
            }));

            if (isDir) {
                $el.addClass('dir');
            }
        }

    },


});
