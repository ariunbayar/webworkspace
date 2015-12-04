var Utility = {

    drawBoxOutline: function () {

        // outline borders
        var borderWidth=5;
        var borderRange=80;
        var colors = ['#F27360', '#9AAABA', '#6E6F71', '#485868', '#F3C766', '#FBE6E1', '#BCBDC1', '#9FC2BB', '#F5A46C'];
        var fn = function(c, b, cls){
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

        // change colors
        //var i = 0;
        //setInterval(function(){
            //$('.back').css('background-color', colors[i]);
            //i = (i + 1) % colors.length;
        //}, 3000)

    },

    translateKeys: function (e) {

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

    },

    distanceBetweenPoints: function (x1, y1, x2, y2) {
        return Math.sqrt(Math.pow(x1 - x2, 2) + Math.pow(y1 - y2, 2));
    }

};
