<?php
class FileWatch implements Serializable
{

    public $x = 10;
    public $y = 10;
    public $width = 150;
    public $height = 200;
    public $file;
    public $numLines = 0;
    public $remove = 0;
    public $isActive = false;

    function __construct($file)
    {
        $this->file = $file;
    }

    function serialize()
    {
        $values = [
            $this->x,
            $this->y,
            $this->width,
            $this->height,
            $this->file,
            $this->isActive ? 1 : 0,
        ];
        return implode('|', $values);
    }

    function unserialize($data)
    {
        $values = explode('|', $data, 6);
        $this->x        = $values[0];
        $this->y        = $values[1];
        $this->width    = $values[2];
        $this->height   = $values[3];
        $this->file     = $values[4];
        $this->isActive = $values[5] ? true : false;
    }

    function getSource()
    {
        $manager = Manager::getInstance();
        $file = $manager->browser->directory . $this->file;
        if (!file_exists($file)) {
            return '';
        }
        $handle = fopen($file, "r");

        $content = '';
        $this->numLines = 0;

        while (!feof($handle)){
          $content .= fgets($handle);
          $this->numLines++;
        }
        fclose($handle);

        return $content;
    }

    function toArray()
    {
        return [
            // TODO id
            'content'  => htmlspecialchars($this->getSource()),
            'numLines' => $this->numLines,
            'filename' => $this->file,
            'top'      => (int)$this->y,
            'left'     => (int)$this->x,
            'width'    => (int)$this->width,
            'height'   => (int)$this->height,
            'isActive' => $this->isActive,
        ];
    }

    function fromArray($values)
    {
        $this->x        = $values['left'];
        $this->y        = $values['top'];
        $this->width    = $values['width'];
        $this->height   = $values['height'];
        $this->file     = $values['filename'];
        $this->isActive = $values['isActive'];
    }

}
