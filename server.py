#!/usr/bin/env python3
"""Kardo: a small self-hosted spaced-repetition flashcard server.

Standard library only. Serves the web app from ./static and keeps every deck,
card and review in one SQLite file under $KARDO_DATA (default /data).

How the file is laid out, top to bottom:

  settings      defaults and validation for the scheduler options
  scheduler     SM-2 style scheduling: learning steps, ease, intervals, fuzz
  study queue   which card comes next, daily limits, answering and undo
  overview      deck tree, tags and statistics
  browse        search, suspend and reset cards
  importers     Anki .apkg (templates, cloze, CSS, media) and CSV/TXT
  HTTP          a ThreadingHTTPServer with a small JSON API
  SQL Lab       progress tracking for the optional SQL practice module (lab.py)

Cards are stored already rendered: an imported note becomes one row per card with
its front and back HTML, so studying never needs Anki's template engine. The
note's guid plus the card number is kept, which is what lets a re-import update
the text in place without touching the card's schedule.

Environment: KARDO_DATA (data folder), PORT (default 8484), KARDO_LOG=0 (quiet).
"""
import csv
import errno
import hashlib
import html
import io
import json
import mimetypes
import os
import random
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import lab

DATA = os.environ.get("KARDO_DATA", "/data")
PORT = int(os.environ.get("PORT", "8484"))
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MEDIA = os.path.join(DATA, "media")
DB_PATH = os.path.join(DATA, "kardo.db")
MAX_UPLOAD = 300 * 1024 * 1024
LEARN_AHEAD = 20 * 60  # seconds a learning card may be shown early when nothing else is left

DEFAULTS = {
    "new_per_day": 25,
    "max_reviews": 400,
    "learn_steps": "1 10",
    "relearn_steps": "10",
    "graduating_ivl": 1,
    "easy_ivl": 4,
    "starting_ease": 2.5,
    "easy_bonus": 1.3,
    "hard_mult": 1.2,
    "lapse_mult": 0.0,
    "max_ivl": 36500,
    "rollover_hour": 4,
    "new_order": "interleave",  # interleave | sequential | random
}

SCHEMA = """
create table if not exists decks(id integer primary key, name text unique not null);
create table if not exists notetypes(id integer primary key, name text not null, css text not null default '');
create table if not exists cards(
  id integer primary key,
  guid text unique not null,
  deck_id integer not null,
  notetype_id integer,
  front text not null,
  back text not null,
  tags text not null default ' ',
  sort_text text not null default '',
  state text not null default 'new',
  due integer not null default 0,
  ivl integer not null default 0,
  ease real not null default 2.5,
  reps integer not null default 0,
  lapses integer not null default 0,
  step integer not null default 0,
  suspended integer not null default 0,
  new_pos integer not null default 0,
  last_review integer,
  created integer not null default 0
);
create index if not exists ix_cards_deck on cards(deck_id);
create index if not exists ix_cards_sched on cards(state, due);
create table if not exists revlog(
  id integer primary key,
  card_id integer not null,
  ts integer not null,
  rating integer not null,
  state text not null,
  ivl integer not null,
  prev_ivl integer not null,
  ease real not null,
  elapsed_ms integer not null default 0,
  undo text
);
create index if not exists ix_revlog_ts on revlog(ts);
create index if not exists ix_revlog_card on revlog(card_id);
create table if not exists settings(key text primary key, value text not null);
create table if not exists lab_progress(
  ex_id text primary key,
  attempts integer not null default 0,
  solved_at integer,
  last_sql text not null default '',
  updated integer not null default 0
);
"""

