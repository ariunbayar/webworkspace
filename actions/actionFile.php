<?php
class actionFile extends actionBase
{
    public function execute($id = null, $n = null)
    {
        $method = $this->getRequestMethod();

        if (in_array($method, ['PUT', 'POST', 'PATCH'])) {
            $data = $this->getRequestPayload();
            $file = new File($id);
            $file->fromArray($data);
            $file->save();
            $data = $file->toArray();
        }

        if ($method == 'GET') {
            $files = File::fetchAll();
            $data = [];
            foreach ($files as $i => $file) {
                $data[$i] = $file->toArray();
                list($content, $numLines) = $file->getFileMeta();
                $data[$i]['content'] = $content;
                $data[$i]['numLines'] = $numLines;
            }
        }

        $this->renderJson($data);
    }
}
