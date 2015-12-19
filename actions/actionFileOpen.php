<?php
class actionFileOpen extends actionBase
{
    public function execute($id)
    {
        $file = new File($id);
        $file = Project::getDirectoryOrCWD() . $file->getFilename();
        exec("gnome-terminal -e \"gvim '$file'\"");
    }
}
