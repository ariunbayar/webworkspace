<?php
class Browser extends Model
{
    protected $values = [
        'top'      => 0,
        'left'     => 0,
        'width'    => 150,
        'height'   => 200,
        'isActive' => false,
        'tree'     => '',
        'activeItem' => [],
    ];

    static protected $name = 'browser';

    public function getActiveItem()
    {
        return $this->values['activeItem'];
    }

    public function setActiveItem($value)
    {
        $this->values['activeItem'] = $value;
    }

    public function refreshTree()
    {
        // load file names from disk
        $traverseTree = function ($dir) use (&$traverseTree) {
            $tree = [];

            $items = glob($dir . '/*');
            sort($items, SORT_STRING);
            $files = [];

            foreach ($items as $item) {
                $name = basename($item);
                if (is_file($item)) {
                    $files[] = [
                        'name'     => $name,
                    ];
                } else {
                    $tree[] = [
                        'name'     => $name,
                        'collapsed'=> true,
                        'children' => $traverseTree($dir . '/' . $name),
                    ];
                }
            }

            return array_merge($tree, $files);
        };
        $tree = $traverseTree(Project::getDirectoryOrCWD());

        // attempt to set default activeItem
        $hasNoActiveItem = count($this->getActiveItem()) == 0;
        $hasTreeItem = count($tree) > 0;
        if ($hasNoActiveItem && $hasTreeItem) {
            $this0>setActiveItem([0]);
        }

        $this->values['tree'] = $tree;
    }
}
