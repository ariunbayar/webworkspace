<?php
class DataStore
{
    static protected $store = null;

    /**
     * Initializes Redis as a data storage
     * Falls back to disk storage otherwise
     */
    static public function getInstance()
    {
        if (static::$store === null) {
            if (class_exists('Redis')) {
                static::$store = new DataStoreRedis();
            } else {
                static::$store = new DataStoreFile();
            }
        }

        return static::$store;
    }
}
