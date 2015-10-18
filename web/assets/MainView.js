var MainCollection = Backbone.Collection.extend({

    fetch: function () {

        var project = new Project();
        var help = new Help({top: 300, left: 20});
        var files = new FileCollection();

        var deferredAll = $.when(
            project.fetch(),
            files.fetch()
        );

        deferredAll.then(_.bind(function(){
            this.add(project);
            this.add(files.models);
            this.add(help);
        }, this));

        return deferredAll;

    }

});


var MainView = Backbone.View.extend({

    collection: null,
    currentModel: null,
    currentMode: 'MODE_NORMAL',

    render: function () {

        this.collection.each(function(model) {
            if (model.get('isActive')) {
                this.switchTo(model);
            }
            model.getView();
        }, this);

    },

    keyAction: function(key) {

        var hasMainViewHandler = !!(this.keyMaps[this.currentMode] && this.keyMaps[this.currentMode][key]);

        if (hasMainViewHandler) {
            this.keyMaps[this.currentMode][key].call(this);
        } else {
            this.currentBox && this.currentBox.keyAction(key);
        }

    },

    openFile: function() {

        // TODO rewrite for this view
        // TODO pass scroll location to code editor
        var fileId = currentBox.attr('data-idx');
        $.get(window.location.pathname + '?open=' + fileId);

    },

    switchMode: function(newMode) {

        if (!this.currentModel) {
            return;
        }

        var modeChange = this.currentMode + ' -> ' + newMode;

        switch (modeChange) {
            case  'MODE_EDIT -> MODE_NORMAL':
                this.currentModel.getView().$el.css('border-color', '#ccc');
                break;
            case  'MODE_NORMAL -> MODE_EDIT':
                this.currentModel.getView().$el.css('border-color', '#00f');
                break;

            default:
                console.error('Unknown mode change: ' + modeChange);
        }

        this.currentMode = newMode;

    },

    closeBox: function () {

        // TODO rewrite for this view
        setTimeout((function(el) {
            el.addClass('hinge');
            return function () {
                // switch to some other window
                navLeft(); navRight(); navUp(); navDown();
                el.remove();
            }
        })(currentBox), 1000);

    },

    moveCurrentBox: function (x, y) {

        var top  = this.currentModel.get('top');
        var left = this.currentModel.get('left');

        // normalize current box position to grid size
        top  = Math.round(top  / Constants.gridSize) * Constants.gridSize;
        left = Math.round(left / Constants.gridSize) * Constants.gridSize;

        // move with x and y by grid size
        this.currentModel.set('top',  top  + y * Constants.gridSize);
        this.currentModel.set('left', left + x * Constants.gridSize);

    },

    resizeCurrentBox: function (x, y) {

        // normalize current box size to grid
        var width  = Math.round(this.currentModel.get('width')  / Constants.gridSize) * Constants.gridSize;
        var height = Math.round(this.currentModel.get('height') / Constants.gridSize) * Constants.gridSize;

        // resize with x and y by grid size
        this.currentModel.set('width',  width  + x * Constants.gridSize);
        this.currentModel.set('height', height + y * Constants.gridSize);

    },

    scrollUp: function () {

        // TODO rewrite for this view
        var scrollTop = currentBox.scrollTop() - Constants.boxScroll;
        scrollTop = scrollTop < 0 ? 0 : scrollTop;
        currentBox.scrollTop(scrollTop);

    },

    scrollDown: function () {

        // TODO rewrite for this view
        var scrollHeight = currentBox[0].scrollHeight;
        var scrollTop = currentBox.scrollTop() + Constants.boxScroll;
        scrollTop = scrollTop > scrollHeight ? scrollHeight : scrollTop;
        currentBox.scrollTop(scrollTop);

    },

    scrollLeft: function () {

        // TODO rewrite for this view
        var scrollLeft = currentBox.scrollLeft() - Constants.boxScroll;
        scrollLeft = scrollLeft < 0 ? 0 : scrollLeft;
        currentBox.scrollLeft(scrollLeft);

    },

    scrollRight: function () {

        // TODO rewrite for this view
        var scrollWidth = currentBox[0].scrollWidth;
        var scrollLeft = currentBox.scrollLeft() + Constants.boxScroll;
        scrollLeft = scrollLeft > scrollWidth ? scrollWidth : scrollLeft;
        currentBox.scrollLeft(scrollLeft);

    },

    switchTo: function (model) {

        if (this.currentModel) {
            this.currentModel.set('isActive', false);
        }
        model.set('isActive', true);
        this.currentModel = model;

        // scroll window to show current box fully in viewport
        var winBound = {
            left   : $(window).scrollLeft(),
            top    : $(window).scrollTop(),
            right  : $(window).scrollLeft() + $(window).width(),
            bottom : $(window).scrollTop()  + $(window).height()
        };
        var boxBound = this.getBoundaries(model);
        var scrollProps = {scrollTop: winBound.top, scrollLeft: winBound.left};
        if (boxBound.bottom > winBound.bottom) {
            scrollProps.scrollTop = boxBound.bottom + Constants.viewPortPadding - $(window).height();
        }
        if (boxBound.right > winBound.right) {
            scrollProps.scrollLeft = boxBound.right + Constants.viewPortPadding - $(window).width();
        }
        if (winBound.top > boxBound.top) {
            scrollProps.scrollTop = boxBound.top - Constants.viewPortPadding;
        }
        if (winBound.left > boxBound.left) {
            scrollProps.scrollLeft = boxBound.left - Constants.viewPortPadding;
        }
        $('html, body').stop().animate(scrollProps, 100);

    },

    getBoundaries: function (model) {

        if (model) {
            var boundary = {
                top     : model.get('top'),
                left    : model.get('left'),
                bottom  : model.get('top')  + model.get('height'),
                right   : model.get('left') + model.get('width'),
                centerX : model.get('left') + Math.round(model.get('width') / 2),
                centerY : model.get('top')  + Math.round(model.get('height') / 2),
            };
        } else {
            var boundary = {
                top     : 0,
                left    : 0,
                bottom  : 0,
                right   : 0,
                centerX : 0,
                centerY : 0,
            };
        }

        return boundary;
    },

    getClosestInRange: function (lines) {

        var isInRange = function (bound, lines) {
            return _.reduce(lines, function (memo, line) {
                var dotProduct =
                    (line.x2 - line.x1) * (bound.centerY - line.y1) -
                    (line.y2 - line.y1) * (bound.centerX - line.x1);
                return memo && (dotProduct > 0);
            }, true);
        }

        var models = _.sortBy(this.collection.models, function (model) {
            var p1 = this.getBoundaries(this.currentModel);
            var p2 = this.getBoundaries(model);
            return Utility.distanceBetweenPoints(p1.left, p1.top, p2.left, p2.top);
        }, this);

        return _.find(models, function(model) {
            if (this.currentModel && this.currentModel.cid == model.cid) {
                return false;
            } else {
                return isInRange(this.getBoundaries(model), lines);
            }
        }, this);

    },

    navUp: function () {

        var curBound = this.getBoundaries(this.currentModel);

        var lines = [
            {
                x1: curBound.right + 1,
                y1: curBound.top - 1,
                x2: curBound.right,
                y2: curBound.top
            },
            {
                x1: curBound.left,
                y1: curBound.top,
                x2: curBound.left - 1,
                y2: curBound.top - 1
            }
        ];

        var modelFound = this.getClosestInRange(lines);
        if (modelFound) {
            this.switchTo(modelFound);
        }

    },

    navDown: function() {

        var curBound = this.getBoundaries(this.currentModel);

        var lines = [
            {
                x1: curBound.left - 1,
                y1: curBound.bottom + 1,
                x2: curBound.left,
                y2: curBound.bottom
            },
            {
                x1: curBound.right,
                y1: curBound.bottom,
                x2: curBound.right + 1,
                y2: curBound.bottom + 1
            }
        ];

        var modelFound = this.getClosestInRange(lines);
        if (modelFound) {
            this.switchTo(modelFound);
        }

    },

    navLeft: function() {

        var curBound = this.getBoundaries(this.currentModel);

        var lines = [
            {
                x1: curBound.left - 1,
                y1: curBound.top - 1,
                x2: curBound.left,
                y2: curBound.top
            },
            {
                x1: curBound.left,
                y1: curBound.bottom,
                x2: curBound.left - 1,
                y2: curBound.bottom + 1
            }
        ];

        var modelFound = this.getClosestInRange(lines);
        if (modelFound) {
            this.switchTo(modelFound);
        }

    },

    navRight: function() {

        var curBound = this.getBoundaries(this.currentModel);

        var lines = [
            {
                x1: curBound.right + 1,
                y1: curBound.bottom + 1,
                x2: curBound.right,
                y2: curBound.bottom
            },
            {
                x1: curBound.right,
                y1: curBound.top,
                x2: curBound.right + 1,
                y2: curBound.top - 1
            }
        ];

        var modelFound = this.getClosestInRange(lines);
        if (modelFound) {
            this.switchTo(modelFound);
        }

    },

    keyMaps: {

        // TODO multiple letter commands
        'MODE_NORMAL': {

            // TODO relative to specific box
            // scroll the box
            // TODO G or gg to go to beginning or ending
            'K': function() { this.scrollUp(); },
            'J': function() { this.scrollDown(); },
            'H': function() { this.scrollLeft(); },
            'L': function() { this.scrollRight(); },

            // TODO relative to specific box
            // opens file in editor
            'Enter': function() { this.openFile(); },

            // navigate between boxes using shift and arrow letters
            'Shift+K': function() { this.navUp(); },
            'Shift+J': function() { this.navDown(); },
            'Shift+H': function() { this.navLeft(); },
            'Shift+L': function() { this.navRight(); },

            // switch between modes
            'E': function() { this.switchMode('MODE_EDIT'); },

        },

        'MODE_EDIT': {

            // resizes the box
            'Shift+K': function() { this.resizeCurrentBox(0, -1); },
            'Shift+J': function() { this.resizeCurrentBox(0,  1); },
            'Shift+H': function() { this.resizeCurrentBox(-1, 0); },
            'Shift+L': function() { this.resizeCurrentBox( 1, 0); },

            // moves the box
            'K': function() { this.moveCurrentBox(0, -1); },
            'J': function() { this.moveCurrentBox(0,  1); },
            'H': function() { this.moveCurrentBox(-1, 0); },
            'L': function() { this.moveCurrentBox( 1, 0); },

            // closes the box
            'D': function() { this.closeBox(); },

            // back to normal mode
            'Esc': function() { this.switchMode('MODE_NORMAL'); },

        }

    }

});
