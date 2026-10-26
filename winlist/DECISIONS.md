# Winlist decisions

What was decided about winlist, and why. Read this before proposing or
building anything. A later session should reason from it, not argue with it.
A decision changes only when the user changes it; when they do, edit its
entry and date it.

Item numbers (#N) are the feature board's
(https://claude.ai/artifact/MX9FKLDDdDEhGLmwu353EZ). PR numbers say "PR".

Each entry:

```
### <item> <title>
- Q: the question
- A: the answer
- Why: the reason
- Status: done (PR) | queued | needs the user | dropped
```

## How we work

### Building
- Q: When does a proposed feature get built?
- A: Only after the user says "do #N". Brainstorm first, then wait.
- Why: features were built before they were discussed, and some weren't wanted.
- Status: standing rule

### Servers
- Q: Who starts or restarts the winlist servers (8766, 8767)?
- A: The user, always, even after a merge. Say when a restart is needed.
- Why: they run the board the user is working in.
- Status: standing rule

### Testing a PR
- Q: How does the user test a PR?
- A: Merge main into the PR branch in its worktree, run the checks, then
  `git checkout --detach <branch>` in the main checkout. Test PRs one at a
  time; the all-features branch is stale.
- Why: the page is served from disk, so the main checkout is what the user sees.
- Status: standing rule

### Checking app.js
- Q: How is app.js checked?
- A: Copy it to a .mjs file and `node --check` the copy.
- Why: a plain `node --check` missed a duplicate top-level name that broke
  the page (PR #85).
- Status: standing rule

### Splitting app.js (#23)
- Q: Should app.js stay one big file?
- A: No: split it into modules (issue #87), after the open PRs are merged or closed.
- Why: one big file hid the PR #85 name clash.
- Status: queued

### — Page errors show a mark
- Q: When the page throws (e.g. an unknown card kind stopped every render, so INSERT could not be entered), how do you find out?
- A: Every uncaught error or rejection, and a script that fails to load, shows a red "⚠ N errors" mark in the top-right corner, in bare mode too. Clicking it lists them, counted. Missing images (favicons) are not errors.
- Why: The user asked on 2026-10-26 after the page silently broke INSERT; an unknown card kind is also drawn as its title rather than thrown on (PR #93).
- Status: done (PR)

## Layout and moving

### Fit and the 0 key
- Q: Keep the Fit button and the 0 key?
- A: Removed.
- Why: the user didn't want them. #26 would bring something like them
  back; ask before doing so.
- Status: done

### Moving a tile with the keyboard
- Q: What happens when a tile moved with Super+Enter reaches the view's edge?
- A: The view follows the tile.
- Why: the tile went out of sight.
- Status: done (PR #85)

### Off-view markers
- Q: Where are the triangles for tiles out of view drawn?
- A: On the frame's edge, kept there when the frame changes size.
- Why: they were drawn in the middle of the board (issue #86).
- Status: done (PR #88)

### #22 Card size
- Q: What happens to cards when you zoom?
- A: They keep their size; long text is trimmed.
- Why: cards grew and shrank in ways the user didn't want.
- Status: done (PR #89)

## Groups and projects

### Groups as folders
- Q: What is a group's folder for?
- A: A group acts as a virtual folder. New terminals and Claude started in
  the group open in its folder. Existing tiles are not moved or changed.
- Why: this brings the `ak` "Claude in a project" menu into winlist.
- Status: done

### Claude in a group
- Q: How do you start Claude in a project?
- A: Press `c` or the group's Claude button. The tile closes when Claude exits.
- Why: it replaces `ak` items 1, 6 and 7.
- Status: done

### #14 Project tools
- Q: How do a project's scripts show up?
- A: Picking a script makes a button card; pressing the button runs the script.
- Why: the user wanted a button, not a script that runs the moment you pick it.
- Status: done (PR #76)

### #30 Caption prefix
- Q: How do you tell which project a tile belongs to?
- A: winlist puts the group name, or else the folder's last part, in front
  of each caption automatically.
- Why: consistent, with nothing to remember. No instruction to Claude is
  involved.
- Status: queued

### #7 Renaming tiles
- Q: Rename tiles by hand (F2, double-click the title)?
- A: No.
- Why: names are only for the user, and the prefix (#30) covers the need.
- Status: dropped (PR #82 closed, branch rename-tile kept)

## Cards

### #6 Cards sent from outside
- Q: Where does a card sent by a shell, script or Claude land?
- A: Next to the sending terminal (`term`), else in the group whose folder
  holds `cwd`, else in the Inbox. A new card pulses, and so does its edge
  marker, until you have looked at it. The view doesn't move.
- Why: the sender knows where it came from; cards shouldn't pile up somewhere random.
- Status: done (PR #81)

### Sending a card
- Q: How does Claude send a card?
- A: `curl -s localhost:8766/api/links -d "{\"url\":\"...\",\"title\":\"...\",\"term\":\"$WINLIST_TERM\",\"cwd\":\"$PWD\"}"`.
  Cards the page adds itself send `from: 'page'`.
- Why: so the card lands by its terminal (#6), and the page's own cards don't go to the Inbox.
- Status: standing rule

## Palette and help

### Command palette
- Q: Which top-bar buttons does the palette replace?
- A: 1:1, Loupe, New terminal, Claude and Architecture are gone. The filter
  box shows only on `/`.
- Why: the palette makes them redundant.
- Status: done (PR #78)

### Help search
- Q: Can you search the `?` dialog?
- A: Yes, with a search box that highlights matches.
- Status: done

## Claude and terminals

### Claude status
- Q: How do you see what Claude is doing?
- A: A chip and ring on its tile (working, waiting, done), fed by Claude Code
  hooks that run ping_hook.sh.
- Status: done (PR #80)

### Restoring terminals
- Q: What happens to terminals after a reboot or a terminal server restart?
- A: Claude tiles resume their session (`claude --resume <id>`). Other
  terminals come back as placeholders showing the last title, last 3
  commands and old output, with Restore and Close.
- Why: the user wanted to pick up where they left off. This covers page
  terminals only.
- Status: done (PR #79)

## Open

### #10 Tidy a group
- Q: Undo, reading order, drop the ▦ button, group shrink?
- A: Waiting for the user's answers.
- Status: needs the user (PR #84 open)

### #9 Sticky notes
- Q: Merge PR #83?
- A: Merged.
- Status: done (PR #83)
