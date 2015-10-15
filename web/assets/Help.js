var Help = Backbone.Model.extend({
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

var HelpView = Backbone.View.extend({

    tagName: 'div',

    className: 'box help',

    events: {},

    initialize: function() {
        this.$el.appendTo('body');

        this.listenTo(this.model, 'change', this.render);

        this.render(false);
    },

    template: _.template($('#template-help').html()),

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

        if (isInitial) {
            this.$el.html(this.template());
        }

    },

    keyAction: function(key) {
    }

});
