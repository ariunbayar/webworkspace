<?php

/*
echo "
SELECT 1
KEYS *
GET directory
GET watches
" | redis-cli
*/

ini_set('error_reporting', E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);


/* Redis setup and functions */
    $redis = new Redis();
    $redis->connect('127.0.0.1', 6379);
    $redis->select(1);

    function get($key) {
        global $redis;
        return $redis->get($key);
    }
    function set($key, $value) {
        global $redis;
        return $redis->set($key, $value);
    }

/* Manager to load and save configs */
    class Browser {

        public $directory;
        public $currentDir = "";
        public $dirs = [];
        public $files = [];


        function __construct($directory)
        {
            $this->directory = $directory;

            // Current directory
            $path = array_key_exists('path', $_GET) ? $_GET['path'] : '';
            $this->currentDir = $this->directory . $path;

            // List directories
            $items = glob($this->currentDir . '/*', GLOB_ONLYDIR);
            $this->dirs = array_map(function($item) {
                return substr($item, strlen($this->currentDir) + 1);
            }, $items);

            // List files
            $items = array_filter(glob($this->currentDir . '/*'), 'is_file');
            $this->files = array_map(function($item) {
                return substr($item, strlen($this->currentDir) + 1);
            }, $items);
        }

        function removeDirPrefix($path) {
            return substr($path, strlen($this->directory));
        }

        function getUpperDir() {
            return $this->removeDirPrefix(dirname($this->currentDir));
        }

        function getAppended($suffix) {
            return $this->removeDirPrefix($this->currentDir) . '/' . $suffix;
        }

        function isMainDir() {
            return $this->currentDir == $this->directory;
        }

    }

    class FileWatch implements Serializable {

        public $x = 10;
        public $y = 10;
        public $width = 150;
        public $height = 200;
        public $file;
        public $numLines = 0;
        public $remove = 0;

        function __construct($file)
        {
            $this->file = $file;
        }

        function serialize()
        {
            return
                $this->x . '|' .
                $this->y . '|' .
                $this->width . '|' .
                $this->height . '|' .
                $this->file;
        }

        function unserialize($data)
        {
            list($this->x, $this->y, $this->width, $this->height, $this->file) = explode('|', $data, 5);
        }

        function load($dump)
        {
            list($this->remove, $this->x, $this->y, $this->width, $this->height) = explode('|', $dump, 5);
        }

        function dump()
        {
            return
                '0|' .
                $this->x . '|' .
                $this->y . '|' .
                $this->width . '|' .
                $this->height;
        }

        function toStyleForWatch()
        {
             return 'top:' . $this->x . 'px; left:' . $this->y . 'px';
        }

        function toStyleForPre()
        {
             return 'width:' . $this->width . 'px; height:' . $this->height . 'px';
        }

        function getSource()
        {
            global $m;
            $handle = fopen($m->browser->directory . $this->file, "r");

            $content = '';
            $this->numLines = 0;

            while (!feof($handle)){
              $content .= fgets($handle);
              $this->numLines++;
            }
            fclose($handle);

            return $content;
        }
    }

    class Manager {

        // saved configs
        public $browser;
        public $watches;

        /**
         * Loads configurations and setup values
         */
        function __construct()
        {

            // Main directory
            $directory = get('directory');
            if (!$directory) {
                $directory = getcwd();
            }
            $this->browser = new Browser($directory);

            // Watching files
            $watches = get('watches');
            $this->watches = $watches ? unserialize($watches) : [];
        }

        function save()
        {
            for ($i = count($this->watches) - 1; $i >= 0; $i--) {
                if ($this->watches[$i]->remove == 1) {
                    array_splice($this->watches, $i, 1);
                }
            }
            set('directory', rtrim($this->browser->directory, '/'));
            set('watches', serialize($this->watches));
        }

    }

    $m = new Manager();

/* Helpers */
    function saveAndRedirect($url) {
        global $m;
        $m->save();
        header('Location: ' . $url);
        exit(0);
    }

    function openFileAndStop($watch) {
        global $m;
        $file = $m->browser->directory . $watch->file;
        exec("gnome-terminal -e \"gvim '$file'\"");
        exit(0);
    }

