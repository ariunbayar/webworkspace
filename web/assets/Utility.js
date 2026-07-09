var Utility = {

    // Layered rounded outline behind each box. Each box owns its 3 layers, kept
    // glued to it: a MutationObserver on the box's inline style repositions them
    // whenever it moves or resizes (mouse drag/resize or keyboard).
    drawBoxOutline: function () {

        var LAYERS = [
            {color: '#9AAABA', b: 85, cls: 'back'},   // grey-blue, outermost
            {color: '#fff',    b: 80, cls: 'front'},  // white
            {color: '#DDEEFF', b: 60, cls: 'front1'}  // light blue, innermost
        ];
        var self = this;

        $('.box').each(function () {
            var box = this;
            box.style.zIndex = box.style.zIndex || 100;   // box sits above its outline
            var layers = LAYERS.map(function (spec) {
                var el = $('<div>').appendTo('body').addClass(spec.cls).css({
                    backgroundColor: spec.color,
                    position: 'absolute',
                    borderRadius: spec.b + 'px'
                })[0];
                return {el: el, b: spec.b};
            });
            $(box).data('outline', layers);
            self.updateBoxOutline(box);
        });

        if (!this._outlineObserver) {
            this._outlineObserver = new MutationObserver(function (muts) {
                muts.forEach(function (m) {
                    if (m.target.classList && m.target.classList.contains('box')) {
                        self.updateBoxOutline(m.target);
                    }
                });
            });
            this._outlineObserver.observe(document.body, {
                attributes: true, attributeFilter: ['style'], subtree: true
            });
        }
    },

    updateBoxOutline: function (box) {
        var layers = $(box).data('outline');
        if (!layers) { return; }
        var t = box.offsetTop, l = box.offsetLeft, w = box.offsetWidth, h = box.offsetHeight;
        layers.forEach(function (layer) {
            layer.el.style.top = (t - layer.b) + 'px';
            layer.el.style.left = (l - layer.b) + 'px';
            layer.el.style.width = (w + layer.b * 2) + 'px';
            layer.el.style.height = (h + layer.b * 2) + 'px';
        });
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