os.makedirs(MEDIA, exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
db.row_factory = sqlite3.Row
db.execute("pragma journal_mode=wal")
db.execute("pragma foreign_keys=on")
db.executescript(SCHEMA)
lock = threading.RLock()


class ApiError(Exception):
    """An error the client should see: becomes a JSON {"error": ...} response with this HTTP status."""
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


# ---------------------------------------------------------------- settings

def get_settings():
    """Scheduler settings: the defaults overlaid with whatever the user has saved."""
    s = dict(DEFAULTS)
    for r in db.execute("select key, value from settings"):
        if r["key"] in s:
            s[r["key"]] = json.loads(r["value"])
    return s


def save_settings(new):
    """Validate and store settings from the Settings screen. Unknown keys are ignored."""
    for k, v in new.items():
        if k not in DEFAULTS:
            continue
        d = DEFAULTS[k]
        if isinstance(d, (int, float)) and not isinstance(d, bool):
            try:
                v = type(d)(v)
            except (TypeError, ValueError):
                raise ApiError(f"{k} must be a number")
            if v < 0:
                raise ApiError(f"{k} cannot be negative")
        elif k in ("learn_steps", "relearn_steps"):
            v = " ".join(str(v).replace(",", " ").split())
            if not v or not all(re.fullmatch(r"\d+(\.\d+)?", x) for x in v.split()):
                raise ApiError(f"{k} must be minutes separated by spaces, like '1 10'")
        elif k == "new_order" and v not in ("interleave", "sequential", "random"):
            raise ApiError("new_order must be interleave, sequential or random")
        db.execute("insert into settings(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
                   (k, json.dumps(v)))


# ---------------------------------------------------------------- time helpers

def day_start(now, tz_min, rollover):
    """Unix time when the current study day began, in the viewer's time zone."""
    off = tz_min * 60
    roll = int(rollover) * 3600
    local = now + off - roll
    return (local // 86400) * 86400 + roll - off


def fmt_span(sec):
    """Human-friendly length of time for the answer buttons and browser, e.g. 10m, 4d, 1.5mo."""
    sec = max(0, sec)
    if sec < 60:
        return "<1m"
    if sec < 3600:
        return f"{round(sec / 60)}m"
    if sec < 86400:
        return f"{round(sec / 3600)}h"
    d = sec / 86400
    if d < 30:
        return f"{round(d)}d"
    if d < 365:
        m = d / 30.4
        return f"{m:.1f}".rstrip("0").rstrip(".") + "mo"
    y = d / 365
    return f"{y:.1f}".rstrip("0").rstrip(".") + "y"


# ---------------------------------------------------------------- scheduler (SM-2 style)

def _steps(s):
    """Parse a learning-steps string such as '1 10' into a list of minutes."""
    out = [max(0.1, float(x)) for x in str(s).split()]
    return out or [1.0]


def schedule(card, rating, now, ds, S, fuzz=True):
    """Return the card fields after answering with rating 1=Again 2=Hard 3=Good 4=Easy.

    card  current card fields (state, due, ivl, ease, reps, lapses, step)
    now   answer time (unix seconds); ds is the start of the current study day
    S     settings from get_settings(); fuzz=False makes it deterministic (button previews, tests)

    New and (re)learning cards walk through minute-based steps; once they graduate
    they become review cards whose interval in days grows by the ease factor.
    """
    c = {k: card[k] for k in ("state", "due", "ivl", "ease", "reps", "lapses", "step")}
    c["reps"] += 1
    state = c["state"]

    def graduate(days):
        """Move the card to the review queue with an interval of `days`."""
        days = int(min(S["max_ivl"], max(1, days)))
        c.update(state="review", ivl=days, step=0, due=ds + days * 86400)

    if state in ("new", "learning", "relearning"):
        relearn = state == "relearning"
        steps = _steps(S["relearn_steps"] if relearn else S["learn_steps"])
        i = 0 if state == "new" else min(c["step"], len(steps) - 1)
        if state == "new":
            c["ease"] = float(S["starting_ease"])
        if rating == 1:
            i, delay = 0, steps[0]
        elif rating == 2:
            if i == 0 and len(steps) > 1:
                delay = (steps[0] + steps[1]) / 2
            elif len(steps) == 1:
                delay = min(steps[0] * 1.5, steps[0] + 1440)
            else:
                delay = steps[i]
        elif rating == 3:
            i += 1
            delay = steps[i] if i < len(steps) else None
        else:
            delay = None
        if delay is None:
            if relearn:
                graduate(c["ivl"] + (1 if rating == 4 else 0))
            else:
                graduate(S["easy_ivl"] if rating == 4 else S["graduating_ivl"])
        else:
            c.update(state="relearning" if relearn else "learning", step=i, due=int(now + delay * 60))
        return c

    # review card: Again lapses it, otherwise the interval grows. Days the card was overdue
    # count partly (Good) or fully (Easy), since remembering it late shows it was well known.
    ivl = max(1, c["ivl"])
    late = max(0, (ds - c["due"]) // 86400)
    ease = c["ease"]
    if rating == 1:
        c["lapses"] += 1
        c["ease"] = max(1.3, ease - 0.2)
        c["ivl"] = max(1, int(ivl * S["lapse_mult"]))
        steps = _steps(S["relearn_steps"])
        c.update(state="relearning", step=0, due=int(now + steps[0] * 60))
        return c
    hard = max(ivl + 1, ivl * S["hard_mult"])
    good = max(hard + 1, (ivl + late / 2) * ease)
    easy = max(good + 1, (ivl + late) * ease * S["easy_bonus"])
    new_ivl = {2: hard, 3: good, 4: easy}[rating]
    if rating == 2:
        c["ease"] = max(1.3, ease - 0.15)
    elif rating == 4:
        c["ease"] = ease + 0.15
    # +/-5% jitter so cards learned together don't stay due on the same day forever
    if fuzz and new_ivl >= 3:
        spread = max(1, new_ivl * 0.05)
        new_ivl = random.uniform(new_ivl - spread, new_ivl + spread)
    new_ivl = int(min(S["max_ivl"], round(new_ivl)))
    c.update(ivl=new_ivl, due=ds + new_ivl * 86400)
    return c


def preview(card, now, ds, S):
    """The interval each answer button would give this card, for the labels under Again/Hard/Good/Easy."""
    out = {}
    for r in (1, 2, 3, 4):
        c = schedule(card, r, now, ds, S, fuzz=False)
        out[r] = fmt_span(c["due"] - now) if c["state"] != "review" else fmt_span(c["ivl"] * 86400)
    return out


# ---------------------------------------------------------------- decks, tags, filters

def ensure_deck(name):
    """Return the id of a deck by its full 'Parent::Child' name, creating it and its parents if needed."""
    name = "::".join(p.strip() for p in name.split("::") if p.strip()) or "Default"
    parts = name.split("::")
    did = None
    for i in range(1, len(parts) + 1):
        n = "::".join(parts[:i])
        db.execute("insert or ignore into decks(name) values(?)", (n,))
        did = db.execute("select id from decks where name=?", (n,)).fetchone()[0]
    return did


def deck_subtree(deck_id):
    """Ids of a deck and all of its subdecks."""
    row = db.execute("select name from decks where id=?", (deck_id,)).fetchone()
    if not row:
        raise ApiError("deck not found", 404)
    name = row["name"]
    return [r[0] for r in db.execute("select id from decks where name=? or name like ? escape '\\'",
                                      (name, like_escape(name) + "::%"))]


def like_escape(s):
    """Escape %, _ and \\ so user text is matched literally in a LIKE pattern."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def card_filter(deck_id=None, tag=None, alias="c"):
    """SQL fragment + params for cards in a deck subtree (or all decks) with an optional tag."""
    where, params = [], []
    if deck_id:
        ids = deck_subtree(int(deck_id))
        where.append(f"{alias}.deck_id in ({','.join('?' * len(ids))})")
        params += ids
    if tag:
        t = like_escape(tag.strip())
        where.append(f"({alias}.tags like ? escape '\\' or {alias}.tags like ? escape '\\')")
        params += [f"% {t} %", f"% {t}::%"]
    return (" and ".join(where) or "1=1"), params


def norm_tags(tags):
    """Store tags as ' tag1 tag2 ' (padded, de-duplicated case-insensitively) so LIKE '% tag %' finds whole tags."""
    if isinstance(tags, str):
        tags = tags.split()
    seen = []
    for t in tags:
        t = t.strip()
        if t and t.lower() not in [x.lower() for x in seen]:
            seen.append(t)
    return " " + " ".join(seen) + " " if seen else " "


# ---------------------------------------------------------------- study queue

def today_counts(where, params, ds):
    """New cards introduced and review cards answered today within the filter."""
    r = db.execute(f"""select
          count(distinct case when r.state='new' then r.card_id end),
          sum(case when r.state='review' then 1 else 0 end)
        from revlog r join cards c on c.id=r.card_id
        where r.ts >= ? and {where}""", [ds] + params).fetchone()
    return r[0] or 0, r[1] or 0


def queue_counts(where, params, now, ds, S):
    """New, learning and due counts for today, after the daily limits are applied."""
    de = ds + 86400
    new_done, rev_done = today_counts(where, params, ds)
    base = f"from cards c where c.suspended=0 and {where}"
    new_avail = db.execute(f"select count(*) {base} and c.state='new'", params).fetchone()[0]
    rev_avail = db.execute(f"select count(*) {base} and c.state='review' and c.due < ?", params + [de]).fetchone()[0]
    learn = db.execute(f"select count(*) {base} and c.state in ('learning','relearning') and c.due < ?",
                       params + [de]).fetchone()[0]
    return {
        "new": max(0, min(new_avail, int(S["new_per_day"]) - new_done)),
        "learn": learn,
        "review": max(0, min(rev_avail, int(S["max_reviews"]) - rev_done)),
        "new_done": new_done,
        "review_done": rev_done,
    }


def pick_new_card(where, params, S):
    """Choose the next new card according to the 'Order of new cards' setting."""
    order = S["new_order"]
    base = f"from cards c where c.suspended=0 and c.state='new' and {where}"
    if order == "interleave":  # card 1 of each subdeck, then card 2 of each, and so on
        return db.execute(f"""select * from (select c.*, row_number() over (partition by c.deck_id order by c.new_pos) rn
            from cards c where {where}) c where c.suspended=0 and c.state='new' order by rn, deck_id limit 1""",
                          params).fetchone()
    key = "((c.id * 2654435761) % 4294967296)" if order == "random" else "c.new_pos"
    return db.execute(f"select c.* {base} order by {key} limit 1", params).fetchone()


def card_payload(row, now, ds, S):
    """Everything the app needs to show one card: rendered HTML, note-type CSS, deck and button intervals."""
    nt = db.execute("select css from notetypes where id=?", (row["notetype_id"],)).fetchone() if row["notetype_id"] else None
    deck = db.execute("select name from decks where id=?", (row["deck_id"],)).fetchone()
    return {
        "id": row["id"],
        "front": row["front"],
        "back": row["back"],
        "css": nt["css"] if nt else "",
        "deck": deck["name"] if deck else "",
        "tags": row["tags"].split(),
        "state": row["state"],
        "intervals": preview(row, now, ds, S),
    }


def next_card(deck_id, tag, now, tz):
    """Pick the next card to study: due learning cards first, then new and review cards mixed in proportion."""
    S = get_settings()
    ds = day_start(now, tz, S["rollover_hour"])
    where, params = card_filter(deck_id, tag)
    counts = queue_counts(where, params, now, ds, S)
    base = f"select c.* from cards c where c.suspended=0 and {where}"
    row = db.execute(f"{base} and c.state in ('learning','relearning') and c.due <= ? order by c.due limit 1",
                     params + [now]).fetchone()
    if not row:
        pick_new = counts["new"] > 0 and (counts["review"] == 0 or
                                          random.random() < counts["new"] / (counts["new"] + counts["review"]))
        if pick_new:
            row = pick_new_card(where, params, S)
        elif counts["review"] > 0:
            row = db.execute(f"{base} and c.state='review' and c.due < ? order by c.due, random() limit 1",
                             params + [ds + 86400]).fetchone()
    if not row:
        row = db.execute(f"{base} and c.state in ('learning','relearning') and c.due <= ? order by c.due limit 1",
                         params + [now + LEARN_AHEAD]).fetchone()
    nxt = None
    if not row:
        r = db.execute(f"select min(c.due) from cards c where c.suspended=0 and {where} and c.state in ('learning','relearning')",
                       params).fetchone()
        nxt = r[0]
    return {"card": card_payload(row, now, ds, S) if row else None, "counts": counts,
            "next_learning_due": nxt}


def answer_card(card_id, rating, elapsed_ms, now, tz):
    """Apply an answer: reschedule the card and log it, keeping a snapshot so it can be undone."""
    if rating not in (1, 2, 3, 4):
        raise ApiError("rating must be 1-4")
    S = get_settings()
    ds = day_start(now, tz, S["rollover_hour"])
    row = db.execute("select * from cards where id=?", (card_id,)).fetchone()
    if not row:
        raise ApiError("card not found", 404)
    c = schedule(row, rating, now, ds, S)
    snapshot = json.dumps({k: row[k] for k in ("state", "due", "ivl", "ease", "reps", "lapses", "step", "last_review")})
    db.execute("begin")
    try:
        db.execute("insert into revlog(card_id, ts, rating, state, ivl, prev_ivl, ease, elapsed_ms, undo) values(?,?,?,?,?,?,?,?,?)",
                   (card_id, now, rating, row["state"], c["ivl"], row["ivl"], c["ease"],
                    max(0, min(int(elapsed_ms or 0), 600000)), snapshot))
        db.execute("update cards set state=?, due=?, ivl=?, ease=?, reps=?, lapses=?, step=?, last_review=? where id=?",
                   (c["state"], c["due"], c["ivl"], c["ease"], c["reps"], c["lapses"], c["step"], now, card_id))
        db.execute("commit")
    except Exception:
        db.execute("rollback")
        raise


def undo_last(now, tz):
    """Undo the most recent answer, restoring the card exactly as it was."""
    r = db.execute("select * from revlog where undo is not null order by id desc limit 1").fetchone()
    if not r:
        raise ApiError("nothing to undo")
    snap = json.loads(r["undo"])
    db.execute("begin")
    db.execute("update cards set state=?, due=?, ivl=?, ease=?, reps=?, lapses=?, step=?, last_review=? where id=?",
               (snap["state"], snap["due"], snap["ivl"], snap["ease"], snap["reps"], snap["lapses"], snap["step"],
                snap["last_review"], r["card_id"]))
    db.execute("delete from revlog where id=?", (r["id"],))
    db.execute("commit")
    S = get_settings()
    row = db.execute("select * from cards where id=?", (r["card_id"],)).fetchone()
    return card_payload(row, now, day_start(now, tz, S["rollover_hour"]), S) if row else None


# ---------------------------------------------------------------- deck overview

def deck_tree(now, tz):
    """Every deck that holds cards, with today's counts, for the home screen."""
    S = get_settings()
    ds = day_start(now, tz, S["rollover_hour"])
    decks = [dict(r) for r in db.execute("select id, name from decks order by name collate nocase")]
    out = []
    for d in decks:
        where, params = card_filter(d["id"])
        total = db.execute(f"select count(*) from cards c where {where}", params).fetchone()[0]
        if total == 0:
            continue
        cnt = queue_counts(where, params, now, ds, S)
        out.append({"id": d["id"], "name": d["name"], "total": total,
                    "new": cnt["new"], "learn": cnt["learn"], "review": cnt["review"]})
    return out


def all_tags():
    """Every tag with its card count. Hierarchical tags (a::b) also count toward their parents."""
    counts = {}
    for (tags,) in db.execute("select tags from cards"):
        for t in tags.split():
            parts = t.split("::")
            for i in range(1, len(parts) + 1):
                k = "::".join(parts[:i])
                counts[k] = counts.get(k, 0) + 1
    return [{"tag": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: kv[0].lower())]


def stats(deck_id, now, tz):
    """Numbers for the Statistics screen: today, 30-day recall, streak, 14-day forecast and history, per-deck progress."""
    S = get_settings()
    ds = day_start(now, tz, S["rollover_hour"])
    where, params = card_filter(deck_id)
    today = db.execute(f"""select count(*), sum(case when r.rating>1 then 1 else 0 end), sum(r.elapsed_ms)
        from revlog r join cards c on c.id=r.card_id where r.ts>=? and {where}""", [ds] + params).fetchone()
    month = db.execute(f"""select count(*), sum(case when r.rating>1 then 1 else 0 end)
        from revlog r join cards c on c.id=r.card_id where r.ts>=? and r.state='review' and {where}""",
                       [ds - 29 * 86400] + params).fetchone()
    days = {int((ts - ds) // 86400) for (ts,) in db.execute(
        f"select r.ts from revlog r join cards c on c.id=r.card_id where r.ts >= ? and {where}",
        [ds - 400 * 86400] + params)}
    streak, d = 0, (0 if 0 in days else -1)
    while d in days:
        streak += 1
        d -= 1
    forecast = []
    for i in range(14):
        lo = -10 ** 12 if i == 0 else ds + i * 86400
        n = db.execute(f"select count(*) from cards c where c.suspended=0 and c.state in ('review','learning','relearning') and c.due >= ? and c.due < ? and {where}",
                       [lo, ds + (i + 1) * 86400] + params).fetchone()[0]
        forecast.append(n)
    history = []
    for i in range(13, -1, -1):
        n = db.execute(f"select count(*) from revlog r join cards c on c.id=r.card_id where r.ts >= ? and r.ts < ? and {where}",
                       [ds - i * 86400, ds - (i - 1) * 86400] + params).fetchone()[0]
        history.append(n)
    breakdown = []
    for d in deck_tree(now, tz):
        w, p = card_filter(d["id"])
        r = db.execute(f"""select count(*),
            sum(c.state='new'), sum(c.state in ('learning','relearning')),
            sum(c.state='review' and c.ivl<21), sum(c.state='review' and c.ivl>=21), sum(c.suspended)
            from cards c where {w}""", p).fetchone()
        breakdown.append({"id": d["id"], "name": d["name"], "total": r[0], "new": r[1] or 0, "learning": r[2] or 0,
                          "young": r[3] or 0, "mature": r[4] or 0, "suspended": r[5] or 0})
    struggling = db.execute(f"select count(*) from cards c where c.lapses>=3 and {where}", params).fetchone()[0]
    return {
        "today": {"reviews": today[0], "correct": today[1] or 0, "minutes": round((today[2] or 0) / 60000, 1)},
        "retention_30d": round(100 * (month[1] or 0) / month[0], 1) if month[0] else None,
        "reviews_30d": month[0],
        "streak": streak,
        "forecast": forecast,
        "history": history,
        "decks": breakdown,
        "struggling": struggling,
    }


# ---------------------------------------------------------------- browse

def strip_html(s):
    """Plain text of a card field, for search and the browser list."""
    s = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</div>|</p>|</li>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(html.unescape(s).split())


def browse(q, deck_id, tag, state, limit, offset, now, tz):
    """Search and filter cards for the Browse screen, one page at a time."""
    S = get_settings()
    ds = day_start(now, tz, S["rollover_hour"])
    where, params = card_filter(deck_id, tag)
    if q:
        for word in q.split():
            where += " and c.sort_text like ? escape '\\'"
            params.append(f"%{like_escape(word)}%")
    if state == "suspended":
        where += " and c.suspended=1"
    elif state == "struggling":
        where += " and c.lapses>=2"
    elif state == "learning":
        where += " and c.state in ('learning','relearning')"
    elif state in ("new", "review"):
        where += " and c.state=?"
        params.append(state)
    elif state == "due":
        where += " and c.state!='new' and c.due < ? and c.suspended=0"
        params.append(ds + 86400)
    total = db.execute(f"select count(*) from cards c where {where}", params).fetchone()[0]
    order = "c.lapses desc, c.id" if state == "struggling" else "c.deck_id, c.new_pos, c.id"
    rows = db.execute(f"""select c.id, c.sort_text, c.state, c.due, c.ivl, c.ease, c.lapses, c.reps, c.suspended, d.name deck
        from cards c join decks d on d.id=c.deck_id where {where} order by {order} limit ? offset ?""",
                      params + [limit, offset]).fetchall()
    items = []
    for r in rows:
        if r["state"] == "new":
            due = "new"
        elif r["state"] == "review":
            due = "today" if r["due"] < ds + 86400 else "in " + fmt_span(r["due"] - ds)
        else:
            due = "learning"
        items.append({"id": r["id"], "text": r["sort_text"][:160], "deck": r["deck"], "state": r["state"],
                      "due": due, "ivl": r["ivl"], "ease": round(r["ease"] * 100), "lapses": r["lapses"],
                      "reps": r["reps"], "suspended": bool(r["suspended"])})
    return {"total": total, "items": items}


def card_action(card_id, action):
    """Suspend, unsuspend or reset ('forget') a single card."""
    row = db.execute("select id from cards where id=?", (card_id,)).fetchone()
    if not row:
        raise ApiError("card not found", 404)
    if action == "suspend":
        db.execute("update cards set suspended=1 where id=?", (card_id,))
    elif action == "unsuspend":
        db.execute("update cards set suspended=0 where id=?", (card_id,))
    elif action == "forget":
        S = get_settings()
        db.execute("update cards set state='new', due=0, ivl=0, ease=?, step=0, reps=0, lapses=0 where id=?",
                   (S["starting_ease"], card_id))
    else:
        raise ApiError("unknown action")


def delete_deck(deck_id):
    """Delete a deck, its subdecks, their cards and their review history."""
    ids = deck_subtree(deck_id)
    marks = ",".join("?" * len(ids))
    db.execute("begin")
    db.execute(f"delete from revlog where card_id in (select id from cards where deck_id in ({marks}))", ids)
    db.execute(f"delete from cards where deck_id in ({marks})", ids)
    db.execute(f"delete from decks where id in ({marks})", ids)
    db.execute("commit")


# ---------------------------------------------------------------- template rendering for imports

CLOZE_RE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)


def render_cloze(text, ord_, side):
    """Render cloze deletions: card number ord_ becomes [...] (or its hint) on the front and is highlighted on the back."""
    def rep(m):
        n, body, hint = int(m.group(1)), m.group(2), m.group(3)
        if n != ord_:
            return body
        if side == "q":
            return f'<span class="cloze">[{hint or "..."}]</span>'
        return f'<span class="cloze">{body}</span>'
    return CLOZE_RE.sub(rep, text)


def render_template(tmpl, fields, side, ord_, front="", tags="", deck=""):
    """Render an Anki card template ({{Field}}, {{#Field}}...{{/Field}}, {{cloze:Field}}, {{FrontSide}} and friends)
    to static HTML at import time."""
    def is_empty(v):
        return not strip_html(v or "").strip() and "<img" not in (v or "")

    sec = re.compile(r"\{\{([#^])\s*([^}]+?)\s*\}\}(.*?)\{\{/\s*\2\s*\}\}", re.S)
    prev = None
    while prev != tmpl:
        prev = tmpl
        tmpl = sec.sub(lambda m: m.group(3) if (is_empty(fields.get(m.group(2).split(":")[-1], "")) == (m.group(1) == "^"))
                       else "", tmpl)

    def tag(m):
        spec = m.group(1).strip()
        if spec == "FrontSide":
            return front
        if spec == "Tags":
            return html.escape(tags.strip())
        if spec in ("Deck", "Subdeck"):
            return html.escape(deck if spec == "Deck" else deck.split("::")[-1])
        parts = spec.split(":")
        name, filters = parts[-1].strip(), [p.strip() for p in parts[:-1]]
        val = fields.get(name, "")
        for f in reversed(filters):
            if f == "cloze":
                val = render_cloze(val, ord_, side)
            elif f == "text":
                val = html.escape(strip_html(val))
            elif f.startswith("type") or f.startswith("tts"):
                val = ""
        return val

    out = re.sub(r"\{\{([^#^/][^}]*)\}\}", tag, tmpl)
    return fix_media(out)


def _media_src(prefix, src):
    """Point a relative media reference at /media/; absolute URLs and data: URIs are left alone."""
    if re.match(r"(?i)(https?:|data:|/)", src):
        return f'{prefix}"{src}"'
    return f'{prefix}"/media/{quote(html.unescape(src))}"'


def fix_media(s):
    """Rewrite <img>/<audio>/<video> sources and [sound:...] tags so imported media is served from /media/."""
    s = re.sub(r'(?i)(<(?:img|audio|video|source)\b[^>]*?\bsrc\s*=\s*)(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))',
               lambda m: _media_src(m.group(1), m.group(2) or m.group(3) or m.group(4) or ""), s)
    s = re.sub(r"\[sound:([^\]]+)\]", lambda m: f'<audio controls preload="none" src="/media/{quote(m.group(1))}"></audio>', s)
    return s


def safe_media_name(name):
    """Reduce a media file name to its base name so an archive can never write outside the media folder."""
    name = os.path.basename(name.replace("\\", "/"))
    return name if name and name not in (".", "..") else None


def upsert_card(guid, deck_id, nt_id, front, back, tags, sort_text, order_key, now, stats_):
    """Insert a card, or update the text of an existing one with the same guid while keeping its progress."""
    ex = db.execute("select id from cards where guid=?", (guid,)).fetchone()
    if ex:
        db.execute("update cards set deck_id=?, notetype_id=?, front=?, back=?, tags=?, sort_text=? where id=?",
                   (deck_id, nt_id, front, back, tags, sort_text, ex["id"]))
        stats_["updated"] += 1
    else:
        db.execute("""insert into cards(guid, deck_id, notetype_id, front, back, tags, sort_text, new_pos, created, ease)
            values(?,?,?,?,?,?,?,?,?,?)""", (guid, deck_id, nt_id, front, back, tags, sort_text, order_key, now,
                                              get_settings()["starting_ease"]))
        stats_["added"] += 1


def next_pos():
    """Position for the next new card, so imported cards are introduced after the ones already there."""
    return (db.execute("select max(new_pos) from cards").fetchone()[0] or 0) + 1


def import_apkg(data):
    """Import an Anki .apkg package: decks, note types (with CSS), notes rendered into cards, and media."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ApiError("That file is not a valid .apkg (zip) package.")
    names = set(z.namelist())
    colname = "collection.anki21" if "collection.anki21" in names else "collection.anki2" if "collection.anki2" in names else None
    if colname is None or ("collection.anki21b" in names and colname == "collection.anki2"):
        raise ApiError("This package uses the newest export format. Export it again with "
                       "'Support older versions' (legacy export) ticked, then import that file.")
    tmpdir = tempfile.mkdtemp()
    try:
        path = os.path.join(tmpdir, "col.db")
        with open(path, "wb") as f:
            f.write(z.read(colname))
        src = sqlite3.connect(path)
        src.row_factory = sqlite3.Row
        col = src.execute("select models, decks from col").fetchone()
        models = json.loads(col["models"])
        decks = json.loads(col["decks"])
        media_map = {}
        if "media" in names:
            try:
                media_map = json.loads(z.read("media").decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                media_map = {}
        media_count = 0
        for key, fname in media_map.items():
            fname = safe_media_name(fname)
            if fname and key in names:
                with z.open(key) as srcf, open(os.path.join(MEDIA, fname), "wb") as dst:
                    shutil.copyfileobj(srcf, dst)
                media_count += 1

        now = int(time.time())
        st = {"added": 0, "updated": 0, "skipped": 0, "media": media_count}
        nt_ids = {}
        rows = src.execute("""select c.id cid, c.ord, c.did, c.odid, c.type, c.due, n.id nid, n.guid, n.mid, n.flds, n.tags
            from cards c join notes n on n.id=c.nid order by c.did, case when c.type=0 then c.due else 1e15 end, n.id, c.ord""").fetchall()
        deck_names = {}
        for r in rows:
            did = r["odid"] or r["did"]
            deck_names.setdefault(did, (decks.get(str(did)) or {}).get("name", "Imported"))
        rows = sorted(rows, key=lambda r: deck_names[r["odid"] or r["did"]].lower())
        pos = next_pos()
        db.execute("begin")
        try:
            for r in rows:
                m = models.get(str(r["mid"]))
                if not m:
                    st["skipped"] += 1
                    continue
                if str(r["mid"]) not in nt_ids:
                    ext_id = int(r["mid"]) % (2 ** 62)
                    db.execute("insert into notetypes(id, name, css) values(?,?,?) on conflict(id) do update set name=excluded.name, css=excluded.css",
                               (ext_id, m.get("name", "Imported"), m.get("css", "")))
                    nt_ids[str(r["mid"])] = ext_id
                vals = r["flds"].split("\x1f")
                fields = {f["name"]: (vals[i] if i < len(vals) else "") for i, f in enumerate(m["flds"])}
                is_cloze = m.get("type") == 1
                tmpls = m["tmpls"]
                t = tmpls[0] if is_cloze else (tmpls[r["ord"]] if r["ord"] < len(tmpls) else None)
                if t is None:
                    st["skipped"] += 1
                    continue
                deck = deck_names[r["odid"] or r["did"]]
                cord = r["ord"] + 1
                q = render_template(t["qfmt"], fields, "q", cord, tags=r["tags"], deck=deck)
                a = render_template(t["afmt"], fields, "a", cord, front=q, tags=r["tags"], deck=deck)
                first = vals[m.get("sortf", 0)] if m.get("sortf", 0) < len(vals) else vals[0]
                sort_text = strip_html(render_cloze(first, cord, "a") if is_cloze else first)
                upsert_card(f"{r['guid']}:{r['ord']}", ensure_deck(deck), nt_ids[str(r["mid"])], q, a,
                            norm_tags(r["tags"]), sort_text, pos, now, st)
                pos += 1
            db.execute("commit")
        except Exception:
            db.execute("rollback")
            raise
        src.close()
        return st
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


SEPARATORS = {"comma": ",", "semicolon": ";", "tab": "\t", "space": " ", "pipe": "|", "colon": ":"}


def import_csv(data, filename, deck_name=None):
    """Import a CSV/TSV/TXT file. Understands Anki's '#separator:', '#html:', '#columns:', '#deck:',
    '#tags column:' and '#deck column:' header lines; otherwise the separator is sniffed from the first line."""
    text = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines(keepends=True)
    headers, body_start = {}, 0
    for i, line in enumerate(lines):
        m = re.match(r"#([\w ]+):(.*)", line.strip())
        if not m:
            break
        headers[m.group(1).strip().lower()] = m.group(2).strip()
        body_start = i + 1
    body = "".join(lines[body_start:])
    sep = headers.get("separator")
    if sep:
        sep = SEPARATORS.get(sep.lower(), sep[:1])
    else:
        first = body.split("\n", 1)[0]
        sep = "\t" if "\t" in first else ";" if first.count(";") > first.count(",") else ","
    is_html = headers.get("html", "true" if re.search(r"<[a-zA-Z/][^>]*>", body) else "false").lower() == "true"
    cols = [c.strip().lower() for c in headers.get("columns", "").split(sep if sep != " " else None)] if headers.get("columns") else []
    tags_col = int(headers["tags column"]) - 1 if headers.get("tags column", "").isdigit() else (cols.index("tags") if "tags" in cols else None)
    deck_col = int(headers["deck column"]) - 1 if headers.get("deck column", "").isdigit() else (cols.index("deck") if "deck" in cols else None)
    default_deck = deck_name or headers.get("deck") or re.sub(r"[_]+", " ", os.path.splitext(os.path.basename(filename))[0]).strip() or "Imported"
    reserved = {tags_col, deck_col}
    content_cols = None
    now = int(time.time())
    st = {"added": 0, "updated": 0, "skipped": 0, "media": 0}
    pos = next_pos()
    css = ".card{font-family:-apple-system,system-ui,sans-serif;font-size:20px;line-height:1.45;text-align:left;padding:6px 10px}"
    db.execute("insert or ignore into notetypes(id, name, css) values(1, 'Basic (CSV)', ?)", (css,))
    db.execute("begin")
    try:
        for row in csv.reader(io.StringIO(body), delimiter=sep):
            if not any(x.strip() for x in row):
                continue
            if content_cols is None:
                content_cols = [i for i in range(len(row)) if i not in reserved]
            vals = [row[i] if i < len(row) else "" for i in content_cols]
            if len(vals) < 2 or not vals[0].strip():
                st["skipped"] += 1
                continue
            front, back = vals[0], vals[1]
            if not is_html:
                front, back = html.escape(front).replace("\n", "<br>"), html.escape(back).replace("\n", "<br>")
            deck = row[deck_col] if deck_col is not None and deck_col < len(row) and row[deck_col].strip() else default_deck
            tags = row[tags_col] if tags_col is not None and tags_col < len(row) else ""
            guid = "csv:" + hashlib.sha1((deck + "\x1f" + vals[0]).encode()).hexdigest()
            upsert_card(guid, ensure_deck(deck), 1, fix_media(front), fix_media(front) + '<hr id="answer">' + fix_media(back),
                        norm_tags(tags), strip_html(vals[0]), pos, now, st)
            pos += 1
        db.execute("commit")
    except Exception:
        db.execute("rollback")
        raise
    return st


def import_file(data, filename, deck_name=None):
    """Import an uploaded file, choosing the importer from the name and content."""
    low = filename.lower()
    if low.endswith(".colpkg"):
        raise ApiError("A .colpkg is a full Anki collection backup. Export decks as .apkg instead.")
    if low.endswith(".apkg") or data[:2] == b"PK":
        return import_apkg(data)
    return import_csv(data, filename, deck_name)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    """HTTP request handler: the JSON API under /api/, imported media under /media/, and the web app itself."""
    server_version = "Kardo/1.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        """Access log on stderr; set KARDO_LOG=0 to silence it."""
        if os.environ.get("KARDO_LOG", "1") != "0":
            super().log_message(fmt, *args)

    def send_json(self, obj, status=200):
        """Send a JSON response that is never cached."""
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        """Read the request body, refusing anything larger than MAX_UPLOAD."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            raise ApiError("file too large", 413)
        return self.rfile.read(n) if n else b""

    def tz(self):
        """The viewer's UTC offset in minutes (sent by the app), so 'today' matches their clock."""
        try:
            return max(-840, min(840, int(self.headers.get("X-TZ-Offset", ""))))
        except ValueError:
            return time.localtime().tm_gmtoff // 60

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_DELETE(self):
        self.route("DELETE")

    def route(self, method):
        """Dispatch a request to the API, the media folder or the static web app."""
        url = urlparse(self.path)
        path = url.path
        qs = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if path.startswith("/api/lab"):  # runs outside the lock so a slow query never blocks studying
                return self.lab_api(method, [p for p in path[8:].split("/") if p], qs)
            if path.startswith("/api/"):
                with lock:
                    return self.api(method, path[5:], qs)
            if method != "GET":
                raise ApiError("not found", 404)
            if path.startswith("/media/"):
                name = safe_media_name(unquote(path[7:]))
                return self.send_file(os.path.join(MEDIA, name) if name else "", cache=True)
            rel = os.path.normpath(unquote(path)).lstrip("/\\")
            full = os.path.join(STATIC, rel)
            if not rel or rel == "." or not os.path.isfile(full) or not os.path.abspath(full).startswith(STATIC):
                full = os.path.join(STATIC, "index.html")
            return self.send_file(full)
        except ApiError as e:
            self.send_json({"error": str(e)}, e.status)
        except lab.LabError as e:
            self.send_json({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # keep the server alive and tell the app what went wrong
            self.log_error("error: %r", e)
            self.send_json({"error": f"server error: {e}"}, 500)

    def lab_api(self, method, parts, qs):
        """SQL Lab endpoints under /api/lab."""
        if method == "GET" and not parts:
            return self.send_json(lab_overview())
        if method == "GET" and parts == ["schema"]:
            return self.send_json({"tables": lab.schema_info()})
        if method == "GET" and len(parts) == 2 and parts[0] == "ex":
            return self.send_json(lab_exercise(parts[1]))
        if method == "GET" and len(parts) == 3 and parts[0] == "ex" and parts[2] == "solution":
            return self.send_json({"solution": lab.get_exercise(parts[1])[1]["solution"]})
        if method == "GET" and len(parts) == 3 and parts[0] == "ex" and parts[2] == "expected":
            cols, rows = lab.expected(lab.get_exercise(parts[1])[1])
            return self.send_json({"columns": cols, "rows": [[lab.jsonable(v) for v in r] for r in rows[:lab.SHOW_ROWS]],
                                   "truncated": len(rows) > lab.SHOW_ROWS, "notes": [], "ms": 0})
        if method == "POST" and parts == ["run"]:
            b = json.loads(self.read_body() or b"{}")
            sql = str(b.get("sql") or "")
            ex = lab.get_exercise(b["ex"])[1] if b.get("ex") else None
            explain = bool(b.get("explain"))
            out = lab.run_for_display(sql, explain=explain, setup=ex["setup"] if ex else "",
                                      check=ex["check"] if ex and not explain else "")
            if ex and not explain:
                out["verdict"] = lab.check_answer(ex, sql)
                lab_record(ex["id"], sql, out["verdict"]["ok"], int(time.time()))
            return self.send_json(out)
        if method == "POST" and parts == ["reset"]:
            with lock:
                db.execute("delete from lab_progress")
            return self.send_json({"ok": True})
        raise ApiError("not found", 404)

    def send_file(self, full, cache=False):
        """Send a file from disk with a guessed content type."""
        if not full or not os.path.isfile(full):
            raise ApiError("not found", 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".webmanifest"):
            ctype = "application/manifest+json"
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400" if cache else "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def api(self, method, path, qs):
        """JSON API endpoints under /api/. Runs under the global lock, so database writes never interleave."""
        now = int(time.time())
        tz = self.tz()
        parts = [p for p in path.split("/") if p]
        deck = qs.get("deck") or None
        tag = qs.get("tag") or None

        if method == "GET" and parts == ["decks"]:
            return self.send_json({"decks": deck_tree(now, tz)})
        if method == "DELETE" and len(parts) == 2 and parts[0] == "decks":
            delete_deck(int(parts[1]))
            return self.send_json({"ok": True})
        if method == "GET" and parts == ["next"]:
            return self.send_json(next_card(deck, tag, now, tz))
        if method == "POST" and parts == ["answer"]:
            b = json.loads(self.read_body() or b"{}")
            answer_card(int(b["card_id"]), int(b["rating"]), b.get("elapsed_ms", 0), now, tz)
            return self.send_json(next_card(b.get("deck") or None, b.get("tag") or None, now, tz))
        if method == "POST" and parts == ["undo"]:
            b = json.loads(self.read_body() or b"{}")
            card = undo_last(now, tz)
            res = next_card(b.get("deck") or None, b.get("tag") or None, now, tz)
            res["card"] = card or res["card"]
            return self.send_json(res)
        if method == "GET" and parts == ["practice"]:
            where, params = card_filter(deck, tag)
            extra = ""
            if qs.get("only") == "struggling":
                extra = " and c.lapses>=1"
            elif qs.get("only") == "seen":
                extra = " and c.state!='new'"
            limit = max(1, min(500, int(qs.get("limit", 50))))
            rows = db.execute(f"select c.* from cards c where c.suspended=0 and {where}{extra} order by random() limit ?",
                              params + [limit]).fetchall()
            S = get_settings()
            ds = day_start(now, tz, S["rollover_hour"])
            return self.send_json({"cards": [card_payload(r, now, ds, S) for r in rows]})
        if method == "GET" and parts == ["tags"]:
            return self.send_json({"tags": all_tags()})
        if method == "GET" and parts == ["stats"]:
            return self.send_json(stats(int(deck) if deck else None, now, tz))
        if method == "GET" and parts == ["cards"]:
            return self.send_json(browse(qs.get("q", ""), deck, tag, qs.get("state", ""),
                                         max(1, min(500, int(qs.get("limit", 100)))), max(0, int(qs.get("offset", 0))), now, tz))
        if len(parts) == 2 and parts[0] == "cards":
            cid = int(parts[1])
            if method == "GET":
                row = db.execute("select * from cards where id=?", (cid,)).fetchone()
                if not row:
                    raise ApiError("card not found", 404)
                S = get_settings()
                return self.send_json(card_payload(row, now, day_start(now, tz, S["rollover_hour"]), S))
            if method == "POST":
                b = json.loads(self.read_body() or b"{}")
                card_action(cid, b.get("action"))
                return self.send_json({"ok": True})
        if parts == ["settings"]:
            if method == "POST":
                save_settings(json.loads(self.read_body() or b"{}"))
            return self.send_json(get_settings())
        if method == "POST" and parts == ["import"]:
            name = qs.get("filename", "upload.csv")
            data = self.read_body()
            if not data:
                raise ApiError("empty file")
            return self.send_json(import_file(data, name, qs.get("deck_name")))
        if method == "GET" and parts == ["backup"]:
            tmp = os.path.join(DATA, "backup-tmp.db")
            if os.path.exists(tmp):
                os.remove(tmp)
            db.execute("vacuum into ?", (tmp,))
            with open(tmp, "rb") as f:
                body = f.read()
            os.remove(tmp)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-sqlite3")
            self.send_header("Content-Disposition", f'attachment; filename="kardo-backup-{time.strftime("%Y%m%d")}.db"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if method == "GET" and parts == ["health"]:
            return self.send_json({"ok": True})
        raise ApiError("not found", 404)


# ---------------------------------------------------------------- SQL Lab

def lab_progress():
    """Solved/attempted state of every SQL Lab exercise, keyed by exercise id."""
    with lock:
        return {r["ex_id"]: dict(r) for r in db.execute("select * from lab_progress")}


def lab_record(ex_id, sql, ok, now):
    """Record an attempt at an exercise, keeping the first time it was solved."""
    with lock:
        db.execute("""insert into lab_progress(ex_id, attempts, solved_at, last_sql, updated) values (?, 1, ?, ?, ?)
                      on conflict(ex_id) do update set attempts = attempts + 1, last_sql = excluded.last_sql,
                      solved_at = coalesce(solved_at, excluded.solved_at), updated = excluded.updated""",
                   (ex_id, now if ok else None, sql[:lab.MAX_SQL], now))


def lab_overview():
    """Exercise list grouped by track, with progress, for the SQL Lab home screen."""
    prog = lab_progress()
    tracks = []
    for e in lab.exercises():
        if not tracks or tracks[-1]["name"] != e["track"]:
            tracks.append({"name": e["track"], "exercises": []})
        p = prog.get(e["id"], {})
        tracks[-1]["exercises"].append({"id": e["id"], "title": e["title"], "solved": bool(p.get("solved_at")),
                                        "tried": bool(p.get("attempts"))})
    total = sum(len(t["exercises"]) for t in tracks)
    solved = sum(x["solved"] for t in tracks for x in t["exercises"])
    return {"tracks": tracks, "total": total, "solved": solved, "sqlite": sqlite3.sqlite_version}


def lab_exercise(ex_id):
    """One exercise with its prompt, expected result shape, saved attempt and neighbours."""
    i, e = lab.get_exercise(ex_id)
    allx = lab.exercises()
    p = lab_progress().get(ex_id, {})
    cols, rows = lab.expected(e)
    return {"id": e["id"], "track": e["track"], "title": e["title"], "prompt": e["prompt"], "hint": e["hint"],
            "setup": e["setup"], "has_check": bool(e["check"]), "check": e["check"], "ordered": e["ordered"],
            "expected_columns": cols, "expected_rows": len(rows),
            "solved": bool(p.get("solved_at")), "attempts": p.get("attempts", 0), "last_sql": p.get("last_sql", ""),
            "prev": allx[i - 1]["id"] if i > 0 else None, "next": allx[i + 1]["id"] if i + 1 < len(allx) else None,
            "number": i + 1, "count": len(allx)}


def main():
    """Start the server, or import files from the command line: python server.py import deck.apkg [...]"""
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "import":  # python server.py import deck.apkg [more files]
        for p in sys.argv[2:]:
            with open(p, "rb") as f:
                print(p, import_file(f.read(), os.path.basename(p)))
        return
    srv, port = bind_server(PORT, explicit="PORT" in os.environ)
    if port != PORT:
        print(f"Port {PORT} is already in use, so Kardo picked {port} instead. "
              f"Set PORT to choose one yourself.", flush=True)
    print(f"Kardo listening on :{port}, data in {DATA}", flush=True)
    srv.serve_forever()


def port_in_use_message(port):
    """What to tell the user when the port is taken."""
    return (f"Kardo can't start: port {port} is already in use by another program (another Kardo, maybe?).\n"
            f"  Pick a free port with PORT, e.g.  PORT=8485 python3 server.py\n"
            f"  With Docker, keep the container port and change the host side instead:  -p 8485:8484")


class KardoServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind a port that is already in use,
    # which would hide the conflict, so it is only enabled elsewhere (for quick restarts).
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def bind_server(port, explicit=True, tries=20):
    """Open the HTTP server on `port`. If that port is taken and the user didn't ask for it
    explicitly, try the next few ports; otherwise exit with a clear message instead of a traceback."""
    for candidate in range(port, port + (1 if explicit else tries)):
        try:
            return KardoServer(("0.0.0.0", candidate), Handler), candidate
        except OSError as e:
            if e.errno not in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1), 10048):
                raise
    raise SystemExit(port_in_use_message(port))


if __name__ == "__main__":
    main()
