<?php
class DataStoreFile
{
    protected $file;

    public function __construct()
    {
        $this->file = __DIR__ . '/dummy.db';
        if (!file_exists($this->file)) {
            touch($this->file);
        }
    }

    protected function _read()
    {
        return unserialize(file_get_contents($this->file));
    }

    protected function _save($data)
    {
        file_put_contents($this->file, serialize($data));
    }

    public function get($key)
    {
        $data = $this->_read();
        return $data[$key];
    }

    public function set($key, $value)
    {
        $data = $this->_read();
        $data[$key] = $value;
        $this->_save($data);
    }

    public function del($key)
    {
        $data = $this->_read();
        unset($data[$key]);
        $this->_save($data);
    }

    public function incr($key)
    {
        $data = $this->_read();
        $data[$key] = 1 + (int)$data[$key];
        $this->_save($data);
        return $data[$key];
    }

    public function __call($name, $args)
    {
        throw new Exception($name . ' method needs to be implemented for file storage');
    }
}
