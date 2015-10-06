<?php
class Application
{
    protected $path;

    function __construct()
    {
        $path = substr(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH), 1);
        $path = ($path == '' ? 'index' : $path);

        $this->path = $path;
    }

    public function dispatch()
    {
        $action = 'action' . ucfirst($this->path);
        $actionExists = preg_match('/^[a-z]+$/i', $action) && class_exists($action);
        if ($actionExists) {
            $this->serveAction($action);
        }

        return $actionExists;
    }

    protected function serveAction($action)
    {
        $action = new $action();
        $action->dispatch();
    }
}
