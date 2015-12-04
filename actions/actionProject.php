<?php
class actionProject extends actionBase
{
    public function execute($id = null)
    {
        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $project = new Project($id);
            $project->fromArray($data);
            $project->save();
        }

        if ($method == 'GET') {
            $project = Project::fetchFirstOrNew();
        }

        if ($method == 'DELETE') {
            $project = new Project($id);
            $project->delete();
        }

        $this->renderJson($project->toArray());
    }
}
