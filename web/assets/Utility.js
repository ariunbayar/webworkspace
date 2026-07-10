var Utility = {

    _outlineContainers: null,

    // Show the outline (normal/rest mode) or hide it entirely (during
    // move/resize/pan/zoom) for smoothness. Toggles display so the layers keep
    // their true colours at rest — no blur/contrast to wash them out.
    showOutline: function (on) {
        (this._outlineContainers || []).forEach(function (c) {
            c.style.display = on ? '' : 'none';
        });
    },

    // Layered rounded outline behind each box: three concentric colour layers,
    // kept glued to it by a MutationObserver on the box's inline style, so they
    // reposition whenever the box moves or resizes (mouse drag/resize or keyboard).
    drawBoxOutline: function () {

        var LAYERS = [
            {color: '#9AAABA', b: 85, cls: 'outline1'},   // grey-blue, outermost
            {color: '#fff',    b: 80, cls: 'outline2'},   // white, middle
            {color: '#DDEEFF', b: 60, cls: 'outline3'}    // light blue, innermost
        ];
        var self = this;

        // size the containers to span all boxes (+ halo margin)
        var maxR = 0, maxB = 0;
        $('.box').each(function () {
            maxR = Math.max(maxR, this.offsetLeft + this.offsetWidth);
            maxB = Math.max(maxB, this.offsetTop + this.offsetHeight);
        });
        // one container per colour layer; hidden as a group during interaction
        // via showOutline() and shown at rest (see the toggle above).
        var containers = LAYERS.map(function () {
            return $('<div>').addClass('outline-layer').appendTo('body').css({
                position: 'absolute', top: 0, left: 0,
                width: (maxR + 300) + 'px', height: (maxB + 300) + 'px'
            })[0];
        });
        this._outlineContainers = containers;

        $('.box').each(function () {
            var box = this;
            box.style.zIndex = box.style.zIndex || 100;   // box sits above its outline
            var layers = LAYERS.map(function (spec, i) {
                var el = $('<div>').appendTo(containers[i]).addClass(spec.cls).css({
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
