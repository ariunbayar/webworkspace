<?php
class actionBrowser extends actionBase
{
    public function execute($id = null)
    {
        $data = [];

        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $browser = new Browser($id);
            $browser->fromArray($data);
            $browser->refreshTree();
            $browser->save();
            $data = $browser->toArray();
        }

        if ($method == 'GET') {
            $browsers = Browser::fetchAll();
            foreach ($browsers as $i => $browser) {
                $data[$i] = $browser->toArray();
            }
        }

        if ($method == 'DELETE') {
            $browser = new Browser($id);
            $browser->delete();
        }

        $this->renderJson($data);
    }
}
