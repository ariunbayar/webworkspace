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

    function __construct($file)
    {
        $this->file = $file;
    }

    function serialize()
    {
        return
            $this->x . '|' .
            $this->y . '|' .
            $this->width . '|' .
            $this->height . '|' .
            $this->file;
    }

    function unserialize($data)
    {
        list($this->x, $this->y, $this->width, $this->height, $this->file) = explode('|', $data, 5);
    }

    function load($dump)
    {
        list($this->remove, $this->x, $this->y, $this->width, $this->height) = explode('|', $dump, 5);
    }

    function dump()
    {
        return
            '0|' .
            $this->x . '|' .
            $this->y . '|' .
            $this->width . '|' .
            $this->height;
    }

    function toStyleForWatch()
    {
         return 'top:' . $this->x . 'px; left:' . $this->y . 'px';
    }

    function toStyleForPre()
    {
         return 'width:' . $this->width . 'px; height:' . $this->height . 'px';
    }

    function getSource()
    {
        global $m;
        $handle = fopen($m->browser->directory . $this->file, "r");

        $content = '';
        $this->numLines = 0;

        while (!feof($handle)){
          $content .= fgets($handle);
          $this->numLines++;
        }
        fclose($handle);

        return $content;
    }

}
