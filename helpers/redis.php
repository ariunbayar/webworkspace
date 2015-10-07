<?php
// check if redis is installed
if (class_exists('Redis')) {

    $redis = new Redis();
    $redis->connect('127.0.0.1', 6379);
    $redis->select(2);

    function get($key) {
        global $redis;
        return $redis->get($key);
    }

    function set($key, $value) {
        global $redis;
        return $redis->set($key, $value);
    }

} else {

    // fallback method of saving to disk
    $file = __DIR__ . '/dummy.db';
    if (!file_exists($file)) {
        touch($file);
    }

    function get($key) {
        global $file;

        $data = unserialize(file_get_contents($file));
        return $data[$key];
    }

    function set($key, $value) {
        global $file;
        $data = unserialize(file_get_contents($file));
        $data[$key] = $value;
        file_put_contents($file, serialize($data));
    }

}
