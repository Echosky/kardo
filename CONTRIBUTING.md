# Contributing to Kardo

Thanks for helping. Kardo is small on purpose, and a few ground rules keep it that way.

## Ground rules

1. **No runtime dependencies.** The server uses only the Python standard library; the web app is plain
   JavaScript, HTML and CSS with no framework and no build step. This is what lets anyone read the whole
   thing, run it on anything with Python, and trust it with their data. Dev-only tools (like `genanki` for
   rebuilding the sample decks) are fine.
2. **Your data stays yours.** No telemetry, no outbound requests, no CDN assets.
3. **Phone first.** Every screen has to work one-handed on a small phone, in light and dark mode.
4. **Don't lose progress.** Anything that touches the schema or the importer must keep existing
   collections working. Add a migration rather than changing a table in place.

## Development setup

```sh
git clone https://github.com/Echosky/kardo && cd kardo
KARDO_DATA=./data PORT=8484 python3 server.py
```

Open <http://localhost:8484>. Python 3.10 or newer is all you need. Edit `static/` files and reload the
page; restart the server after editing `server.py` or `lab.py`.

Useful extras:

```sh
python3 server.py import samples/*.apkg        # load the sample decks (uses KARDO_DATA)
python -m unittest discover -s tests -v         # run the test suite
pip install genanki pillow && python scripts/make_samples.py   # rebuild samples/
```

To try the app on your phone while developing, run the server on your LAN and open
`http://<your-computer-ip>:8484` on the phone.

## Making a change

- **Open an issue first** for anything bigger than a bug fix, so we can agree on the approach before you spend time on it.
- **Add or update tests** in `tests/` for behaviour changes. Scheduler and importer changes need tests.
- **Match the surrounding style.** Short functions, a docstring on anything non-obvious, comments that
  explain *why*. Python follows PEP 8 with a 120-column limit. JavaScript is modern ES2020 with no transpiling.
- **Keep the UI text plain and friendly.** Error messages should tell people what to do next.
- **Screenshots** for UI changes help a lot in the pull request.
- **Bump the service-worker cache name** in `static/sw.js` when you change files in its `SHELL` list, so
  installed apps pick up the new version.

## Adding SQL Lab exercises

Exercises are plain text in `lab_exercises.txt`; the format is described at the top of the file. Every
exercise needs a reference solution, and the test suite checks that each solution passes its own checker.

## Good first contributions

- Card editing in the browser
- FSRS as an alternative scheduler
- A per-deck options preset
- Importing the newest `.apkg` format (zstd-compressed `collection.anki21b`) without relying on the legacy export
- Translations of the UI

## Reporting bugs

Use the bug report template. For import problems, the most useful thing is a small `.apkg` that
reproduces it (strip personal content first). Security issues: see [SECURITY.md](SECURITY.md).

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
