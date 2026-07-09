<?php
class Browser extends Model
{
    protected $values = [
        'top'      => 0,
        'left'     => 0,
        'width'    => 150,
        'height'   => 200,
        'isActive' => false,
        'activeItem' => null,
        'rootItems' => "",
    ];

    static protected $name = 'browser';

    public function getActiveItem()
    {
        $browserItem = new BrowserItem($this->values['activeItem']);
        if ($browserItem->isNew()) {
            return null;
        } else {
            return $browserItem;
        }
    }

    public function setActiveItem($browserItem)
    {
        $this->values['activeItem'] = $browserItem->getId();
    }

    public function setRootItems($value)
    {
        $this->values['rootItems'] = implode(',', $value);
    }

    public function getRootItems()
    {
        return explode(',', $this->values['rootItems']);
    }

    public function refreshTree()
    {
        // TODO preserve existing collapse or active state
        // load from disk and store in redis DB
        $traverseFromDisk = function ($dir, $parentBrowserItem = null) use (&$traverseFromDisk) {
            $dirs = [];
            $filenames = [];
            $ids = [];

            $items = glob($dir . '/*');
            sort($items, SORT_STRING);

            foreach ($items as $item) {
                $name = basename($item);
                if (is_file($item)) {
                    $filenames[] = $name;
                } else {
                    $browserItem = new BrowserItem();
                    $browserItem->setName($name);
                    $browserItem->setIsDir(true);
                    $browserItem->setCollapsed(true);
                    $childIds = $traverseFromDisk($dir . '/' . $name, $browserItem);
                    $browserItem->setChildItems($childIds);
                    $browserItem->save();
                    $ids[] = $browserItem->getId();
                }
            }

            foreach ($filenames as $filename) {
                $browserItem = new BrowserItem();
                $browserItem->setName($filename);
                $browserItem->save();
                $ids[] = $browserItem->getId();
            }

            return $ids;
        };

        $rootItems = $traverseFromDisk(Project::getDirectoryOrCWD());
        $this->setRootItems($rootItems);

        // attempt to set default activeItem
        $activeItem = $this->getActiveItem();
        $hasTreeItem = count($rootItems) > 0;
        if (!$activeItem && $hasTreeItem) {
            $this->setActiveItem(new BrowserItem($rootItems[0]));
        }
    }

    public function treeExpandCollapse($itemLocation, $isCollapsed)
    {
        // minor structure for sake of the loop
        $treeItem = ['children' => &$this->values['tree']];
        foreach ($itemLocation as $location) {
            $treeItem = &$treeItem['children'][$location];
        }
        if (array_key_exists('collapsed', $treeItem)) {
            $treeItem['collapsed'] = $isCollapsed;
        }
    }

    /**
     * Flat, pre-order list of the tree the frontend renders (BrowserView
     * indents each row by its `level`). Assembled from the stored BrowserItems.
     */
    private function buildTree($ids, $level)
    {
        $rows = [];
        foreach ($ids as $id) {
            if ($id === '') {
                continue;
            }
            $item = new BrowserItem($id);
            $rows[] = [
                'id'        => (int) $id,
                'name'      => $item->getName(),
                'isDir'     => $item->getIsDir(),
                'collapsed' => $item->getCollapsed(),
                'level'     => $level,
            ];
            if ($item->getIsDir()) {
                $rows = array_merge($rows, $this->buildTree($item->getChildItems(), $level + 1));
            }
        }
        return $rows;
    }

    public function toArray()
    {
        $values = $this->values;
        $values['tree'] = $this->buildTree($this->getRootItems(), 0);
        return $values;
    }
}
