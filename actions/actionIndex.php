<?php
class actionIndex extends actionBase
{
    public function execute()
    {
        $manager = Manager::getInstance();

        // TODO change them to corresponding actions

        $directory = $this->getRequestParamPost('directory');
        if ($directory) {
            $manager->browser->directory = $directory;
            $manager->save();
            $this->redirect($_SERVER['REQUEST_URI']);
        }

        $pick = $this->getRequestParamGet('pick');
        if ($pick) {
            // TODO don't add if already exists
            $manager->watches[] = new FileWatch($pick);
            $manager->save();
            $this->redirect('/');
        }

        $watchOptions = $this->getRequestParamPost('watch');
        if ($watchOptions) {
            // save watch file positions
            foreach ($manager->watches as $i => $watch) {
                $watch->load($watchOptions[$i]);
            }
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

        $widgets = [new WidgetDirectory($manager->browser->directory)];

        return [
            'm'       => $manager,
            'widgets' => $widgets,
        ];
    }
}
