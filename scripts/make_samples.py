#!/usr/bin/env python3
"""Build the sample decks in samples/ as real Anki .apkg packages.

The decks exercise the parts of the importer that matter most: subdecks, several
card templates per note, custom card CSS, images, tags and cloze deletions. They
are also what the README screenshots are taken with.

    pip install genanki pillow
    python scripts/make_samples.py

All content in these decks is original and released under the same license as Kardo.
"""
import os
import shutil
import tempfile

import genanki
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def model(mid, name, fields, templates, css="", cloze=False):
    return genanki.Model(
        mid, name,
        fields=[{"name": f} for f in fields],
        templates=[{"name": n, "qfmt": q, "afmt": a} for n, q, a in templates],
        css=css,
        model_type=genanki.Model.CLOZE if cloze else genanki.Model.FRONT_BACK,
    )


def write(decks, filename, media=()):
    os.makedirs(OUT, exist_ok=True)
    pkg = genanki.Package(decks)
    pkg.media_files = list(media)
    path = os.path.join(OUT, filename)
    pkg.write_to_file(path)
    print(f"{path}: {sum(len(d.notes) for d in decks)} notes")


# ---------------------------------------------------------------- flags and capitals

# (country, capital, continent, flag design)
H = "h"   # horizontal stripes, top to bottom
V = "v"   # vertical stripes, left to right
N = "n"   # Nordic cross: field, cross, optional inner cross
C = "c"   # disc on a field
F = "f"   # a ready-made image in scripts/assets, for flags too detailed to draw here
COUNTRIES = [
    ("France", "Paris", "Europe", (V, "#002654", "#ffffff", "#ce1126")),
    ("Italy", "Rome", "Europe", (V, "#008c45", "#f4f5f0", "#cd212a")),
    ("Ireland", "Dublin", "Europe", (V, "#169b62", "#ffffff", "#ff883e")),
    ("Belgium", "Brussels", "Europe", (V, "#000000", "#fdda24", "#ef3340")),
    ("Romania", "Bucharest", "Europe", (V, "#002b7f", "#fcd116", "#ce1126")),
    ("Germany", "Berlin", "Europe", (H, "#000000", "#dd0000", "#ffce00")),
    ("Netherlands", "Amsterdam", "Europe", (H, "#ae1c28", "#ffffff", "#21468b")),
    ("Austria", "Vienna", "Europe", (H, "#ed2939", "#ffffff", "#ed2939")),
    ("Hungary", "Budapest", "Europe", (H, "#ce2939", "#ffffff", "#477050")),
    ("Bulgaria", "Sofia", "Europe", (H, "#ffffff", "#00966e", "#d62612")),
    ("Estonia", "Tallinn", "Europe", (H, "#0072ce", "#000000", "#ffffff")),
    ("Lithuania", "Vilnius", "Europe", (H, "#fdb913", "#006a44", "#c1272d")),
    ("Poland", "Warsaw", "Europe", (H, "#ffffff", "#dc143c")),
    ("Ukraine", "Kyiv", "Europe", (H, "#0057b7", "#ffd700")),
    ("Sweden", "Stockholm", "Europe", (N, "#006aa7", "#fecc00")),
    ("Denmark", "Copenhagen", "Europe", (N, "#c8102e", "#ffffff")),
    ("Finland", "Helsinki", "Europe", (N, "#ffffff", "#002f6c")),
    ("Norway", "Oslo", "Europe", (N, "#ba0c2f", "#ffffff", "#00205b")),
    ("Iceland", "Reykjavík", "Europe", (N, "#02529c", "#ffffff", "#dc1e35")),
    ("Japan", "Tokyo", "Asia", (C, "#ffffff", "#bc002d")),
    ("Bangladesh", "Dhaka", "Asia", (C, "#006a4e", "#f42a41")),
    ("Indonesia", "Jakarta", "Asia", (H, "#ce1126", "#ffffff")),
    ("Yemen", "Sanaa", "Asia", (H, "#ce1126", "#ffffff", "#000000")),
    ("Nigeria", "Abuja", "Africa", (V, "#008751", "#ffffff", "#008751")),
    ("Guinea", "Conakry", "Africa", (V, "#ce1126", "#fcd116", "#009460")),
    ("Chad", "N'Djamena", "Africa", (V, "#002664", "#fecb00", "#c60c30")),
    ("Sierra Leone", "Freetown", "Africa", (H, "#1eb53a", "#ffffff", "#0072c6")),
    ("Gabon", "Libreville", "Africa", (H, "#009e60", "#fcd116", "#3a75c4")),
    ("Canada", "Ottawa", "North America", (F, "flag-canada.png")),
    ("Peru", "Lima", "South America", (V, "#d91023", "#ffffff", "#d91023")),
    ("Colombia", "Bogotá", "South America", (H, "#fcd116", "#fcd116", "#003893", "#ce1126")),
]


ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def draw_flag(design, path, w=600, h=400):
    kind, *cols = design
    if kind == F:  # keep the flag's own official proportions (Canada is 2:1)
        shutil.copyfile(os.path.join(ASSETS, cols[0]), path)
        return
    img = Image.new("RGB", (w, h), cols[0])
    d = ImageDraw.Draw(img)
    if kind == V:
        for i, c in enumerate(cols):
            d.rectangle([i * w // len(cols), 0, (i + 1) * w // len(cols), h], fill=c)
    elif kind == H:
        for i, c in enumerate(cols):
            d.rectangle([0, i * h // len(cols), w, (i + 1) * h // len(cols)], fill=c)
    elif kind == N:
        bar, x = h // 4, w * 5 // 16
        d.rectangle([x, 0, x + bar, h], fill=cols[1])
        d.rectangle([0, (h - bar) // 2, w, (h + bar) // 2], fill=cols[1])
        if len(cols) > 2:
            inner = bar // 2
            d.rectangle([x + (bar - inner) // 2, 0, x + (bar + inner) // 2, h], fill=cols[2])
            d.rectangle([0, (h - inner) // 2, w, (h + inner) // 2], fill=cols[2])
    elif kind == C:
        r = h * 3 // 10
        cx = w // 2 - (w // 20 if cols[0] != "#ffffff" else 0)
        d.ellipse([cx - r, h // 2 - r, cx + r, h // 2 + r], fill=cols[1])
    # thin frame so white flags stay visible on a white card
    d.rectangle([0, 0, w - 1, h - 1], outline="#d0d4da", width=2)
    img.save(path, optimize=True)


GEO_CSS = """
.card { font-family: -apple-system, system-ui, sans-serif; font-size: 22px; text-align: center;
        color: #1d2433; background: #ffffff; }
.nightMode .card, .card.nightMode { color: #e9edf3; background: #1b1e24; }
.flag img { width: 78%; max-width: 360px; }
.prompt { margin-top: 22px; font-size: 15px; letter-spacing: .08em; text-transform: uppercase; color: #7a8394; }
.answer { font-size: 34px; font-weight: 700; margin-top: 8px; }
.meta { display: inline-block; margin-top: 12px; padding: 4px 12px; border-radius: 999px;
        background: #eef2ff; color: #3949ab; font-size: 14px; font-weight: 600; }
.capital { font-size: 30px; font-weight: 700; color: #c2410c; }
"""


def geography(tmp):
    m = model(1607392301, "Kardo Sample: Country", ["Country", "Capital", "Continent", "Flag"], [
        ("Flag → Country",
         '<div class="flag">{{Flag}}</div><div class="prompt">Which country?</div>',
         '{{FrontSide}}<hr id="answer"><div class="answer">{{Country}}</div><div class="meta">{{Continent}}</div>'),
        ("Country → Capital",
         '<div class="prompt">Capital of</div><div class="answer">{{Country}}</div>',
         '{{FrontSide}}<hr id="answer"><div class="capital">{{Capital}}</div><div class="flag" style="margin-top:18px">{{Flag}}</div>'),
    ], GEO_CSS)
    deck = genanki.Deck(2059400110, "Geography::Flags & Capitals")
    media = []
    for country, capital, continent, design in COUNTRIES:
        fn = "kardo_flag_" + country.lower().replace(" ", "_").replace("'", "") + ".png"
        path = os.path.join(tmp, fn)
        draw_flag(design, path)
        media.append(path)
        deck.add_note(genanki.Note(m, [country, capital, continent, f'<img src="{fn}">'],
                                   tags=["geography", continent.lower().replace(" ", "_")],
                                   guid=genanki.guid_for("kardo-geo", country)))
    write([deck], "geography-flags-capitals.apkg", media)


# ---------------------------------------------------------------- Spanish vocabulary

SPANISH = [
    ("el perro", "the dog", "m", "El perro duerme en el sofá.", "animals"),
    ("el gato", "the cat", "m", "Mi gato es muy curioso.", "animals"),
    ("la casa", "the house", "f", "Vivimos en una casa pequeña.", "home"),
    ("la cocina", "the kitchen", "f", "La cocina huele a café.", "home"),
    ("la ventana", "the window", "f", "Abre la ventana, por favor.", "home"),
    ("el libro", "the book", "m", "Estoy leyendo un libro nuevo.", "everyday"),
    ("la llave", "the key", "f", "No encuentro la llave del coche.", "everyday"),
    ("el agua", "the water", "f", "El agua está fría.", "food"),
    ("el pan", "the bread", "m", "Compramos pan cada mañana.", "food"),
    ("la manzana", "the apple", "f", "Una manzana al día.", "food"),
    ("el queso", "the cheese", "m", "Este queso es de Manchego.", "food"),
    ("la playa", "the beach", "f", "Vamos a la playa el sábado.", "travel"),
    ("el billete", "the ticket", "m", "¿Dónde compro el billete?", "travel"),
    ("la estación", "the station", "f", "La estación está cerca.", "travel"),
    ("el aeropuerto", "the airport", "m", "Llegamos al aeropuerto a las seis.", "travel"),
    ("la calle", "the street", "f", "La calle está llena de gente.", "city"),
    ("el mercado", "the market", "m", "El mercado abre los domingos.", "city"),
    ("la ciudad", "the city", "f", "Madrid es una ciudad enorme.", "city"),
    ("el trabajo", "the work / job", "m", "Tengo mucho trabajo hoy.", "everyday"),
    ("la semana", "the week", "f", "Nos vemos la semana que viene.", "time"),
    ("el año", "the year", "m", "Este año quiero aprender español.", "time"),
    ("la mañana", "the morning", "f", "Corro por la mañana.", "time"),
    ("hablar", "to speak", "v", "¿Hablas inglés?", "verbs"),
    ("comer", "to eat", "v", "Comemos a las dos.", "verbs"),
    ("vivir", "to live", "v", "Vivo en Barcelona.", "verbs"),
    ("tener", "to have", "v", "Tengo dos hermanos.", "verbs"),
    ("ir", "to go", "v", "Voy al cine esta noche.", "verbs"),
    ("querer", "to want", "v", "Quiero un café con leche.", "verbs"),
    ("poder", "to be able to", "v", "¿Puedo pagar con tarjeta?", "verbs"),
    ("saber", "to know (a fact)", "v", "No sé dónde está.", "verbs"),
    ("conocer", "to know (a person)", "v", "¿Conoces a María?", "verbs"),
    ("rápido", "fast", "adj", "El tren es muy rápido.", "adjectives"),
    ("barato", "cheap", "adj", "Este restaurante es barato.", "adjectives"),
    ("cansado", "tired", "adj", "Estoy cansado después del viaje.", "adjectives"),
    ("feliz", "happy", "adj", "Ella está feliz hoy.", "adjectives"),
    ("lleno", "full", "adj", "El autobús está lleno.", "adjectives"),
]
GENDER = {"m": "masculine", "f": "feminine", "v": "verb", "adj": "adjective"}

ES_CSS = """
.card { font-family: Georgia, 'Times New Roman', serif; font-size: 21px; text-align: center;
        color: #2b2118; background: #fffaf2; }
.nightMode .card, .card.nightMode { color: #f3e9dc; background: #221c16; }
.word { font-size: 40px; font-weight: 700; margin: 18px 0 6px; }
.en { font-family: -apple-system, system-ui, sans-serif; font-size: 28px; color: #7c2d12; }
.pill { display: inline-block; font-family: -apple-system, system-ui, sans-serif; font-size: 13px; font-weight: 700;
        letter-spacing: .06em; text-transform: uppercase; padding: 4px 12px; border-radius: 999px; }
.pill.m { background: #dbeafe; color: #1d4ed8; } .pill.f { background: #fce7f3; color: #be185d; }
.pill.v { background: #dcfce7; color: #15803d; } .pill.adj { background: #fef3c7; color: #b45309; }
.ex { margin-top: 22px; font-style: italic; color: #6b5b4a; font-size: 19px; }
.dir { font-family: -apple-system, system-ui, sans-serif; font-size: 13px; color: #a8957f; letter-spacing: .1em;
       text-transform: uppercase; }
"""


def spanish():
    m = model(1607392302, "Kardo Sample: Vocabulary", ["Spanish", "English", "Kind", "KindLabel", "Example"], [
        ("Spanish → English",
         '<div class="dir">Español → English</div><div class="word">{{Spanish}}</div><span class="pill {{Kind}}">{{KindLabel}}</span>',
         '{{FrontSide}}<hr id="answer"><div class="en">{{English}}</div><div class="ex">{{Example}}</div>'),
        ("English → Spanish",
         '<div class="dir">English → Español</div><div class="word en">{{English}}</div>',
         '{{FrontSide}}<hr id="answer"><div class="word">{{Spanish}}</div><span class="pill {{Kind}}">{{KindLabel}}</span>'
         '<div class="ex">{{Example}}</div>'),
    ], ES_CSS)
    deck = genanki.Deck(2059400111, "Languages::Spanish::A1 Vocabulary")
    for es, en, kind, ex, topic in SPANISH:
        deck.add_note(genanki.Note(m, [es, en, kind, GENDER[kind], ex], tags=["spanish", topic],
                                   guid=genanki.guid_for("kardo-es", es)))
    write([deck], "spanish-a1-vocabulary.apkg")


# ---------------------------------------------------------------- Japanese hiragana

KANA = [
    ("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o"),
    ("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko"),
    ("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so"),
    ("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"), ("と", "to"),
    ("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no"),
    ("は", "ha"), ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho"),
    ("ま", "ma"), ("み", "mi"), ("む", "mu"), ("め", "me"), ("も", "mo"),
    ("や", "ya"), ("ゆ", "yu"), ("よ", "yo"),
    ("ら", "ra"), ("り", "ri"), ("る", "ru"), ("れ", "re"), ("ろ", "ro"),
    ("わ", "wa"), ("を", "wo"), ("ん", "n"),
]
KANA_EXAMPLES = {"あ": "あめ (ame) rain", "か": "かさ (kasa) umbrella", "さ": "さかな (sakana) fish",
                 "た": "たまご (tamago) egg", "な": "なつ (natsu) summer", "は": "はな (hana) flower",
                 "ま": "まど (mado) window", "や": "やま (yama) mountain", "ら": "らいねん (rainen) next year",
                 "ね": "ねこ (neko) cat", "み": "みず (mizu) water", "そ": "そら (sora) sky",
                 "き": "きのこ (kinoko) mushroom", "ふ": "ふゆ (fuyu) winter", "つ": "つき (tsuki) moon"}

JA_CSS = """
.card { font-family: 'Hiragino Sans', 'IPAGothic', 'Noto Sans JP', sans-serif; text-align: center;
        color: #f5f0ff; background: linear-gradient(160deg, #2a1f4a 0%, #3b1f3f 100%); min-height: 100%; }
.kana { font-size: 120px; line-height: 1.1; margin-top: 30px; text-shadow: 0 6px 24px rgba(0,0,0,.35); }
.row { font-family: -apple-system, system-ui, sans-serif; font-size: 13px; letter-spacing: .14em;
       text-transform: uppercase; color: #c4b5fd; }
.romaji { font-family: -apple-system, system-ui, sans-serif; font-size: 44px; font-weight: 800; color: #fbbf24; }
.ex { margin-top: 16px; font-size: 20px; color: #e9d5ff; }
hr#answer { border: 0; height: 1px; background: rgba(255,255,255,.18); margin: 20px 10%; }
"""


def hiragana():
    m = model(1607392303, "Kardo Sample: Kana", ["Kana", "Romaji", "Row", "Example"], [
        ("Recognise",
         '<div class="row">{{Row}}</div><div class="kana">{{Kana}}</div>',
         '{{FrontSide}}<hr id="answer"><div class="romaji">{{Romaji}}</div>{{#Example}}<div class="ex">{{Example}}</div>{{/Example}}'),
    ], JA_CSS)
    deck = genanki.Deck(2059400112, "Languages::Japanese::Hiragana")
    for kana, romaji in KANA:
        row = {"a": "vowels", "n": "n"}.get(romaji, romaji[:-1] + "-row" if len(romaji) > 1 else "vowels")
        if romaji in ("shi", "chi", "tsu", "fu"):
            row = {"shi": "s-row", "chi": "t-row", "tsu": "t-row", "fu": "h-row"}[romaji]
        deck.add_note(genanki.Note(m, [kana, romaji, row, KANA_EXAMPLES.get(kana, "")],
                                   tags=["japanese", "hiragana"], guid=genanki.guid_for("kardo-ja", kana)))
    write([deck], "japanese-hiragana.apkg")


# ---------------------------------------------------------------- cell biology (cloze)

BIO = [
    ("The {{c1::mitochondrion}} produces most of the cell's {{c2::ATP}} through cellular respiration.", "organelles"),
    ("{{c1::Ribosomes}} translate messenger RNA into {{c2::proteins}}.", "organelles"),
    ("The {{c1::rough}} endoplasmic reticulum is studded with ribosomes; the {{c2::smooth}} ER makes lipids.", "organelles"),
    ("The {{c1::Golgi apparatus}} modifies, sorts and packages proteins for secretion.", "organelles"),
    ("{{c1::Lysosomes}} contain hydrolytic enzymes that break down waste and worn-out organelles.", "organelles"),
    ("Plant cells have a {{c1::cell wall}} made of {{c2::cellulose}} outside the plasma membrane.", "plant"),
    ("Photosynthesis takes place in the {{c1::chloroplasts}}, using the pigment {{c2::chlorophyll}}.", "plant"),
    ("The plasma membrane is a {{c1::phospholipid bilayer}} described by the {{c2::fluid mosaic}} model.", "membrane"),
    ("{{c1::Osmosis}} is the diffusion of {{c2::water}} across a selectively permeable membrane.", "membrane"),
    ("Moving a substance against its concentration gradient requires {{c1::active transport}} and energy from {{c2::ATP}}.", "membrane"),
    ("The sodium-potassium pump moves {{c1::3}} Na⁺ out and {{c2::2}} K⁺ into the cell per ATP.", "membrane"),
    ("DNA is copied during the {{c1::S}} phase of interphase.", "cell_cycle"),
    ("The four phases of mitosis are {{c1::prophase}}, {{c2::metaphase}}, {{c3::anaphase}} and {{c4::telophase}}.", "cell_cycle"),
    ("In {{c1::metaphase}}, chromosomes line up along the cell's equator.", "cell_cycle"),
    ("Meiosis produces {{c1::four}} genetically different {{c2::haploid}} cells.", "cell_cycle"),
    ("Crossing over between homologous chromosomes happens in {{c1::prophase I}} of meiosis.", "cell_cycle"),
    ("Prokaryotic cells have no {{c1::nucleus}}; their DNA sits in a region called the {{c2::nucleoid}}.", "cell_types"),
    ("Glycolysis takes place in the {{c1::cytoplasm}} and yields a net {{c2::2}} ATP per glucose.", "respiration"),
    ("The Krebs cycle runs in the mitochondrial {{c1::matrix}}.", "respiration"),
    ("The electron transport chain is located on the {{c1::inner mitochondrial membrane}}.", "respiration"),
    ("Enzymes speed up reactions by lowering the {{c1::activation energy}}.", "enzymes"),
    ("The region of an enzyme where the substrate binds is the {{c1::active site}}.", "enzymes"),
]

BIO_CSS = """
.card { font-family: -apple-system, system-ui, sans-serif; font-size: 22px; line-height: 1.55; text-align: left;
        color: #0f2b23; background: #f4fbf7; padding: 6px 4px; }
.nightMode .card, .card.nightMode { color: #d9f2e6; background: #11201b; }
.cloze { font-weight: 700; color: #047857; background: #d1fae5; padding: 1px 6px; border-radius: 6px; }
.nightMode .cloze { color: #6ee7b7; background: #064e3b; }
.topic { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: #059669; margin-bottom: 10px; }
.extra { margin-top: 18px; font-size: 16px; color: #557a6c; border-left: 3px solid #a7f3d0; padding-left: 10px; }
"""


def biology():
    m = model(1607392304, "Kardo Sample: Cloze", ["Text", "Topic"], [
        ("Cloze", '<div class="topic">{{Topic}}</div>{{cloze:Text}}',
         '<div class="topic">{{Topic}}</div>{{cloze:Text}}'),
    ], BIO_CSS, cloze=True)
    deck = genanki.Deck(2059400113, "Science::Cell Biology")
    for text, topic in BIO:
        deck.add_note(genanki.Note(m, [text, topic.replace("_", " ").title()], tags=["biology", topic],
                                   guid=genanki.guid_for("kardo-bio", text)))
    write([deck], "cell-biology-cloze.apkg")


# ---------------------------------------------------------------- git on the command line

GIT = [
    ("Create a new branch and switch to it", "git switch -c feature/login", "Older form: <code>git checkout -b feature/login</code>"),
    ("Show what changed but is not yet staged", "git diff", "Add <code>--staged</code> to see what is staged."),
    ("Stage only some hunks of a file, interactively", "git add -p app.py", ""),
    ("Undo the last commit but keep its changes staged", "git reset --soft HEAD~1", ""),
    ("Throw away local changes to one file", "git restore app.py", "Older form: <code>git checkout -- app.py</code>"),
    ("Unstage a file without losing the edits", "git restore --staged app.py", ""),
    ("Amend the last commit message", 'git commit --amend -m "Better message"', "Only before you push, or you rewrite shared history."),
    ("Temporarily shelve uncommitted work", "git stash push -m \"wip\"", "Bring it back with <code>git stash pop</code>."),
    ("Rebase the current branch onto the latest main", "git fetch origin\ngit rebase origin/main", ""),
    ("See a compact graph of all branches", "git log --oneline --graph --all", ""),
    ("Find which commit introduced a bug", "git bisect start\ngit bisect bad\ngit bisect good v1.4", ""),
    ("Show who last changed each line of a file", "git blame server.py", ""),
    ("Apply one commit from another branch", "git cherry-pick 3f2a91c", ""),
    ("Delete a local branch that has been merged", "git branch -d feature/login", "<code>-D</code> forces it."),
    ("Delete a branch on the remote", "git push origin --delete feature/login", ""),
    ("Push a new branch and set its upstream", "git push -u origin feature/login", ""),
    ("Create an annotated tag", 'git tag -a v1.0 -m "First release"', "Push tags with <code>git push --tags</code>."),
    ("Recover a commit you lost after a reset", "git reflog\ngit switch -c rescue 3f2a91c", ""),
    ("Revert a pushed commit safely", "git revert 3f2a91c", "Creates a new commit that undoes it."),
    ("List files git is ignoring", "git status --ignored", ""),
]

GIT_CSS = """
.card { font-family: -apple-system, system-ui, sans-serif; font-size: 20px; text-align: left; color: #e6edf3;
        background: #0d1117; padding: 4px; }
.q { font-size: 23px; font-weight: 650; line-height: 1.35; }
.label { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: #7d8590; margin-bottom: 8px; }
pre { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 14px 16px; font-size: 17px;
      font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace; color: #7ee787; white-space: pre-wrap; }
pre::before { content: "$ "; color: #6e7681; }
code { font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace; background: #161b22; color: #79c0ff;
       padding: 1px 5px; border-radius: 5px; font-size: 16px; }
.note { font-size: 16px; color: #8b949e; margin-top: 12px; }
hr#answer { border: 0; border-top: 1px solid #30363d; margin: 18px 0; }
"""


def git():
    m = model(1607392305, "Kardo Sample: Command", ["Task", "Command", "Note"], [
        ("Task → Command", '<div class="label">How do you…</div><div class="q">{{Task}}</div>',
         '{{FrontSide}}<hr id="answer"><pre>{{Command}}</pre>{{#Note}}<div class="note">{{Note}}</div>{{/Note}}'),
    ], GIT_CSS)
    deck = genanki.Deck(2059400114, "Developer::Git Essentials")
    for task, cmd, note in GIT:
        deck.add_note(genanki.Note(m, [task, cmd.replace("\n", "<br>"), note], tags=["git", "cli"],
                                   guid=genanki.guid_for("kardo-git", task)))
    write([deck], "git-essentials.apkg")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        geography(tmp)
        spanish()
        hiragana()
        biology()
        git()
