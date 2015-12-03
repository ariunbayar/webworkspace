<?php
class actionIndex extends actionBase
{
    public function execute()
    {
        $manager = Manager::getInstance();

        // TODO change them to corresponding actions

        $pick = $this->getRequestParamGet('pick');
        if ($pick) {
            // TODO don't add if already exists
            $file = new File();
            $file->setFilename($pick);
            $file->save();
            $this->redirect('/');
        }

        // TODO fix
        /*
        $openIndex = $this->getRequestParamGet('open');
        if ($openIndex !== null) {
            $watch = $manager->watches[$openIndex];
            $file = $manager->browser->directory . $watch->file;
            exec("gnome-terminal -e \"gvim '$file'\"");
            exit(0);
        }
         */

        $this->render([
            'm' => $manager,
        ]);
    }
}
