# Changelog

All notable changes to Kardo are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/)
and versions follow [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-10-26

Android support across screen sizes.

### Added
- Layout size classes for Android phones and foldables: compact (360px and below, including the Galaxy Z Fold cover screen), standard (Pixel and Galaxy S/Ultra), wide (unfolded Z Fold and Pixel Fold, tablets) and short landscape.
- Maskable app icon, so the home-screen icon fills Android's adaptive icon shapes.

### Changed
- The app height follows Chrome's collapsing address bar (`dvh`), and the on-screen keyboard resizes the page instead of covering the SQL editor.
- Landscape phones get a compact top bar and single-line answer buttons, giving the card about 25% more room.
- Wide screens use a wider column and a four-tile stats row.

## [1.0.0] - 2026-10-26

First public release.

### Added
- Anki `.apkg` import: subdecks, multiple templates, note-type CSS, images, audio, cloze, tags, conditional sections.
- CSV/TSV/TXT import with Anki header lines; re-import updates card text and keeps progress.
- SM-2 style scheduler with learning and relearning steps, ease, fuzz, daily limits, maximum interval, day rollover and undo.
- Interleaved, sequential or random order for new cards.
- Practice quizzes that don't affect scheduling; tag filter; card browser with suspend and reset.
- Statistics: today, 30-day recall, streak, 14-day forecast and history, per-deck maturity.
- Installable PWA with light and dark themes and keyboard shortcuts.
- One-tap SQLite backup.
- Port check at startup: a clear message when the port is taken, or the next free port when none was chosen.
- SQL Lab with 151 graded exercises in 13 tracks.
- Docker image (amd64 and arm64), Docker Compose file and Unraid template.
- Sample decks, test suite and CI.
