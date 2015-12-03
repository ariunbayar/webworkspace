<?php
class actionFile extends actionBase
{
    public function execute()
    {
        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $data = $this->setFileData($data);
        }

        if ($method == 'GET') {
            $data = $this->getFileData();
        }

        $this->renderJson($data);
    }

    protected function getFileData()
    {
        $raw = DataStore::getInstance()->get('watches');  // TODO change to another format
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
        $raw = DataStore::getInstance()->get('watches');  // TODO change to another format
        $files = $raw ? unserialize($raw) : [];
        $file = $files[$data['id']];
        $file->fromArray($data);
        DataStore::getInstance()->set('watches', serialize($files));

        return $data;
    }
}
