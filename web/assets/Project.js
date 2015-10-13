var Project = Backbone.Model.extend({
    defaults: {
        top: 0,
        left: 0,
        width: 150,
        height: 200,
        directory: ''
    },

    initialize: function(attributes, options) {
    }
});

var ProjectView = Backbone.View.extend({

    tagName: 'div',

    className: 'box project',

    events: {},

    initialize: function() {
        this.$el.appendTo('body');

        boxes.push(this);

        this.listenTo(this.model, 'change', this.render);

        this.render();
    },

    template: _.template($('#template-project').html()),

    render: function() {
        this.$el.css({
            top: this.model.get('top'),
            left: this.model.get('left'),
            width: this.model.get('width'),
            height: this.model.get('height')
        });
        this.$el.html(this.template({directory: this.model.get('directory')}));
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
