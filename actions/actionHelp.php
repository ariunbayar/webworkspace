<?php
class actionHelp extends actionBase
{
    public function execute()
    {
        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $data = $this->setHelpData($data);
        }

        if ($method == 'GET') {
            $data = $this->getHelpData();
        }

        $this->renderJson($data);
    }

    protected function getHelpData()
    {
        $json = get('help');

        if ($json) {
            $data = json_decode($json, true);
        } else {
            $data = [
                'top'       => 0,
                'left'      => 0,
                'width'     => 150,
                'height'    => 200,
            ];
        }

        return $data;
    }

    protected function setHelpData($data)
    {
        set('help', json_encode($data));

        return $data;
    }
}
