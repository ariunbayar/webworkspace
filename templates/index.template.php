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


<script type="text/html" id="template-browser-helper">
    <ul <% print(collapsed ? 'style="display:none"' : '') %>>
    <% for (var name in tree) { %>
        <% if (tree[name] === 1) { %>
            <li><%- name %></li>
        <% } else { %>
            <li class="dir">
                <span><%- name %> (<%= _.size(tree[name]) %>)</span>
                <% print(_.template($('#template-browser-helper').html())({tree: tree[name], collapsed: true})), %>
            </li>
        <% } %>
    <% } %>
    </ul>
</script>
<script type="text/html" id="template-browser">
    <% print(_.template($('#template-browser-helper').html())({tree: tree, collapsed: false})), %>
</script>
