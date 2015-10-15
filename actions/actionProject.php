<?php
class actionProject extends actionBase
{
    public function execute()
    {
        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $data = $this->setProjectData($data);
        }

        if ($method == 'GET') {
            $data = $this->getProjectData();
        }

        $this->renderJson($data);
    }

    protected function getProjectData()
    {
        $json = get('project');

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

    protected function setProjectData($data)
    {
        $data['id'] = 1;  // TODO allow multiple projects

        set('project', json_encode($data));

        return $data;
    }
}
