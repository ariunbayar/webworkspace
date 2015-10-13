var boxes = [];
var currentView = null;
var currentBox = $('.help').addClass('active');

var Constants = {
    MODE_NORMAL: 'MODE_NORMAL',
    MODE_EDIT  : 'MODE_EDIT',
    gridSize : 30,
    boxScroll: 30
}

var currentMode = 'MODE_NORMAL';

var keyMaps = {
    // TODO multiple letter commands
    'MODE_NORMAL': {
        // scroll the box
        // TODO G or gg to go to beginning or ending
        'K': scrollUp,
        'J': scrollDown,
        'H': scrollLeft,
        'L': scrollRight,
        // navigate between boxes using shift and arrow letters
        'Shift+K': navUp,
        'Shift+J': navDown,
        'Shift+H': navLeft,
        'Shift+L': navRight,
        // opens file in editor
        'Enter': openFile,
        // switch between modes
        'E': function() { switchMode('MODE_EDIT'); },
    },
    'MODE_EDIT': {
        // resizes the box
        'Shift+K': function() { resizeCurrentBox(0, -1); },
        'Shift+J': function() { resizeCurrentBox(0,  1); },
        'Shift+H': function() { resizeCurrentBox(-1, 0); },
        'Shift+L': function() { resizeCurrentBox( 1, 0); },
        // moves the box
        'K': function() { moveCurrentBox(0, -1); },
        'J': function() { moveCurrentBox(0,  1); },
        'H': function() { moveCurrentBox(-1, 0); },
        'L': function() { moveCurrentBox( 1, 0); },
        // closes the box
        'D': closeBox,
        // back to normal mode
        'Esc': function() { switchMode('MODE_NORMAL'); },
    }
};

function positionsChanged(box, removeFlag)
{
    removeFlag = removeFlag || '0';

    var offset = box.offset();
    var width = box.width();
    var height = box.height();

    var input = $('#formPosition input[name="watch[' + box.attr('data-idx') + ']"]');
    input.val(removeFlag + '|' + offset.top + '|' + offset.left + '|' + width  + '|' + height);

    $('#formPosition label.changed').show();
    $('#formPosition label.unchanged').hide();
}

function moveCurrentBox(x, y)
{
    var offset = currentBox.offset();

    // normalize current box offset to grid size
    offset.top = Math.round(offset.top / Constants.gridSize) * Constants.gridSize;
    offset.left = Math.round(offset.left / Constants.gridSize) * Constants.gridSize;

    // move with x and y by grid size
    offset.top = offset.top + y * Constants.gridSize;
    offset.left = offset.left + x * Constants.gridSize;
    currentBox.offset(offset);

    positionsChanged(currentBox);
}

function resizeCurrentBox(x, y)
{
    // normalize current box size to grid
    width = Math.round(currentBox.width() / Constants.gridSize) * Constants.gridSize;
    height = Math.round(currentBox.height() / Constants.gridSize) * Constants.gridSize;

    // resize with x and y by grid size
    currentBox.height(height + y * Constants.gridSize);
    currentBox.width(width + x * Constants.gridSize);

    positionsChanged(currentBox);
}

function switchMode(newMode)
{
    var modeChange = currentMode + ' -> ' + newMode;

    switch (modeChange) {
        case  'MODE_EDIT -> MODE_NORMAL':
            $('.active').css('border-color', '#ccc');
            break;
        case  'MODE_NORMAL -> MODE_EDIT':
            $('.active').css('border-color', '#00f');
            break;

        default:
            console.error('Unknown mode change: ' + modeChange);
    }

    currentMode = newMode;
}

function getElementBoundaries(el)
{
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
}

function switchTo(box)
{
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
}

function scrollUp()
{
    var scrollTop = currentBox.scrollTop() - Constants.boxScroll;
    scrollTop = scrollTop < 0 ? 0 : scrollTop;
    currentBox.scrollTop(scrollTop);
}

function scrollDown()
{
    var scrollHeight = currentBox[0].scrollHeight;
    var scrollTop = currentBox.scrollTop() + Constants.boxScroll;
    scrollTop = scrollTop > scrollHeight ? scrollHeight : scrollTop;
    currentBox.scrollTop(scrollTop);
}

function scrollLeft()
{
    var scrollLeft = currentBox.scrollLeft() - Constants.boxScroll;
    scrollLeft = scrollLeft < 0 ? 0 : scrollLeft;
    currentBox.scrollLeft(scrollLeft);
}

