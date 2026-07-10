<?php
// Cache-bust assets: append ?v=<mtime> so the URL changes whenever the file
// does. The php dev server sends no cache headers, so without this the browser
// can serve a stale JS/CSS on a normal reload. Docroot is web/, this file is in
// templates/, so an "/assets/x" URL maps to ../web/assets/x on disk.
function asset($url) {
    $v = @filemtime(__DIR__ . '/../web' . $url);
    return $url . ($v ? '?v=' . $v : '');
}
?>
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="<?= asset('/assets/main.css') ?>" type="text/css" media="all" />
    <link rel="icon" type="image/png" href="/assets/favicon.png">
</head>
<body>

    <img src="/assets/logo.png" style="position: absolute; top: 750px; left: 800px; z-index: 100; box-shadow: 0 0 0 5px #fff, 0 0 0 6px #ccc"/>

    <?php echo $mainContent ?>
    <script src="<?= asset('/assets/libs/jquery-2.1.4.min.js') ?>"></script>
    <script src="<?= asset('/assets/libs/underscore-min.js') ?>"></script>
    <script src="<?= asset('/assets/libs/backbone-min.js') ?>"></script>
    <script src="<?= asset('/assets/Utility.js') ?>"></script>
    <script src="<?= asset('/assets/Project.js') ?>"></script>
    <script src="<?= asset('/assets/File.js') ?>"></script>
    <script src="<?= asset('/assets/Help.js') ?>"></script>
    <script src="<?= asset('/assets/Browser.js') ?>"></script>
    <script src="<?= asset('/assets/MainView.js') ?>"></script>
    <script src="<?= asset('/assets/main.js') ?>"></script>
    <script src="<?= asset('/assets/BoxDrag.js') ?>"></script>
    <script src="<?= asset('/assets/ZoomPan.js') ?>"></script>

</body>
</html>
