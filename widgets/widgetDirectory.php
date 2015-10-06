<?php

class WidgetDirectory extends WidgetBase
{
    protected $directory;

    function __construct($directory = '')
    {
        $this->directory = $directory;
    }

    public function render()
    {
        ?>
        <form action="" method="POST">
            <input type="text" name="directory" value="<?php echo get('directory')?>"/>

            <input type="submit" value="Save and Reload"/>
        </form>
        <?php
    }

}
