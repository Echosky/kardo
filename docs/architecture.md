# Architecture

Kardo is deliberately small: about 1,100 lines of Python for the server, 700 for the SQL Lab, and 1,100 of
JavaScript and CSS for the app. There's no framework on either side and no build step.

```
browser / Home Screen app                server.py (ThreadingHTTPServer)
┌──────────────────────────┐   JSON    ┌────────────────────────────────────┐
│ index.html               │ ────────► │ /api/*      study, import, stats…  │
│ app.js  (views, router)  │ ◄──────── │ /media/*    images & audio         │
│ lab.js  (SQL Lab views)  │           │ /*          static app files       │
│ style.css, sw.js         │           └───────┬───────────────┬────────────┘
└──────────────────────────┘                   │               │
                                         kardo.db (SQLite)   lab.py (in-memory
                                         + media/ folder     practice databases)
```

## Server (`server.py`)

One file, top to bottom:

- **Settings**: `DEFAULTS` plus validation. Stored as JSON values in a `settings` table.
- **Scheduler**: `schedule()` is a pure function: given a card, a rating, the time and the settings, it returns the card's new fields. Everything else (picking cards, logging) is around it, which is what makes it easy to test.
- **Study queue**: `next_card()` decides what to show; `answer_card()` applies a rating in a transaction and stores a snapshot of the card's previous state in the review log, which is what `undo_last()` restores.
- **Overview and stats**: deck tree with counts, tags, and the numbers for the statistics screen, all computed with SQL on demand.
- **Importers**: `import_apkg()` opens the collection inside the zip with `sqlite3`, renders every card with `render_template()`, copies media, and upserts cards by `guid:ord`. `import_csv()` handles delimited text with Anki's header lines.
- **HTTP**: a `BaseHTTPRequestHandler` with a hand-written router. API calls run under one global lock, so writes never interleave; SQL Lab queries run outside it so a slow query can't block studying.

### Why cards are stored pre-rendered

Anki stores *notes* and renders cards from templates every time it shows one. Kardo renders once at import and
stores each card's front and back HTML. Studying becomes a simple lookup, the phone never needs a template engine,
and the server never has to understand a template again. The cost is that changing a note type means re-importing
the deck, which is cheap and keeps progress.

### Data model

| Table | Purpose |
|---|---|
| `decks` | Full deck names (`Parent::Child`); parents are created automatically |
| `notetypes` | CSS for each imported note type |
| `cards` | One row per card: rendered HTML, deck, tags, and scheduling fields (`state`, `due`, `ivl`, `ease`, `reps`, `lapses`, `step`) |
| `revlog` | One row per answer: rating, intervals, ease, time taken, and an undo snapshot |
| `settings` | Key/value JSON |
| `lab_progress` | SQL Lab attempts and solved exercises |

`state` is one of `new`, `learning`, `review`, `relearning`. `due` is a unix timestamp. For review cards it's set
to the start of the study day the card is due on, and for learning cards it's the exact minute.

## App (`static/`)

- **`app.js`**: a hash router (`#/deck/3`, `#/study/3`, …) and one async function per screen that fetches JSON and renders HTML strings. Event listeners are attached after each render; a view can register a `cleanup` callback for timers and global listeners.
- **Card rendering**: each card is drawn inside a **shadow root** together with its note type's CSS. Deck styles can't leak into the app and the app's styles can't break a card. In dark mode the card gets Anki's `nightMode` classes.
- **`lab.js`**: the SQL Lab screens, using the helpers from `app.js`.
- **`sw.js`**: a network-first service worker that caches the app shell for fast starts. API responses are never cached, because the server is the source of truth for your schedule.
- **Theming** uses CSS custom properties with light and dark sets; the theme can follow the system or be fixed in settings.

## Design choices

| Choice | Why |
|---|---|
| Standard library only | Nothing to install or patch; runs anywhere Python runs; easy to audit |
| SQLite in WAL mode | One file, transactional, fast, trivially backed up |
| Server-side scheduling | One source of truth across devices; no sync conflicts |
| No auth | The supported deployment is a private network (see [SECURITY.md](../SECURITY.md)); auth belongs in the proxy you already trust |
| No build step | `git clone` and run; contributors can change the UI with a text editor |
