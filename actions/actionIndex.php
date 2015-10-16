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
            $manager->watches[] = new FileWatch($pick);
            $manager->save();
            $this->redirect('/');
        }

        $openIndex = $this->getRequestParamGet('open');
        if ($openIndex !== null) {
            $watch = $manager->watches[$openIndex];
            $file = $manager->browser->directory . $watch->file;
            exec("gnome-terminal -e \"gvim '$file'\"");
            exit(0);
        }

        $this->render([
            'm' => $manager,
        ]);
    }
}
