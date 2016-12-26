<?php
class BrowserItem extends Model
{
    protected $values = [
        'name'       => "",
        'isDir'      => false,
        'collapsed'  => false,
        'childItems' => "",
    ];

    static protected $name = 'browser_item';

    public function setName($value)
    {
        $this->values['name'] = $value;
    }

    public function getName()
    {
        return $this->values['name'];
    }

    public function setIsDir($value)
    {
        $this->values['isDir'] = $value;
    }

    public function getIsDir()
    {
        return $this->values['isDir'];
    }

    public function setCollapsed($value)
    {
        $this->values['collapsed'] = $value;
    }

    public function getCollapsed()
    {
        return $this->values['collapsed'];
    }

    public function setChildItems($value)
    {
        $this->values['childItems'] = implode(',', $value);
    }

    public function getChildItems()
    {
        return explode(',', $this->values['childItems']);
    }
}
