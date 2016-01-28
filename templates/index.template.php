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
                <li><strong>K, J, H, L</strong> - Navigate up, down, left and right</li>
                <li><strong>e</strong> - Enter edit box mode</li>
            </ul>
            <strong>Normal mode: Source code</strong>
            <ul>
                <li><strong>k, j, h, l</strong> - Scrolls box up, down, left and right</li>
                <li><strong>Enter</strong> - Opens selected file</li>
            </ul>
            <strong>Normal mode: Browser</strong>
            <ul>
                <li><strong>k, j</strong> - Navigates up, down</li>
                <li><strong>Enter</strong> - Opens selected file or toggles directory</li>
                <li><strong>a</strong> - Add new file or directory</li>
                <li><strong>m</strong> - Moves current item</li>
                <li><strong>c</strong> - Copies current item</li>
                <li><strong>d</strong> - Deletes current item</li>
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


<script type="text/html" id="template-browser">
    <ul></ul>
</script>


<script type="text/html" id="template-browser-item">
    <% if (isDir) { %>
        <span><%- name %></span>
        <ul></ul>
    <% } else { %>
        <%- name %>
    <% } %>
</script>
