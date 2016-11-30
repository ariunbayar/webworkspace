$(function(){
    var cur_line_el = null;

    $.get('/matches', {}, function(matches){
        $.each(matches, function(i, match){
            var el = $('<pre></pre>').appendTo('body');
            el.html(match.line + ': ' + match.text);
            el.attr('data-line', match.line);
        });
        cur_line_el = $('pre:last-child').addClass('active');
    });

    $(document).keydown(function(e){
        if (cur_line_el === null) return;
        var char = String.fromCharCode(e.which);
        var is_line_changed = false;

        cur_line_el.removeClass('active');

        if (char == 'J') {  // down
            var next = cur_line_el.next('pre');
            if (next.length) {
                cur_line_el = next;
                is_line_changed = true;
            }
        } else if (char == 'K') {  // up
            var prev = cur_line_el.prev('pre');
            if (prev.length) {
                cur_line_el = prev;
                is_line_changed = true;
            }
        }

        cur_line_el.addClass('active');

        if (is_line_changed) {
            var line = cur_line_el.attr('data-line');
            $.post('/line', {line: line}, function(rsp){
                console.log(rsp);
            });
        }
    });
});

