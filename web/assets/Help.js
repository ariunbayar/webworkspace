var Help = Backbone.Model.extend({

    url: '/help',

    defaults: {
        id: null,
        top: 0,
        left: 0,
        width: 150,
        height: 200,
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

        this.save(null, options);

    },


    getView: function () {

        if (!this.view) {
            this.view = new HelpView({model: this});
        }
        return this.view;

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

        if (isInitial || isAttributeChanged(['isActive'])) {
            this.$el.toggleClass('active', this.model.get('isActive'));
        }

        if (isInitial) {
            this.$el.html(this.template());
        }

    },

    keyAction: function(key) {
    }

});
