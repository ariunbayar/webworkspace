<?php
// Seed redis (db 2) so the PHP workspace displays this project's own source
// files. Walks DEMO_DIR (default /app), keeps text/source files, lays them out
// as a grid of boxes. Keys match the PHP Model scheme (<name>_ids/<name>_<id>).

$root = rtrim(getenv('DEMO_DIR') ?: '/app', '/');

$redis = new Redis();
$redis->connect('127.0.0.1', 6379);
$redis->select(2);

$sourceExt = ['py', 'php', 'js', 'css', 'html', 'sh', 'yml', 'yaml', 'txt', 'md'];
$extraNames = ['.env.example', '.dockerignore', '.gitignore'];
$skipDirs = ['.git', '__pycache__', 'libs', 'node_modules'];

$isSource = function ($name) use ($sourceExt, $extraNames) {
    if (in_array($name, $extraNames) || strpos($name, 'Dockerfile') === 0) {
        return true;
    }
    if (preg_match('/\.min\.js$/', $name)) {
        return false;
    }
    if (preg_match('/^(createjs-|easeljs-|tweenjs-|underscore|backbone|jquery)/', $name)) {
        return false;
    }
    return in_array(strtolower(pathinfo($name, PATHINFO_EXTENSION)), $sourceExt);
};

$it = new RecursiveIteratorIterator(new RecursiveCallbackFilterIterator(
    new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS),
    function ($current) use ($skipDirs) {
        return $current->isDir() ? !in_array($current->getFilename(), $skipDirs) : true;
    }
));

$files = [];
foreach ($it as $f) {
    if ($f->isFile() && $isSource($f->getFilename())) {
        $files[] = ltrim(substr($f->getPathname(), strlen($root)), '/');
    }
}
sort($files);

$cols = 6;
$bw = 240; $bh = 300; $gx = 40; $gy = 60; $x0 = 60; $y0 = 80;

$redis->set('project_ids', json_encode([1]));
$redis->set('project_1', json_encode([
    'top' => 10, 'left' => 10, 'width' => 200, 'height' => 150,
    'isActive' => false, 'directory' => $root . '/', 'id' => 1,
]));

$ids = [];
foreach ($files as $i => $rel) {
    $fid = $i + 1;
    $ids[] = $fid;
    $col = $i % $cols;
    $row = intdiv($i, $cols);
    $redis->set('file_' . $fid, json_encode([
        'top' => $y0 + $row * ($bh + $gy),
        'left' => $x0 + $col * ($bw + $gx),
        'width' => $bw, 'height' => $bh, 'isActive' => false,
        'filename' => $rel, 'id' => $fid,
    ]));
}
$redis->set('file_ids', json_encode($ids));
$redis->set('last_id', count($files));

echo 'seeded ' . count($files) . " project files from $root\n";
