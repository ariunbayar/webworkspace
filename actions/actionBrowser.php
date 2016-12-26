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
            $isCreated = $browser->isNew();
            if ($isCreated) {
                $browser->refreshTree();
            }
            if (array_key_exists('collapsed', $data)) {
                $browser->treeExpandCollapse($data['collapsed'][0], !!$data['collapsed'][1]);
            }
            $browser->save();

            $data = $browser->toArray();
        }

        if ($method == 'GET') {
            $browsers = Browser::fetchAll();
            foreach ($browsers as $i => $browser) {
                if ($this->getRequestParamGet('refresh') == 1) {
                    $browser->refreshTree();
                    $browser->save();
                }
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
