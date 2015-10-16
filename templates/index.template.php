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


<div style="top: 20px; left: 1350px;" class="box preview"><pre></pre></div>


<script type="text/html" id="template-project">
    <span><%= directory %></span>
    <ul>
        <li><strong>i</strong> - edit directory and reload workspace from new position</li>
        <li><strong>o</strong> - opens new file browser</li>
    </ul>
</script>


<script type="text/html" id="template-help">
    <ul>
        <li>Press <strong>?</strong> for help</li>
        <li><strong>Esc</strong> - Goes back to normal mode from whatever mode</li>
        <li>
            <strong>Normal mode</strong>
            <ul>
                <li><strong>k, j, h, l</strong> - Scrolls box up, down, left and right</li>
                <li><strong>K, J, H, L</strong> - Navigate up, down, left and right</li>
                <li><strong>Enter</strong> - Opens selected file</li>
                <li><strong>e</strong> - Enter edit box mode</li>
            </ul>
        </li>
        <li>
            <strong>Edit box mode</strong>
            <ul>
                <li><strong>k, j, h, l</strong> - Move box up, down, left and right</li>
                <li><strong>K, J, H, L</strong> - Resize box up, down, left and right</li>
                <li><strong>d</strong> - Remove current box</li>
            </ul>
        </li>
    </ul>
</script>


<script type="text/html" id="template-file">
    <div class="filename"><%= filename %></div>
    <pre data-num-lines="<%= numLines %>"><%= content %></pre>
</script>
