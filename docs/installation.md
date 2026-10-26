# Installation

Kardo is one container (or one Python process) with one data folder. Pick whichever fits your setup.

- [Docker](#docker)
- [Docker Compose](#docker-compose)
- [Unraid](#unraid)
- [Synology, TrueNAS, Portainer and other Docker UIs](#synology-truenas-portainer-and-other-docker-uis)
- [Without Docker](#without-docker)
- [Updating](#updating)
- [Data folder permissions](#data-folder-permissions)
- [Port already in use](#port-already-in-use)

## Docker

```sh
docker run -d --name kardo --restart unless-stopped \
  -p 8484:8484 \
  -v /srv/kardo:/data \
  ghcr.io/echosky/kardo:latest
```

Open `http://<server>:8484`. The image is published for `linux/amd64` and `linux/arm64`.

To build the image yourself instead:

```sh
git clone https://github.com/Echosky/kardo && cd kardo
docker build -t kardo .
docker run -d --name kardo --restart unless-stopped -p 8484:8484 -v /srv/kardo:/data kardo
```

## Docker Compose

The repository includes a [`docker-compose.yml`](../docker-compose.yml):

```sh
mkdir kardo && cd kardo
curl -O https://raw.githubusercontent.com/Echosky/kardo/main/docker-compose.yml
docker compose up -d
```

Data goes to `./data` next to the compose file. See [permissions](#data-folder-permissions) if the container
can't write there.

## Unraid

### With the template (recommended)

1. In the Unraid terminal, fetch the template into your user templates:

   ```sh
   curl -o /boot/config/plugins/dockerMan/templates-user/my-kardo.xml \
     https://raw.githubusercontent.com/Echosky/kardo/main/unraid/kardo.xml
   ```

2. Go to **Docker → Add Container**, pick **kardo** from the *Template* list, check the port and the data path
   (`/mnt/user/appdata/kardo` by default) and click **Apply**.
3. Click the Kardo icon on the Docker tab → **WebUI**.

### From the terminal

```sh
mkdir -p /mnt/user/appdata/kardo && chown 99:100 /mnt/user/appdata/kardo
docker run -d --name kardo --restart unless-stopped \
  -p 8484:8484 -v /mnt/user/appdata/kardo:/data \
  ghcr.io/echosky/kardo:latest
```

The container runs as `nobody:users` (99:100), Unraid's standard, so files in `appdata` stay editable from
the share. Kardo appears on the Docker tab like any other container.

For phone access, Unraid 7 has Tailscale built in (Settings → Tailscale); older versions use the Tailscale
plugin. Then follow [remote access](remote-access.md).

## Synology, TrueNAS, Portainer and other Docker UIs

Create a container with:

| Setting | Value |
|---|---|
| Image | `ghcr.io/echosky/kardo:latest` |
| Port | container `8484` → any host port |
| Volume | a folder on your storage → `/data` |
| Restart policy | unless stopped |

If the container can't write its data folder, see [permissions](#data-folder-permissions).

## Without Docker

Python 3.10 or newer, nothing else:

```sh
git clone https://github.com/Echosky/kardo && cd kardo
KARDO_DATA=./data PORT=8484 python3 server.py
```

On Windows PowerShell:

```powershell
$env:KARDO_DATA = ".\data"; python server.py
```

To keep it running on Linux, a minimal systemd unit:

```ini
# /etc/systemd/system/kardo.service
[Unit]
Description=Kardo flashcards
After=network.target

[Service]
User=kardo
WorkingDirectory=/opt/kardo
Environment=KARDO_DATA=/var/lib/kardo PORT=8484
ExecStart=/usr/bin/python3 /opt/kardo/server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Updating

Your decks and progress live in the data folder, so updating never touches them.

```sh
docker pull ghcr.io/echosky/kardo:latest
docker rm -f kardo
docker run -d --name kardo --restart unless-stopped -p 8484:8484 -v /srv/kardo:/data ghcr.io/echosky/kardo:latest
```

With Compose: `docker compose pull && docker compose up -d`. On Unraid: Docker tab → *Check for updates* →
*Apply update*. Without Docker: `git pull` and restart the process.

The database schema is created automatically on first start.

## Data folder permissions

The image runs as uid 99, gid 100. If you mount a folder owned by another user, either:

```sh
sudo chown -R 99:100 /srv/kardo
```

or run the container as your own user with `--user 1000:1000` (Compose: `user: "1000:1000"`).

## Port already in use

Kardo checks its port when it starts.

- **Without Docker**, if you didn't set `PORT` and 8484 is taken, Kardo moves to the next free port (8485, 8486, …) and prints the one it chose. If you set `PORT` yourself and it's taken, Kardo stops and tells you, instead of quietly using another port.
- **With Docker**, the port inside the container is always free; a clash happens on the host side and Docker reports `port is already allocated`. Keep the container port and change the host one: `-p 8485:8484` (Compose: `"8485:8484"`).

To see what is using a port: `ss -ltnp | grep 8484` on Linux, `lsof -i :8484` on macOS, `netstat -ano | findstr 8484` on Windows.
