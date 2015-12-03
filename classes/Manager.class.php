<?php
class Manager
{
    public $browser;
    public $watches;

    static protected $_instance = null;

    /**
     * Loads configurations and setup values
     */
    public function __construct()
    {

        // Main directory
        $project = DataStore::getInstance()->get('project');
        if ($project) {
            $directory = json_decode($project, true)['directory'];
        } else {
            $directory = '';
        }
        if (!$directory) {
            $directory = getcwd();
        }
        $this->browser = new Browser($directory);

        // Watching files
        $watches = DataStore::getInstance()->get('watches');
        $this->watches = $watches ? unserialize($watches) : [];
    }

    public function save()
    {
        for ($i = count($this->watches) - 1; $i >= 0; $i--) {
            if ($this->watches[$i]->remove == 1) {
                array_splice($this->watches, $i, 1);
            }
        }
        DataStore::getInstance()->set('watches', serialize($this->watches));
    }

    static public function getInstance()
    {
        if (self::$_instance === null) {
            self::$_instance = new Manager();
        }
        return self::$_instance;
    }
}
