var boxes = [];
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

function navUp()
{
    var currentPosition = currentBox.position();

    var curTop = currentPosition.top;
    var curLeft = currentPosition.left;
    var curRight = left + currentBox.width();
    var curBottom = top + currentBox.height();

    var bottomMost;
    $('.box').each(function(i) {
        var el = $(this);
        var pos = el.position();
        var bottom = pos.top + el.height();
        if (bottom <= top)
        var middle = pos.top + el.height() / 2
        if (pos.top) {

        }
        if (i == 0) {
            bottomMost = bottom;
        }
    });
    break;
}

function keyPressed(ctrlKeyPressed, altKeyPressed, shiftKeyPressed, charCode)
{
    var keyMap = {
        '0|0|1|75': function() { moveCurrentBox(0, -gridSize); },
        '0|0|1|74': function() { moveCurrentBox(0, gridSize); },
        '0|0|1|72': function() { moveCurrentBox(-gridSize, 0); },
        '0|0|1|76': function() { moveCurrentBox(gridSize, 0); },
        '0|0|0|75': function() { navUp(); },
    };
    var key = [ctrlKeyPressed, altKeyPressed, shiftKeyPressed, charCode].join('|');
    //console.log(key);return;

    // call corresponding function
    if (keyMap[key]) {
        keyMap[key]();
    }
}



$(function(){

    $('.box').each(function() {
        var position = $(this).position();
        boxes.push(position);
    });

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

    $('.watch pre').mouseout(function (e) {
        if (window.tmpBox) {
            tmpBox.hide();
        }
    });

    $('.watch pre').dblclick(function(e){
        // TODO find clicked line to locate when editor opens
        var fileId = $(e.target).parents('.watch').attr('data-idx');
        $.get(window.location.pathname + '?open=' + fileId);
    });

});
