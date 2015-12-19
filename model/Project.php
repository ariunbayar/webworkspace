<?php
class Project extends Model
{
    protected $values = [
        'top'      => 0,
        'left'     => 0,
        'width'    => 150,
        'height'   => 200,
        'isActive' => false,
        'directory' => '',
    ];

    static protected $name = 'project';

    public function getDirectory()
    {
        return $this->values['directory'];
    }

    public function setDirectory($value)
    {
        $this->values['directory'] = $value;
    }

    static public function getDirectoryOrCWD()
    {
        $project = static::fetchFirstOrNew();
        if (!$project->getDirectory()) {
            $project->setDirectory(getcwd());
            $project->save();
        }

        return $project->getDirectory();
    }
}
