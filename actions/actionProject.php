<?php
class actionProject extends actionBase
{
    public function execute()
    {
        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $project = new Project($data['id']);
            $project->fromArray($data);
            $project->save();
        }

        if ($method == 'GET') {
            $project = Project::fetchFirstOrNew();
        }

        $this->renderJson($project->toArray());
    }
}
