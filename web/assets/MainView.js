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

    boxes: [],
    currentBox: null,
    currentMode: 'MODE_NORMAL',

    render: function () {

        this.collection.each(function(model) {
            var view = model.getView();
            this.boxes.push(view);
        }, this);
        this.currentBox = this.boxes[this.boxes.length - 1];

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

        var modeChange = this.currentMode + ' -> ' + newMode;

        switch (modeChange) {
            case  'MODE_EDIT -> MODE_NORMAL':
                this.currentBox.$el.css('border-color', '#ccc');
                break;
            case  'MODE_NORMAL -> MODE_EDIT':
                this.currentBox.$el.css('border-color', '#00f');
                break;

            default:
                console.error('Unknown mode change: ' + modeChange);
        }

        this.currentMode = newMode;

    },

    closeBox: function () {

        // TODO rewrite for this view
        positionsChanged(currentBox, 1);
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

        var curBoxModel = this.currentBox.model;
        var top  = curBoxModel.get('top');
        var left = curBoxModel.get('left');

        // normalize current box position to grid size
        top  = Math.round(top  / Constants.gridSize) * Constants.gridSize;
        left = Math.round(left / Constants.gridSize) * Constants.gridSize;

        // move with x and y by grid size
        curBoxModel.set('top',  top  + y * Constants.gridSize);
        curBoxModel.set('left', left + x * Constants.gridSize);

         positionsChanged(this.currentBox.$el);

    },

    resizeCurrentBox: function (x, y) {

        var curBoxModel = this.currentBox.model;

        // normalize current box size to grid
        var width  = Math.round(curBoxModel.get('width')  / Constants.gridSize) * Constants.gridSize;
        var height = Math.round(curBoxModel.get('height') / Constants.gridSize) * Constants.gridSize;

        // resize with x and y by grid size
        curBoxModel.set('width',  width  + x * Constants.gridSize);
        curBoxModel.set('height', height + y * Constants.gridSize);

        positionsChanged(this.currentBox.$el);

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

    switchTo: function (box) {

        // TODO rewrite for this view
        box.addClass('active');
        currentBox.removeClass('active');
        currentBox = box;

        // scroll window to show current box fully in viewport
        var viewPortPadding = 40;
        var winBound = {
            left   : $(window).scrollLeft(),
            top    : $(window).scrollTop(),
            right  : $(window).scrollLeft() + $(window).width(),
            bottom : $(window).scrollTop()  + $(window).height()
        };
        var boxBound = {
            left   : currentBox.offset().left,
            top    : currentBox.offset().top,
            right  : currentBox.offset().left + currentBox.width(),
            bottom : currentBox.offset().top  + currentBox.height()
        };
        var scrollProps = {scrollTop: winBound.top, scrollLeft: winBound.left};
        if (boxBound.bottom > winBound.bottom) {
            scrollProps.scrollTop = boxBound.bottom + viewPortPadding - $(window).height();
        }
        if (boxBound.right > winBound.right) {
            scrollProps.scrollLeft = boxBound.right + viewPortPadding - $(window).width();
        }
        if (winBound.top > boxBound.top) {
            scrollProps.scrollTop = boxBound.top - viewPortPadding;
        }
        if (winBound.left > boxBound.left) {
            scrollProps.scrollLeft = boxBound.left - viewPortPadding;
        }
        $('html, body').stop().animate(scrollProps, 100);

    },

    getElementBoundaries: function (el) {

        // TODO rewrite for this view
        var pos = el.offset();
        var width = el.width();
        var height = el.height();

        var boundaries = {
            top: pos.top - parseInt(el.css('border-top-width')),
            left: pos.left - parseInt(el.css('border-left-width')),
            right: pos.left + width + parseInt(el.css('border-right-width')),
            bottom: pos.top + height + parseInt(el.css('border-bottom-width')),
            centerX: pos.left + (width + parseInt(el.css('border-left-width')) + parseInt(el.css('border-right-width'))) / 2,
            centerY: pos.top + (height + parseInt(el.css('border-top-width')) + parseInt(el.css('border-bottom-width'))) / 2,
            isInColumn: function (bound) {
                var result =
                    this.left < bound.centerX && bound.centerX < this.right ||
                    this.left < bound.left    && bound.left    < this.right ||
                    this.left < bound.right   && bound.right   < this.right ||
                    bound.left < this.centerX && this.centerX < bound.right ||
                    bound.left < this.left    && this.left    < bound.right ||
                    bound.left < this.right   && this.right   < bound.right;
                return result;
            },
            isInRow: function(bound) {
                var result =
                    this.top < bound.centerY && bound.centerY < this.bottom ||
                    this.top < bound.top     && bound.top     < this.bottom ||
                    this.top < bound.bottom  && bound.bottom  < this.bottom ||
                    bound.top < this.centerY && this.centerY < bound.bottom ||
                    bound.top < this.top     && this.top     < bound.bottom ||
                    bound.top < this.bottom  && this.bottom  < bound.bottom;
                return result;
            },
            isAbove: function (bound, ignoreColumnCheck) {
                var isAbove = bound.top < this.top;
                return isAbove && (ignoreColumnCheck || this.isInColumn(bound));
            },
            isBelow: function (bound, ignoreColumnCheck) {
                var isBelow = this.bottom < bound.bottom;
                return isBelow && (ignoreColumnCheck || this.isInColumn(bound));
            },
            isLeft: function (bound, ignoreRowCheck) {
                var isLeft = bound.left < this.left;
                return isLeft && (ignoreRowCheck || this.isInRow(bound));
            },
            isRight: function (bound, ignoreRowCheck) {
                var isRight = this.right < bound.right;
                return isRight && (ignoreRowCheck || this.isInRow(bound));
            }
        };

        return boundaries;

    },

    navUp: function () {

        // TODO please optimize these nav functions
        var curBound = getElementBoundaries(currentBox);

        var bottomMostBox = null;
        var bottomMost = null;
        var bottomMostBoxNoColumn = null;
        var bottomMostNoColumn = null;
        $('.box').each(function() {
            var el = $(this);
            bound = getElementBoundaries(el);

            if (curBound.isAbove(bound, true)) {
                if (bottomMostNoColumn === null || bound.bottom > bottomMostNoColumn) {
                    bottomMostNoColumn = bound.bottom;
                    bottomMostBoxNoColumn = el;
                }
            }
            if (curBound.isAbove(bound)) {
                if (bottomMost === null || bound.bottom > bottomMost) {
                    bottomMost = bound.bottom;
                    bottomMostBox = el;
                }
            }
        });
        if (bottomMostBox) {
            switchTo(bottomMostBox);
        } else if (bottomMostBoxNoColumn) {
            switchTo(bottomMostBoxNoColumn);
        }

    },

    navDown: function() {

        // TODO rewrite for this view
        var curBound = getElementBoundaries(currentBox);

        var topMostBox = null;
        var topMost = null;
        var topMostBoxNoColumn = null;
        var topMostNoColumn = null;
        $('.box').each(function() {
            var el = $(this);
            bound = getElementBoundaries(el);

            if (curBound.isBelow(bound, true)) {
                if (topMostNoColumn === null || bound.top < topMostNoColumn) {
                    topMostNoColumn = bound.top;
                    topMostBoxNoColumn = el;
                }
            }
            if (curBound.isBelow(bound)) {
                if (topMost === null || bound.top < topMost) {
                    topMost = bound.top;
                    topMostBox = el;
                }
            }
        });
        if (topMostBox) {
            switchTo(topMostBox);
        } else if (topMostBoxNoColumn) {
            switchTo(topMostBoxNoColumn);
        }

    },

    navLeft: function () {

        // TODO rewrite for this view
        var curBound = getElementBoundaries(currentBox);

        var rightMostBox = null;
        var rightMost = null;
        var rightMostBoxNoRow = null;
        var rightMostNoRow = null;
        $('.box').each(function() {
            var el = $(this);
            bound = getElementBoundaries(el);

            if (curBound.isLeft(bound, true)) {
                if (rightMostNoRow === null || bound.right > rightMostNoRow) {
                    rightMostNoRow = bound.right;
                    rightMostBoxNoRow = el;
                }
            }
            if (curBound.isLeft(bound)) {
                if (rightMost === null || bound.right > rightMost) {
                    rightMost = bound.right;
                    rightMostBox = el;
                }
            }
        });
        if (rightMostBox) {
            switchTo(rightMostBox);
        } else if (rightMostBoxNoRow) {
            switchTo(rightMostBoxNoRow);
        }

    },

    navRight: function () {

        // TODO rewrite for this view
        var curBound = getElementBoundaries(currentBox);

        var leftMostBox = null;
        var leftMost = null;
        var leftMostBoxNoRow = null;
        var leftMostNoRow = null;
        $('.box').each(function() {
            var el = $(this);
            bound = getElementBoundaries(el);

            if (curBound.isRight(bound, true)) {
                if (leftMostNoRow === null || bound.left < leftMostNoRow) {
                    leftMostNoRow = bound.left;
                    leftMostBoxNoRow = el;
                }
            }
            if (curBound.isRight(bound)) {
                if (leftMost === null || bound.left < leftMost) {
                    leftMost = bound.left;
                    leftMostBox = el;
                }
            }
        });
        if (leftMostBox) {
            switchTo(leftMostBox);
        } else if (leftMostBoxNoRow) {
            switchTo(leftMostBoxNoRow);
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
