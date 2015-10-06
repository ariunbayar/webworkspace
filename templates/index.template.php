<?php foreach ($widgets as $widget) {
    $widget->render();
} ?>


<form id="formPosition" action="" method="POST">
    <label class="unchanged">Positions haven't changed</label>
    <label class="changed" style="display: none; color: red;">Positions have changed</label>
    <?php foreach ($m->watches as $i => $w) { ?>
    <input type="hidden" name="watch[<?php echo $i ?>]" value="<?php echo $w->dump() ?>"/>
    <?php } ?>
    <input type="submit" value="Save and Reload"/>
</form>


<!-- File browser -->
<?php $b = $m->browser ?>
<div class="browser box">
    <?php echo $b->currentDir ?>
    <ul>
        <?php if (!$b->isMainDir()) { ?>
        <li><a href="?path=<?php echo $b->getUpperDir() ?>">..</a></li>
        <?php } ?>

        <?php foreach ($b->dirs as $dir) { ?>
        <li><a href="?path=<?php echo $b->getAppended($dir) ?>">/<?php echo $dir ?></a></li>
        <?php } ?>

        <?php foreach ($b->files as $file) { ?>
        <li>+ <a href="?path=<?php echo $b->removeDirPrefix($b->currentDir)?>&pick=<?php echo $b->getAppended($file) ?>"><?php echo $file ?></a></li>
        <?php } ?>
    </ul>
</div>


<!-- Watching files -->
<?php foreach ($m->watches as $i => $watch) { ?>
<div class="watch box" data-idx="<?php echo $i ?>" style="<?php echo $watch->toStyleForWatch() ?>">
    <div class="filename"><?php echo $watch->file ?></div>
    <a href="#" title="close" class="close">X</a>
    <a href="#" title="resize to default 150x200" class="resize">R</a>
    <?php $content = $watch->getSource() ?>
    <pre style="<?php echo $watch->toStyleForPre() ?>" data-num-lines="<?php echo $watch->numLines ?>"><?php echo htmlspecialchars($content) ?></pre>
</div>
<?php } ?>

<div style="top: 20px; left: 1350px;" class="box preview"><pre></pre></div>