function scrollRight()
{
    var scrollWidth = currentBox[0].scrollWidth;
    var scrollLeft = currentBox.scrollLeft() + Constants.boxScroll;
    scrollLeft = scrollLeft > scrollWidth ? scrollWidth : scrollLeft;
    currentBox.scrollLeft(scrollLeft);
}

function navUp()
{
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
}

function navDown()
{
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
}

function navLeft()
{
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
}

function navRight()
{
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
}

function openFile()
{
    // TODO pass scroll to editor
    var fileId = currentBox.attr('data-idx');
    $.get(window.location.pathname + '?open=' + fileId);
}

function closeBox()
{
    positionsChanged(currentBox, 1);
    setTimeout((function(el) {
        el.addClass('hinge');
        return function () {
            // switch to some other window
            navLeft(); navRight(); navUp(); navDown();
            el.remove();
        }
    })(currentBox), 1000);
}

function keyPressed(key)
{
    if (keyMaps[currentMode] && keyMaps[currentMode][key]) {
        keyMaps[currentMode][key]();
    }
}

function translateKeys(e)
{
    var charMap = {
        27: 'Esc',
        13: 'Enter'
    };

    var key = '';

    key += e.ctrlKey ? 'Ctrl+' : '';
    key += e.altKey ? 'Alt+' : '';
    key += e.shiftKey ? 'Shift+' : '';
    // A-Z
    key += (65 <= e.which && e.which <= 90) ? String.fromCharCode(e.which) : '';
    // Other non-printable characters
    key += charMap[e.which] ? charMap[e.which] : '';

    return key;
}

$(function(){
    $(document).keydown(function(e){
        var key = translateKeys(e);
        keyPressed(key);
        currentView.keyAction(key);
    });

    $('.watch pre').mousemove(function (e) {
        var pre = $(e.target);
        var tmpBox = $('.tmpBox');
        var boxHeight = 100;

        // make sure the indicator exists
        if (tmpBox.length == 0) {
            tmpBox = $('<div class="tmpBox">');
            tmpBox.css({
                position: 'absolute',
                borderRight: '3px solid rgba(225, 0, 0, 0.3)',
                height: boxHeight,
            });
            tmpBox.appendTo('body');
        }

        // position the indicator
        var left = pre.offset().left;
        tmpBox.css({
            left: left,
            top: e.pageY - boxHeight / 2,
        });

        // define line range
        var height = parseInt(pre.css('height'));
        var heightBegin = e.offsetY - boxHeight / 2;
        var heightEnd = e.offsetY + boxHeight / 2;
        var lineTotal = parseInt(pre.attr('data-num-lines'));
        var lineBegin = Math.round((heightBegin < 0 ? 0 : heightBegin) / height * lineTotal);
        var lineEnd = Math.round((heightEnd > height ? height : heightEnd) / height * lineTotal);

        // show source code
        var newLine = "\n";
        var contentArray = pre.html().split(newLine);
        $('.preview pre').html(contentArray.slice(lineBegin, lineEnd).join(newLine));
    });

    // outline borders
    borderWidth=150;
    borderRange=200;
    colors = ['#F27360', '#9AAABA', '#6E6F71', '#485868', '#F3C766', '#FBE6E1', '#BCBDC1', '#9FC2BB', '#F5A46C'];
    fn = function(c, b, cls){
        els = $('.box');
        els.css('z-index', 100);
        els.each(function(){
            el=$(this);
            p=el.position();
            w=el.width();
            h=el.height();
            $('<div>').appendTo('body').css({
                backgroundColor: c,
                position: 'absolute',
                top: (p.top-b)+'px',
                left: (p.left-b)+'px',
                borderRadius: b+'px',
                width: (w+b*2)+'px',
                height: (h+b*2)+'px'
            }).addClass(cls);
        });
    };
    fn(colors[1], borderRange+borderWidth, 'back');
    fn('#fff', borderRange, 'front');
    fn('#DDEEFF', borderRange-20, 'front1');
    //i=0;setInterval(function(){ $('.back').css('background-color', colors[i]); i=(i+1)%colors.length; }, 3000)

    // project widget
    var project = new ProjectView({
        model: new Project({top: 200, left: 200})
    });
    currentView = project;

});
