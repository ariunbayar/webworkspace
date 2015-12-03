<?php
class Manager
{
    public $browser;

    static protected $_instance = null;

    /**
     * Loads configurations and setup values
     */
    public function __construct()
    {
        // Main directory
        $project = Project::fetchFirstOrNew();
        if (!$project->getDirectory()) {
            $project->setDirectory(getcwd());
            $project->save();
        }
        $this->browser = new Browser($project->getDirectory());
    }

    public function save()
    {
    }

    static public function getInstance()
    {
        if (self::$_instance === null) {
            self::$_instance = new Manager();
        }
        return self::$_instance;
    }
}
