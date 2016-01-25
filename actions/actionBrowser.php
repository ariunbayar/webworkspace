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
            $browser->save();
            $data = $browser->toArray();
        }

        if ($method == 'GET') {
            $browsers = Browser::fetchAll();
            foreach ($browsers as $i => $browser) {
                $data[$i] = $browser->toArray();
                $data[$i]['tree'] = $this->getTree();
            }
        }

        if ($method == 'DELETE') {
            $browser = new Browser($id);
            $browser->delete();
        }

        $this->renderJson($data);
    }

    public function getTree()
    {
        $traverseTree = function ($dir) use (&$traverseTree) {
            $tree = [];

            $items = glob($dir . '/*');
            sort($items, SORT_STRING);
            $files = [];

            foreach ($items as $item) {
                $name = basename($item);
                if (is_file($item)) {
                    $files[$name] = 1;
                } else {
                    $tree[$name] = $traverseTree($dir . '/' . $name);
                }
            }

            return array_merge($tree, $files);
        };

        return $traverseTree(Project::getDirectoryOrCWD());
    }
}
