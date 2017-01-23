var Constants = {
    gridSize : 30,
    boxScroll: 30,
    viewPortPadding: 40
}
var mainCollection;

$(function(){

    setTimeout(function(){
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
                    zIndex: 200,
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
    }, 1000);

    mainCollection = new MainCollection();
    var mainView = new MainView({collection: mainCollection});
    mainCollection.fetch().then(function(){
        mainView.render();
    });


    $(document).keydown(function(e){
        var key = Utility.translateKeys(e);
        mainView.keyAction(key);
    });

    window.mainView = mainView;

});
