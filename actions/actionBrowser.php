<?php
class actionBrowser extends actionBase
{
    public function execute($id = null)
    {
        $dir = Project::getDirectoryOrCWD();
        $data = [];

        $method = $this->getRequestMethod();

        if ($method == 'PUT' || $method == 'POST') {
            $data = $this->getRequestPayload();
            $browser = new Browser($id);
            $browser->fromArray($data);
            $browser->save();
            $data = $browser->toArray();
        }

        if ($method == 'GET') {
            $browsers = Browser::fetchAll();
            foreach ($browsers as $i => $browser) {
                $data[$i] = $browser->toArray();
            }
        }

        if ($method == 'DELETE') {
            $browser = new Browser($id);
            $browser->delete();
        }

        $this->renderJson($data);
    }

    /*
    <div class="browser box">
        <?php echo $b->currentDir ?>
        <ul>
            <?php if (!$b->isMainDir()) { ?>
            <li><a href="?path=<?php echo $b->getUpperDir() ?>">..</a></li>
            <?php } ?>

            <?php foreach ($b->dirs as $dir) { ?>
            <li><a href="?path=<?php echo $b->getAppended($dir) ?>">/<?php echo $dir ?></a></li>
            <?php } ?>

            <?php foreach ($b->files as $file) { ?>
            <li>+ <a href="?path=<?php echo $b->removeDirPrefix($b->currentDir)?>&pick=<?php echo $b->getAppended($file) ?>"><?php echo $file ?></a></li>
            <?php } ?>
        </ul>
    </div>
     */
}
