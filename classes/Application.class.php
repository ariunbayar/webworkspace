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
        $urlParts = explode('/', $this->path);

        $action = 'action' . ucfirst(array_shift($urlParts));
        $actionExists = preg_match('/^[a-z]+$/i', $action) && class_exists($action);
        if ($actionExists) {
            $this->serveAction($action, $urlParts);
        }

        return $actionExists;
    }

    protected function serveAction($actionName, $urlParts)
    {
        $action = new $actionName();
        call_user_func_array([$action, 'execute'], $urlParts);
    }
}