/* Form submission */
    if (array_key_exists('directory', $_POST)) {
        $m->directory = $_POST['directory'];
        saveAndRedirect($_SERVER['REQUEST_URI']);
    }

    if (array_key_exists('pick', $_GET)) {
        // TODO don't add if already exists
        $m->watches[] = new FileWatch($_GET['pick']);
        $qargs = $_GET;
        unset($qargs['pick']);
        saveAndRedirect($_SERVER['SCRIPT_NAME'] . '?' . http_build_query($qargs));
    }

    if (array_key_exists('watch', $_POST)) {
        // save watch file positions
        foreach ($m->watches as $i => $watch) {
            $watch->load($_POST['watch'][$i]);
        }
        saveAndRedirect($_SERVER['REQUEST_URI']);
    }

    if (array_key_exists('open', $_GET)) {
        openFileAndStop($m->watches[$_GET['open']]);
    }


?><!DOCTYPE html>
<html>
<head>
    <style>
    *{ margin: 0; padding: 0; font-family: Monospace; font-size: 12px;}

    a{ color: #0099dd; text-decoration: none; }
    a:hover, a:focus { color: #0099dd; text-decoration: underline; }

    .box{
        border-color: #ccc;
        border-style: solid;
        border-width: 10px 1px 1px 1px;
        background-color: #eee;
        position: absolute;
    }
    .browser ul{
        width: 200px;
        overflow-x: auto;
    }
    .browser ul li{
        font-size: 8px;
        width: 400px;
    }

    .watch{
        font-size: 12px;
        color: #657b83;
        resize: both;
        overflow: auto;
    }
    .watch .filename{
        font-weight: bold;
    }
    .watch pre{
        display: block;
        font-size: 2px;
        background-color: #fdf6e3;
        /*
        resize: both;
        overflow: auto;
        */
        margin: 0;
    }

/*
    div.watch:hover::before{
        background: #eee;
        border: 1px solid #ccc;
        position: absolute;
        content: "";
        top: -22px;
        right: -1px;
        width: 80px;
        height: 20px;
    }
*/
    </style>
</head>
<body>

<form action="" method="POST">
    <input type="text" name="directory" value="<?php echo get('directory')?>"/>

    <input type="submit" value="Save and Reload"/>
</form>

<form id="formPosition" action="" method="POST">
    <label class="unchanged">Positions haven't changed</label>
    <label class="changed" style="display: none; color: red;">Positions have changed</label>
    <?php foreach ($m->watches as $i => $w) { ?>
    <input type="hidden" name="watch[<?php echo $i ?>]" value="<?php echo $w->dump() ?>"/>
    <?php } ?>
    <input type="submit" value="Save and Reload"/>
</form>


<br/>

<!-- File browser -->
<?php $b = $m->browser ?>
<div class="browser box">
    <?php echo $b->currentDir ?>
    <ul>
        <?php if (!$b->isMainDir()) { ?>
        <li><a href="?path=<?php echo $b->getUpperDir() ?>">..</a></li>
        <?php } ?>

        <?php foreach ($b->dirs as $dir) { ?>
        <li><a href="?path=<?php echo $b->getAppended($dir) ?>">/<?php echo $dir ?></a></li>
        <?php } ?>

        <?php foreach ($b->files as $file) { ?>
        <li>+ <a href="?path=<?php echo $b->removeDirPrefix($b->currentDir)?>&pick=<?php echo $b->getAppended($file) ?>"><?php echo $file ?></a></li>
        <?php } ?>
    </ul>
</div>


<!-- Watching files -->
<?php foreach ($m->watches as $i => $watch) { ?>
<div class="watch box" data-idx="<?php echo $i ?>" style="<?php echo $watch->toStyleForWatch() ?>">
    <div class="filename"><?php echo $watch->file ?></div>
    <a href="#" title="close" class="close">X</a>
    <a href="#" title="resize to default 150x200" class="resize">R</a>
    <?php $content = $watch->getSource() ?>
    <pre style="<?php echo $watch->toStyleForPre() ?>" data-num-lines="<?php echo $watch->numLines ?>"><?php echo htmlspecialchars($content) ?></pre>
</div>
<?php } ?>

<div style="top: 20px; left: 1350px;" class="box preview"><pre></pre></div>


<script src="//code.jquery.com/jquery-1.11.3.min.js"></script>
<script>
$(function(){

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

    var throttle = function (fn, threshhold, scope) {
        threshhold || (threshhold = 250);
        var last, deferTimer;
        return function () {
            var context = scope || this;

            var now = +new Date,
                args = arguments;
            if (last && now < last + threshhold) {
                // hold on to it
                clearTimeout(deferTimer);
                deferTimer = setTimeout(function () {
                    last = now;
                    fn.apply(context, args);
                }, threshhold);
            } else {
                last = now;
                fn.apply(context, args);
            }
        };
    }

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
</script>
</body>
</html>
