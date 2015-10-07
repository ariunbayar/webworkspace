var currentBox = $('.help').addClass('active');
var gridSize = 30;

function positionsChanged()
{
    $('#formPosition label.changed').show();
    $('#formPosition label.unchanged').hide();
}

function moveCurrentBox(x, y)
{
    var position = currentBox.position();
    currentBox.css({
        top: position.top + y,
        left: position.left + x
    });
    positionsChanged();
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

function keyPressed(ctrlKeyPressed, altKeyPressed, shiftKeyPressed, charCode)
{
    var keyMap = {
        '0|0|1|75': function() { moveCurrentBox(0, -gridSize); },
        '0|0|1|74': function() { moveCurrentBox(0, gridSize); },
        '0|0|1|72': function() { moveCurrentBox(-gridSize, 0); },
        '0|0|1|76': function() { moveCurrentBox(gridSize, 0); },
        '0|0|0|75': function() { navUp(); },
        '0|0|0|74': function() { navDown(); },
        '0|0|0|72': function() { navLeft(); },
        '0|0|0|76': function() { navRight(); },
    };
    var key = [ctrlKeyPressed, altKeyPressed, shiftKeyPressed, charCode].join('|');
    //console.log(key);return;

    // call corresponding function
    if (keyMap[key]) {
        keyMap[key]();
    }
}



$(function(){

    $(document).keydown(function(e){
        keyPressed(e.ctrlKey & 1, e.altKey & 1, e.shiftKey & 1, e.which);
    });

    $.fn.drags = function(opt) {

        opt = $.extend({handle:"",cursor:"move",dragstop: null}, opt);

        if(opt.handle === "") {
            var $el = this;
        } else {
            var $el = this.find(opt.handle);
        }

        return $el.css('cursor', opt.cursor).on("mousedown", function(e) {
            if(opt.handle === "") {
                var $drag = $(this).addClass('draggable');
            } else {
                var $drag = $(this).addClass('active-handle').parent().addClass('draggable');
            }
            var z_idx = $drag.css('z-index'),
                drg_h = $drag.outerHeight(),
                drg_w = $drag.outerWidth(),
                pos_y = $drag.offset().top + drg_h - e.pageY,
                pos_x = $drag.offset().left + drg_w - e.pageX;
            $drag.css('z-index', 1000).parents().on("mousemove", function(e) {
                $('.draggable').offset({
                    top:e.pageY + pos_y - drg_h,
                    left:e.pageX + pos_x - drg_w
                }).on("mouseup", function() {
                    $(this).removeClass('draggable').css('z-index', z_idx);
                });
            });
            e.preventDefault(); // disable selection
        }).on("mouseup", function() {

            if (opt.dragstop) {
                opt.dragstop($(this));
            }
            if(opt.handle === "") {
                $(this).removeClass('draggable');
            } else {
                $(this).removeClass('active-handle').parent().removeClass('draggable');
            }
        });

    }

    $('.browser').drags();

    var updateInput = function (watch, removeFlag) {
        removeFlag = removeFlag || '0';
        var input = $('#formPosition input[name="watch[' + watch.attr('data-idx') + ']"]');
        var top = parseInt(watch.css('top'));
        var left = parseInt(watch.css('left'));
        var pre = watch.find('pre');
        var width = parseInt(pre.css('width'));
        var height = parseInt(pre.css('height'));
        input.val(removeFlag + '|' + top + '|' + left + '|' + width  + '|' + height);
        $('#formPosition label.changed').show();
        $('#formPosition label.unchanged').hide();
    }

    $('.watch').drags({
        dragstop: function(handle){
            var watch = $(handle).parents('.watch');
            updateInput(watch);
        },
        handle: '.filename'
    });

    $('.watch a.close').click(function() {
        var watch = $(this).parents('.watch');
        updateInput(watch, 1);
        watch.remove();
    });

    $('.watch a.resize').click(function() {
        var watch = $(this).parents('.watch');
        watch.find('pre').css({width: 150, height: 200});
        updateInput(watch);
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

    $('.watch pre').dblclick(function(e){
        // TODO find clicked line to locate when editor opens
        var fileId = $(e.target).parents('.watch').attr('data-idx');
        $.get(window.location.pathname + '?open=' + fileId);
    });

});
