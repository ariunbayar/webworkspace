var Project = Backbone.Model.extend({
    defaults: {
        top: 0,
        left: 0,
        width: 150,
        height: 200
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
        this.$el.html(this.template({directory: '/ab/cd/123'}));
    }
});
