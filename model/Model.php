<?php
class Model
{
    protected $values = [];
    static protected $name = '';

    public function __construct($id = null)
    {
        if ($id) {
            $json = get(static::$name . '_' . $id);
            if ($json) {
                $this->values = json_decode($json, true);
            }
        }
    }

    protected function _saveNewId()
    {
        $json = get(static::$name . '_ids') ?: '[]';

        $ids = json_decode($json, true);
        $ids[] = $this->getId();

        set(static::$name . '_ids', json_encode($ids));
    }

    protected function _saveModel()
    {
        if ($this->isNew()) {
            $this->setId(incr('last_id'));
            $this->_saveNewId();
        }

        $json = json_encode($this->values);
        set(static::$name . '_' . $this->getId(), $json);
    }

    public function getId()
    {
        return $this->values['id'];
    }

    protected function setId($val)
    {
        $this->values['id'] = $val;
    }

    public function isNew()
    {
        return !isset($this->values['id']);
    }

    public function save()
    {
        $this->_saveModel();
    }

    public function delete()
    {
        if ($this->isNew()) {
             return;
        }

        // remove object
        del(static::$name . '_' . $this->getId(), null);

        // remove id from list
        $json = get(static::$name . '_ids') ?: '[]';
        $ids = json_decode($json, true);
        $index = array_search($this->getId(), $ids);
        if ($index !== false) {
            unset($ids[$index]);
            $ids = array_values($ids);
            set(static::$name . '_ids', json_encode($ids));
        }
    }

    public function toArray()
    {
        return $this->values;
    }

    static public function fetchAll()
    {
        $objects = [];

        $json_ids = get(static::$name . '_ids');
        $ids = $json_ids ? json_decode($json_ids) : [];

        foreach ($ids as $id) {
            $objects[] = new static($id);
        }

        return $objects;
    }
}
