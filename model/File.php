<?php
class File extends Model
{
    protected $values = [
        'top'      => 0,
        'left'     => 0,
        'width'    => 150,
        'height'   => 200,
        'isActive' => false,
        'filename'     => '',
    ];

    static protected $name = 'file';

    public function setFilename($value)
    {
        $this->values['filename'] = $value;
    }

    public function getFilename()
    {
        return $this->values['filename'];
    }

    public function getFileMeta()
    {
        $manager = Manager::getInstance();
        $filename = $manager->browser->directory . $this->values['filename'];
        if (!file_exists($filename)) {
            return ['', 0];
        }
        $handle = fopen($filename, "r");

        $content = '';
        $numLines = 0;

        while (!feof($handle)){
          $content .= fgets($handle);
          $numLines++;
        }
        fclose($handle);

        return [htmlspecialchars($content), $numLines];
    }
}
