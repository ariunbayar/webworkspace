var Constants = {
    gridSize : 30,
    boxScroll: 30
}

function positionsChanged(box, removeFlag)
{
    // TODO let the position view know about positions have changed
    removeFlag = removeFlag || '0';

    var offset = box.offset();
    var width = box.width();
    var height = box.height();

    var input = $('#formPosition input[name="watch[' + box.attr('data-idx') + ']"]');
    input.val(removeFlag + '|' + offset.top + '|' + offset.left + '|' + width  + '|' + height);

    $('#formPosition label.changed').show();
    $('#formPosition label.unchanged').hide();
}

$(function(){
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

    Utility.drawBoxOutline();

    var mainView = new MainView();

    var project = new ProjectView({model: new Project({top: 200, left: 200})});
    mainView.boxes.push(project);
    mainView.currentBox = project;

    var help = new HelpView({model: new Help({top: 300, left: 20})});
    mainView.boxes.push(help);

    $(document).keydown(function(e){
        var key = Utility.translateKeys(e);
        mainView.keyAction(key);
    });

});
