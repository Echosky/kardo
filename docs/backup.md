# Backup and restore

Everything Kardo knows is in its data folder (`/data` in the container):

| Path | Contents |
|---|---|
| `kardo.db` | Decks, cards, note-type CSS, review history, settings, SQL Lab progress |
| `kardo.db-wal`, `kardo.db-shm` | SQLite's write-ahead log; part of the database while Kardo runs |
| `media/` | Images and audio from imported decks |

## Back up from the app

Settings → **Download a backup of all progress** downloads `kardo-backup-YYYYMMDD.db`. It's made with SQLite's
`VACUUM INTO`, so it's a consistent snapshot even while you study. It doesn't include `media/`; keep the original
`.apkg` files, or back up the folder as below.

## Back up the folder

The simplest complete backup is a copy of the data folder. To be safe while Kardo is running, take the database
through the API (consistent) and copy media alongside it:

```sh
#!/bin/sh
# kardo-backup.sh: run daily from cron or the Unraid User Scripts plugin
DEST=/mnt/user/backups/kardo/$(date +%Y-%m-%d)
mkdir -p "$DEST"
curl -fsS http://localhost:8484/api/backup -o "$DEST/kardo.db"
cp -r /mnt/user/appdata/kardo/media "$DEST/"
find /mnt/user/backups/kardo -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +   # keep 30 days
```

Or stop the container, copy the folder, and start it again. Appdata backup tools (like the Unraid *Appdata
Backup* plugin) do exactly that.

## Restore

1. Stop Kardo: `docker stop kardo`.
2. Replace `kardo.db` in the data folder with your backup, and delete any `kardo.db-wal` and `kardo.db-shm` next to it.
3. Put `media/` back if you backed it up.
4. Start Kardo: `docker start kardo`.

## Moving to a new server

Copy the whole data folder to the new machine, start Kardo there with the folder mounted at `/data`, and point your
phone at the new address. If the address changes, delete the old Home Screen icon and add the new one.
