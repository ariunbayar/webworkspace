var Project = Backbone.Model.extend({

    url: '/project',

    defaults: {
        id: 2,
        top: 0,
        left: 0,
        width: 150,
        height: 200,
        directory: ''
    },

    initialize: function(attributes, options) {
        this.fetch();
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
        // waits for model to synchronize with backend
        setTimeout(function(){ window.location.reload(); }, 3000);
    },

    openFileBrowser: function() {
        // TODO open file browser widget
    }

});
