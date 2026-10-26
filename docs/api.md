# HTTP API

The app talks to the server through a small JSON API, which you can also use from scripts. All endpoints are
under `/api/`. Errors come back as `{"error": "message"}` with a 4xx or 5xx status.

Send `X-TZ-Offset: <minutes east of UTC>` (for example `120` for UTC+2) so "today" matches your clock; without
it the server's time zone is used.

## Decks and studying

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/decks` | Deck tree with `total`, `new`, `learn`, `review` counts for today |
| `DELETE` | `/api/decks/<id>` | Delete a deck, its subdecks, cards and history |
| `GET` | `/api/next?deck=<id>&tag=<tag>` | Next card to study plus today's counts. Both parameters are optional |
| `POST` | `/api/answer` | Body `{"card_id", "rating": 1-4, "elapsed_ms", "deck", "tag"}`. Returns the next card |
| `POST` | `/api/undo` | Body `{"deck", "tag"}`. Undoes the last answer and returns that card |
| `GET` | `/api/practice?deck=&tag=&limit=50&only=struggling\|seen` | Random cards for a quiz; doesn't change scheduling |

A card object looks like:

```json
{
  "id": 412,
  "front": "<div class=\"flag\"><img src=\"/media/kardo_flag_canada.png\"></div>…",
  "back": "…<hr id=\"answer\"><div class=\"answer\">Canada</div>…",
  "css": ".card { … }",
  "deck": "Geography::Flags & Capitals",
  "tags": ["geography", "north_america"],
  "state": "review",
  "intervals": {"1": "10m", "2": "6d", "3": "13d", "4": "21d"}
}
```

## Cards

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/cards?q=&deck=&tag=&state=&limit=100&offset=0` | Search and filter. `state`: `new`, `learning`, `review`, `due`, `suspended`, `struggling` |
| `GET` | `/api/cards/<id>` | One card |
| `POST` | `/api/cards/<id>` | Body `{"action": "suspend" \| "unsuspend" \| "forget"}` |
| `GET` | `/api/tags` | All tags with counts |

## Import, settings, stats, backup

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/import?filename=<name>&deck_name=<deck>` | Raw file as the request body. Returns `{"added", "updated", "skipped", "media"}` |
| `GET` | `/api/settings` | Current settings |
| `POST` | `/api/settings` | Partial settings object; returns the full settings. Keys are listed in [scheduling.md](scheduling.md#settings-reference) |
| `GET` | `/api/stats?deck=<id>` | Today, 30-day recall, streak, forecast, history, per-deck breakdown |
| `GET` | `/api/backup` | Consistent SQLite copy of the whole database |
| `GET` | `/api/health` | `{"ok": true}`; used by the Docker health check |

## SQL Lab

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/lab` | Tracks and exercises with progress |
| `GET` | `/api/lab/schema` | Practice database tables and columns |
| `GET` | `/api/lab/ex/<id>` | One exercise |
| `GET` | `/api/lab/ex/<id>/expected` | Expected result |
| `GET` | `/api/lab/ex/<id>/solution` | Reference solution |
| `POST` | `/api/lab/run` | Body `{"sql", "ex"?, "explain"?}`. Runs SQL; with `ex` it also checks the answer |
| `POST` | `/api/lab/reset` | Clears SQL Lab progress |

## Examples

```sh
# Import a deck
curl -X POST --data-binary @spanish.apkg "http://kestrel:8484/api/import?filename=spanish.apkg"

# How many cards are due today, per deck?
curl -s http://kestrel:8484/api/decks | jq -r '.decks[] | "\(.review)\t\(.name)"'

# Cap intervals at 7 days before an exam
curl -X POST -H 'Content-Type: application/json' -d '{"max_ivl": 7}' http://kestrel:8484/api/settings

# Nightly backup
curl -fsS http://kestrel:8484/api/backup -o kardo-$(date +%F).db
```
