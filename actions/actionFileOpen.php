<?php
class actionFileOpen extends actionBase
{
    public function execute()
    {
        $id = $this->getRequestParamGet('id');

        $file = new File($id);
        $file = Manager::getInstance()->browser->directory . $file->getFilename();
        exec("gnome-terminal -e \"gvim '$file'\"");
    }
}
