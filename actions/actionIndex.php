<?php
class actionIndex extends actionBase
{
    public function execute()
    {
        $pick = $this->getRequestParamGet('pick');
        if ($pick) {
            // TODO don't add if already exists
            $file = new File();
            $file->setFilename($pick);
            $file->save();
            $this->redirect('/');
        }

        $this->render([]);
    }
}
