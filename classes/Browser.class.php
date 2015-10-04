<?php
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
