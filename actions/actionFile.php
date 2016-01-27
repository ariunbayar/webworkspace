<?php
class actionFile extends actionBase
{
    public function execute($id = null)
    {
        $data = [];

        $method = $this->getRequestMethod();

        if (in_array($method, ['PUT', 'POST', 'PATCH'])) {
            $data = $this->getRequestPayload();
            $file = new File($id);
            $file->fromArray($data);
            $file->save();
            $data = $file->toArray();
            if ($method == 'POST') {
                // Meta data is required upon creation
                list($content, $numLines) = $file->getFileMeta();
                $data['content'] = $content;
                $data['numLines'] = $numLines;
            }
        }

        if ($method == 'GET') {
            $files = File::fetchAll();
            foreach ($files as $i => $file) {
                $data[$i] = $file->toArray();
                list($content, $numLines) = $file->getFileMeta();
                $data[$i]['content'] = $content;
                $data[$i]['numLines'] = $numLines;
            }
        }

        if ($method == 'DELETE') {
            $file = new File($id);
            $file->delete();
        }

        $this->renderJson($data);
    }
}
