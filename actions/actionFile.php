<?php
class actionFile extends actionBase
{
    public function execute()
    {
        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            //$data = $this->getRequestPayload();
            //$data = $this->setFileData($data);
        }

        if ($method == 'GET') {
            $data = $this->getFileData();
        }

        $this->renderJson($data);
    }

    protected function getFileData()
    {
        $raw = get('watches');  // TODO change to another format
        $files = $raw ? unserialize($raw) : [];

        $data = [];
        foreach ($files as $i => $file) {
            $values = $file->toArray();
            $values['id'] = $i;
            $data[] = $values;
        }

        return $data;
    }

    protected function setFileData($data)
    {
        //set('watches', serialize($this->watches));

        //return $data;
    }
}
