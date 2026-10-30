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
- Status: built 2026-10-26 (Claude's pick: group name, else folder). Terminal
  and Claude tiles only; desktop windows get none.

### #7 Renaming tiles
- Q: Rename tiles by hand (F2, double-click the title)?
- A: No.
- Why: names are only for the user, and the prefix (#30) covers the need.
- Status: dropped (PR #82 closed, branch rename-tile kept)

### #10 Tidy a group
- Q: Pack a group's windows into a neat layout with one key?
- A: No.
- Why: the user would almost never use it.
- Status: dropped (PR #84 closed, branch tidy-group kept)

## Cards

### #6 Cards sent from outside
- Q: Where does a card sent by a shell, script or Claude land?
- A: Next to the sending terminal (`term`), else in the group whose folder
  holds `cwd`, else in the Inbox. A new card pulses, and so does its edge
  marker, until you have looked at it. The view doesn't move.
- Why: the sender knows where it came from; cards shouldn't pile up somewhere random.
- Status: done (PR #81)

### #31 See a PR's diff from its card
- Q: How does the user see what a PR changes without leaving the board?
- A: A PR card has a Diff button; it opens a diff card beside it (files with
  + and − counts on top, then coloured lines, scrollable like a document),
  from `gh pr diff` via `GET /api/diff`. It refetches only when the PR's head
  commit changes; over 1 MB is cut. Stored as a card with `diff: <PR url>`.
- Why: the user's idea, greenlit 2026-10-26.
- Status: done (PR open)

### Sending a card
- Q: How does Claude send a card?
- A: `curl -s localhost:8766/api/links -d "{\"url\":\"...\",\"title\":\"...\",\"term\":\"$WINLIST_TERM\",\"cwd\":\"$PWD\"}"`.
  Cards the page adds itself send `from: 'page'`.
- Why: so the card lands by its terminal (#6), and the page's own cards don't go to the Inbox.
- Status: standing rule

## Palette and help

### Mode badge (#32)
- Q: Where does the mode (NORMAL / INSERT / TILE) show?
- A: In a small fixed badge in the bottom-left corner, above tiles and cards,
  not in the top bar. It shows with the bar collapsed too.
- Why: the user's request (2026-10-26): see the mode at a glance, and keep the
  collapsible bar free of it.
- Status: done

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

### #34 Pointing Claude at a tile
- Q: How do you hand a tile (a note, a terminal, a window) to Claude?
- A: `y` copies a link to `/api/what?ref=wl:<kind>:<id>` for the picked tile.
  Claude asks it and gets what the tile is and how to get at it. A note can
  be read and changed this way, through the server, since it is not a file.
- Why: it works with any Claude, inside winlist or not, with nothing to
  remember. The link explains itself where a bare id would not.
- Status: built 2026-10-26

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

### #9 Where a closed note goes
- Q: Where do closed notes go?
- A: Nowhere: a note is a card in `~/.local/state/winlist/links.json`, its text kept on the card. Closing it sends DELETE /api/links/<id>, and the server drops the card and rewrites the file. No trash, archive or undo; only a backup of links.json brings one back.
- Why: the user asked (2026-10-26) and turned down a "closed notes" bin.
- Status: done

### #29 One session fills the usage log with fake card adds
- Q: How do old loop entries (one page logged 1584 card adds) stop skewing the usage report?
- A: Both: the page logs nothing when `navigator.webdriver` is true or the URL has `?nolog`; usage_report.py drops one page's events of one kind when it logs 300+ in a minute, says how many it ignored, and `--all` shows everything. The poll never counted cards after PR #88 (placed cards are not adds).
- Why: card adds looked like the top action. 300, not 100: fast key repeat reaches ~200 a minute in real use; the loop made 480-620.
- Status: done (PR)

### Note editor looks like the note
- Q: Should typing a note look different from reading it?
- A: No: the editor uses the note's own font (14px system-ui), and it grows with the text so the card is the only thing that scrolls.
- Why: the user saw two scrollbars and the font switch to monospace when editing (2026-10-26).
- Status: done (PR)

### Pulses survive a reload and a restart
- Q: Should a pulse (a new card, or Claude finished in a window) stop when the page reloads or the server restarts?
- A: No: new-card pulses are kept in the browser, pings in `~/.local/state/winlist/pings.json`. Both still clear once you have looked at the tile. A ping older than a week is dropped at start.
- Why: the user saw a reload clear the pulse (2026-10-26).
- Status: done (PR)

### #25 The X on a terminal kills a running Claude at once
- Q: What should closing a busy terminal do?
- A: Release + ask: the X closes only on a click that did not move (a press that drags, or a second finger, closes nothing). A terminal running Claude or another program asks on its caption first: a second click or Enter closes, while Esc, a click elsewhere or 4 seconds keep it. An idle shell closes at once. Cards' X also answers only a click.
- Why: a Claude session was lost to a pan or zoom that started on the X (2026-10-29). The X fired on the press.
- Status: done (PR)

### #35 Off-view markers drift into the middle of the screen
- Q: Fix it how?
- A: Snap the frame back: any scroll of #pan is reset to 0,0. The surface is placed by its origin and never scrolled.
- Why: the user saw the triangles inside the view while scrolling a terminal (2026-10-29).
- Status: done (PR)

### Zoom snaps to 1:1 near it
- Q: Terminal text looks blurry at 97%. What should happen?
- A: A zoom that comes to rest within 10% of 100% (90-110%) snaps to exactly 100%, on whole pixels, after 0.3 s, and not while fingers are still pinching. Elsewhere the zoom stays where you left it.
- Why: anywhere but 1:1 every glyph is resampled and the text goes soft (2026-10-29). The user chose this over drawing terminals at a font sized to the zoom.
- Status: done (PR)

### #11 Minimap
- Q: When is the map of the surface shown?
- A: While you pan or zoom, fading 1.2 s after; `m` (or the palette) keeps it shown, remembered across reloads. Bottom-right, 220x150: every tile as a box in its app colour, a pinging one orange, the picked one outlined, filtered-out ones faint, the view as a frame. A press or drag on it carries the view there, and doesn't take the keyboard from the terminal you're typing in.
- Why: zoom is the most used action, mostly zooming out to find something and back (2026-10-29 log review). The user asked to try it; Claude's pick, as no option was chosen.
- Status: done (PR)

### #16 1 toggles: actual size and back
- Q: How should 1 get you back?
- A: A second 1 goes back to the exact zoom and position the first came from, with a short "back to 72%" toast, as long as you haven't panned or zoomed since. Any move of your own (wheel, pinch, drag, the map, a pick that scrolls the view) forgets the way back, and 1 then does 1:1 again. The way back is kept across a reload. Pressing 1 at 100% saves nothing.
- Why: of 118 presses of 1 in Oct 23-29, 115 were followed by a zoom within 5 s (2026-10-29 log review). #38's fly-in should reuse the same slot.
- Status: replaced by "Double Ctrl" below

### #41 The usage log records what you type in a group's folder or name
- Q: The log spelled out text typed into a group's name and folder chips. Fix it how, and what about the lines already logged?
- A: Fix + scrub. The page now counts anything that takes text as typing (contenteditable, open dialogs and menus too), and logs only the keys it acts on by name; any other key is 'other', with no character. `winlist/scrub_usage.py` masks the old lines once, keeping a backup beside the log. The report applies the same mask whenever it reads, so anything that slips through is hidden: a run of keys less than 3 s apart that holds a non-page character was typing, and every character in it becomes 'char'.
- Why: the log's promise is "never what is typed"; folder paths were in it (found in the 2026-10-29 log review).
### Text stays sharp at 100%
- Q: Text was still soft at "100%". Why?
- A: The label rounds, so a zoom saved before the snap (e.g. 99.7%) showed as 100% but was still resampled; and tiles and the surface could sit on half pixels (a tile centred on a point lands on x.5). Now a kept zoom near 1:1 snaps at load, the surface and every tile are placed on whole screen pixels, and at exactly 1:1 terminals and text cards are not scaled at all.
- Why: the user saw the blur again after the snap (2026-10-29).
- Status: done (PR)

### #44 A new terminal takes the keyboard
- Q: Should a new terminal (t, c, the palette) be ready to type in, or stay picked in NORMAL until Enter?
- A: Type at once. Once it is listed, the new terminal is focused, as a new terminal window is. If you press a key or click anything while it is starting, it is only picked: you have moved on. Keys typed before its socket opens are held and sent when it does. A terminal a tool button starts runs its own command, so it is only picked.
- Why: usage log, Oct 23-29: of 77 new terminals, the next action was Enter 32 times, a median of 2.3 s later.
- Status: done (PR)

### #23 Split app.js into modules
- Q: Split the 3.2k-line app.js into ES modules, or not?
- A: Not split; a parse check instead. `winlist/check_page.sh` parses every page script as the browser will (app.js as a module, index.html's inline scripts), and a GitHub workflow runs it on each PR that touches the page.
- Why: the page shares 39 top-level variables that many sections reassign, and a module cannot assign another's, so a split is a rewrite, not a move: risk with no visible gain. What broke the page in PR #85, a name declared twice, is a parse error in a module, which the check catches.
- Status: done (PR)

### PgUp/PgDn scroll the picked tile in NORMAL
- Q: Scroll a card or terminal without going into it?
- A: Yes. In NORMAL, PgUp/PgDn scroll the picked tile a page: a terminal's (or restored husk's) scrollback, or a document, note or diff card. A Claude terminal (it reads the mouse) gets a page of wheel turns; vim or less gets the key. Desktop windows and link cards: nothing.
- Why: asked by the user 2026-10-30; reading output meant going in and coming out again.
- Status: done (PR)

### #19 Claude chip outlives Claude
- Q: How should a stale Claude chip go away?
- A: Both. For a page terminal the server looks under its shell each poll; with no claude process anywhere below it for 5 s, the chip goes. The whole tree is looked at, not the foreground, because Claude running a tool puts bash or node in front. And ping_hook.sh sends 'gone' on SessionEnd, which clears it at once, X windows included; a crash in an X window still waits for the 30-minute timeout.
- Why: quitting Claude left 'done' or 'waiting' on the tile for good.
- Status: done (PR)

### #18 Reset layout off the top bar
- Q: Where should Reset layout live?
- A: Only in the `:` palette, marked with a ⚠ and an amber highlight. The first Enter (or click) only arms it, and the row says it can't be undone; a second Enter runs it. Typing anything else disarms it.
- Why: the usage log never recorded it in a week, and an always-visible button for something that throws away the whole arrangement is the wrong shape.
- Status: done (PR)

### Ctrl+W in a terminal no longer closes the board unasked
- Q: Ctrl+W (delete a word in bash) closes the whole tab, because Chrome takes it before the page. What to do?
- A: While a terminal has the keyboard, leaving the page asks first (beforeunload: Chrome's "Leave site?"). In NORMAL nothing asks. A reload while typing in a terminal asks too. The terminals themselves always survive in pty_server.
- Why: the likeliest accidental close left after the X fixes (2026-10-30). Skipped for now: undoing a shell exit (Ctrl+D) or a Claude exit.
- Status: done (PR)

### A ⋯ menu instead of the X on every tile
- Q: How to stop accidental closes for good: hold the X, an undo list, or a menu?
- A: A ⋯ on every closable tile (terminals, cards, groups) opens its options. For now: Font (terminals; cycles, menu stays open) and Close. Close turns into "Confirm: close … ✕" in place, and only that closes: three deliberate clicks. Esc or a press elsewhere puts the menu away. It replaces the X, #25's "Close Claude?" question and the font name in the caption. No undo list for now.
- Why: the X kept closing things during pans and zooms (2026-10-29/30). A menu can't be closed through by a stray press, and it gives the caption one place for options.
- Status: done (PR)

### Double Ctrl flips overview ⇄ 100%; the 1 key is gone
- Q: The 1 key only works in NORMAL and its way back is fragile. Something better?
- A: Tap Ctrl twice (no other key, click or wheel between, within 350 ms) in any mode, typing in a terminal included: at 100% it goes to the 30% overview, anywhere else to 100%, about the picked tile. 1 and its saved way back are removed; the palette row is "Overview / 100%".
- Why: resting zooms cluster at 25-35% (28%) and 100%; after 1, the view was zoomed by hand again within 2 min 119 of 173 times (2026-10-30 log review). Ctrl alone sends nothing to a terminal, so it is free in every mode.
- Status: done (PR)

### #39 Cards from a terminal stack in a column beside it
- Q: Cards Claude sends land at the terminal's top right and step down-right over each other and over neighbours. Place them how?
- A: A column on the terminal's right: the first gap from its top down, with nothing overlapping (real rectangles, half a grid apart). If the right side is full (about 8 card heights), under the terminal, then down its left side, then the old step down and right. Cards into a group, the Inbox and new terminals are unchanged. The view doesn't move.
- Why: Oct 23-29, 35 of 109 arrived cards (32%) were dragged within a minute, and cards are the most dragged tile (290 drags). The old check only compared top-left corners.
### #43 A sharper usage log
- Q: Several findings were guesses because the log couldn't say how a tile was picked or entered, that you panned, or why something closed. Add how much?
- A: All of it. pick {kind, by, n} when the pick changes; activate gains {by, n}; by is click, key, dbl, enter, space, palette, new, back, exit or auto. n is a tile's number for this page load (1, 2, 3…), never a title, URL or id, so re-entering the same tile shows. pan {d} once on release, only if it moved. term.close {why: menu|exit}, card.close {kind, gh}. The page closing is now page.close; the report reads both. usage_report.py adds picks and entries by source, re-entry share, closes by cause and pans per active minute.
- Why: #36, #37, #38 and #40 rested on guesses (2026-10-29 log review). Next review measures.
- Status: done (PR)
