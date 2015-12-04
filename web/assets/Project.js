var Project = Backbone.Model.extend({

    urlRoot: '/project',

    defaults: {
        id: null,
        top: 0,
        left: 0,
        width: 0,
        height: 0,
        directory: '',
        isActive: false
    },

    initialize: function(attributes, options) {

    },

    init: function () {

        this.on('change', this.changeOccured, this);
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
            this.view = new ProjectView({model: this});
        }
        return this.view;

    }

});

var ProjectView = Backbone.View.extend({

    tagName: 'div',

    className: 'box project',

    events: {},

    initialize: function() {

        this.$el.appendTo('body');

        this.listenTo(this.model, 'change', this.render);

        this.render(false);

    },

    template: _.template($('#template-project').html()),

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

        if (isInitial || isAttributeChanged(['directory'])) {
            this.$el.html(this.template({directory: this.model.get('directory')}));
        }

    },

    keyAction: function(key) {

        var keyMap = {
            'I': this.promptDirectoryAndReload,
            'O': this.openFileBrowser
        }
        keyMap[key] && keyMap[key].apply(this);

    },

    promptDirectoryAndReload: function() {

        var msg = 'Project directory is located at';
        var result = window.prompt(msg, this.model.get('directory'));
        var isUserCanceled = result === null;
        if (isUserCanceled) {
            return;
        }
        this.model.set('directory', result);

    },

    openFileBrowser: function() {

        // TODO open file browser widget

    }

});
