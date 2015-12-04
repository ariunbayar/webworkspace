<?php
abstract class actionBase
{
    private $_requestParamGet = [];
    private $_requestParamPost = [];

    public function __construct()
    {
        $this->_requestParamGet = $_GET;
        $this->_requestParamPost = $_POST;
    }

    protected function getRequestParamGet($key, $default = null)
    {
        $value = $default;
        if (array_key_exists($key, $this->_requestParamGet)) {
            $value = $this->_requestParamGet[$key];
        }
        return $value;
    }

    protected function getRequestParamPost($key, $default = null)
    {
        $value = $default;
        if (array_key_exists($key, $this->_requestParamPost)) {
            $value = $this->_requestParamPost[$key];
        }
        return $value;
    }

    protected function getRequestMethod()
    {
        return $_SERVER['REQUEST_METHOD'];
    }

    protected function getRequestPayload()
    {
        return json_decode(file_get_contents('php://input'), true);
    }

    protected function redirect($url)
    {
        header('Location: ' . $url);
        exit(0);
    }

    protected function render($template_args)
    {
        foreach ($template_args as $var => $value) {
            $$var = $value;
        }

        ob_start();
        require_once(__DIR__ . '/../templates/' . lcfirst(substr(get_class($this), 6)) . '.template.php');
        $mainContent = ob_get_clean();

        require_once(__DIR__ . '/../templates/layout.php');
    }

    protected function renderJson($values)
    {
        header('Content-Type: application/json');
        echo json_encode($values);
    }

}
