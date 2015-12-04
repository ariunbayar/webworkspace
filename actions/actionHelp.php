<?php
class actionHelp extends actionBase
{
    public function execute($id = null)
    {
        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $help = new Help($id);
            $help->fromArray($data);
            $help->save();
        }

        if ($method == 'GET') {
            $help = Help::fetchFirstOrNew();
        }

        $this->renderJson($help->toArray());
    }
}
