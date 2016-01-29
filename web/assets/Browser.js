var Browser = Backbone.Model.extend({

    urlRoot: '/browser',

    defaults: {
        id: null,
        top: 0,
        left: 0,
        width: 150,
        height: 200,
        isActive: false,
        tree: {},
        activeItem: []
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

    topItems: false,
    curItem: false,

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

            traverse = function (items, containerEl, parentModel) {
                var browserItems = new BrowserItemCollection();
                _.each(items, function(item) {
                    var model = browserItems.add(item);
                    model.set('isDir', !!item.children);
                    model.set('parent', parentModel);
                    var view = model.getView(containerEl);

                    if (model.get('isDir')) {
                        var childItems = traverse(item.children, view.$el.find('ul'), model);
                        model.set('children', childItems);
                    }
                });
                return browserItems;
            };
            this.topItems = traverse(this.model.get('tree'), this.$el.find('ul'), false);
            if (this.topItems.length) {
                this.curItem = this.topItems.first();
                this.curItem.set('isActive', true);
            }
        }

    },

    keyAction: function(key) {

        var keyMap = {
            'K': this.navUp,
            'J': this.navDown,

            'A': this.manageAdd,
            'M': this.manageMove,
            'D': this.manageDelete,
            'C': this.manageCopy,

            'Enter': this.openFileWidgetOrToggleDir
        }
        keyMap[key] && keyMap[key].apply(this);

    },

    openFileWidgetOrToggleDir: function() {

        if (!this.curItem) {
            return;
        }

        if (this.curItem.get('isDir')) {
            this.toggleDir(this.curItem);
        } else {
            this.openFileWidget(this.curItem);
        }

    },

    getFilenameFor: function (item) {

        var filename = '';
        var traversingItem = item;
        while (traversingItem) {
            filename = '/' + traversingItem.get('name') + filename;
            traversingItem = traversingItem.get('parent');
        }
        return filename;

    },

    openFileWidget: function (item) {

        var filename = this.getFilenameFor(item);

        // Initialize the widget
        var file = new File({filename: filename});
        file.save().then(function () {
            mainView.collection.add(file);
            file.init();
            file.getView();
            mainView.switchTo(file);
        });

    },

    toggleDir: function (item) {

        var collapsed = item.get('collapsed');
        item.set('collapsed', !collapsed);

    },

    updateCurItem: function (newCurItem) {
        this.curItem.set('isActive', false);
        newCurItem.set('isActive', true);
        this.curItem = newCurItem;
    },

    navUp: function() {

        if (!this.curItem) {
            return;
        }

        var item = this.curItem;
        var items = item.collection;
        var itemIndex = items.indexOf(item);
        if (itemIndex == 0) {
            if (item.get('parent')) {
                this.updateCurItem(item.get('parent'));
            }
        } else {
            var item = items.at(itemIndex - 1);
            if (item.get('isDir')) {
                // find exact upper item while traversing its upper directory item
                while (!item.get('collapsed')) {
                    if (item.get('children').length == 0) {
                        break;
                    }
                    item = item.get('children').last();
                }
            }
            this.updateCurItem(item);
        }

    },

    navDown: function() {

        if (!this.curItem) {
            return;
        }

        var item = this.curItem;

        if (item.get('isDir') && !item.get('collapsed') && item.get('children').length) {
            this.updateCurItem(item.get('children').first());
        } else {
            var items = item.collection;
            var itemIndex = items.indexOf(item);
            var isLastItem = itemIndex == items.length - 1;

            while (isLastItem) {
                if (item.get('parent') === false) {
                    break;
                }
                item = item.get('parent');
                items = item.collection;
                itemIndex = items.indexOf(item);
                isLastItem = itemIndex == items.length - 1;
            }

            if (!isLastItem) {
                this.updateCurItem(items.at(itemIndex + 1));
            }
        }

    },

    manageAdd: function () {

        var curItem = this.curItem;
        var addingDir = '/';

        if (curItem && curItem.get('isDir')) {
            addingDir = this.getFilenameFor(curItem) + '/';
        } else if (curItem && curItem.get('parent')) {
            addingDir = this.getFilenameFor(curItem.get('parent')) + '/';
        }

        var msg = "Enter name of your new file or directory.\nDirectory ends with /";
        var filename = window.prompt(msg, addingDir);
        var isUserCanceled = filename === null;
        if (isUserCanceled) {
            return;
        }

        var self = this;
        Backbone.ajax({
            method: 'POST',
            url: '/fileManage/add',
            data: {filename: filename},
            success: _.bind(function (rsp) {
                if (rsp.isSuccess) {
                    self.model.collection.fetch({data: $.param({refresh: 1})}).then(function(){
                        self.render(false);
                    });
                } else {
                    alert(rsp.message);
                }
            }, self)
        });

    },

    manageMove: function () {

    },

    manageDelete: function () {

    },

    manageCopy: function () {

    }

});



var BrowserItem = Backbone.Model.extend({

    defaults: {
        id: null,
        name: '',
        isActive: false,
        collapsed: true,
        isDir: false,
        parent: false,
        children: false
    },

    initialize: function(attributes, options) {

    },

    getView: function (containerEl) {

        if (!this.view) {
            this.view = new BrowserItemView({model: this, containerEl: containerEl});
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

        this.$el.appendTo(options.containerEl);

        this.listenTo(this.model, 'change', this.render);

        this.render(false);

    },

    template: _.template($('#template-browser-item').html()),

    render: function(_model) {

        var isInitial = _model === false;
        var model = this.model;
        var $el = this.$el;
        var isAttributeChanged = function (attrs) {
            return _.intersection(attrs, _.keys(model.changedAttributes())).length > 0;
        };

        if (isInitial || isAttributeChanged(['isActive', 'collapsed'])) {
            $el.toggleClass('active', model.get('isActive'));
            if (model.get('isDir')) {
                $el.toggleClass('collapsed', model.get('collapsed'));
            }
        }

        if (isInitial) {

            $el.html(this.template({
                name      : model.get('name'),
                isDir     : model.get('isDir'),
                collapsed : model.get('collapsed')
            }));

            if (model.get('isDir')) {
                $el.addClass('dir');
            }
        }

    }

});
