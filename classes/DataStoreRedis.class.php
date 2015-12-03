<?php
class DataStoreRedis
{
    protected $redis = null;

    public function __construct()
    {
        $this->redis = new Redis();
        $this->redis->connect('127.0.0.1', 6379);
        $this->redis->select(2);
    }

    public function __call($name, $args)
    {
        return call_user_func_array([$this->redis, $name], $args);
    }
}
