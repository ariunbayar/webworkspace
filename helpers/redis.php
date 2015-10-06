<?php
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
