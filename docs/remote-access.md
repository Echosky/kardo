# Remote access and installing on your phone

Kardo has no login, so the goal is to reach it from your phone **without** opening it to the internet.

## Option 1: Tailscale (recommended)

[Tailscale](https://tailscale.com) puts your server and phone on a private network. It's free for personal use.

1. Install Tailscale on the server (Unraid 7: Settings → Tailscale; Synology and TrueNAS have packages;
   Linux: `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`).
2. Install the Tailscale app on your phone and sign in with the same account.
3. On the phone, open `http://<server-name>:8484`, for example `http://kestrel:8484`. The name (and the
   `100.x.y.z` address) is listed in the Tailscale app.

### HTTPS with Tailscale Serve

```sh
tailscale serve --bg 8484
```

Kardo is then available at `https://<server-name>.<your-tailnet>.ts.net`, with a valid certificate, still only
inside your tailnet. HTTPS lets the app register its service worker, so it opens instantly. Turn it off with
`tailscale serve --https=443 off`.

## Option 2: a reverse proxy you already run

Any proxy works; Kardo needs nothing special (no websockets). Put authentication in front of it.

**Caddy**

```caddyfile
cards.example.com {
    basic_auth {
        me <hash from `caddy hash-password`>
    }
    reverse_proxy kardo:8484
}
```

**Nginx**

```nginx
location / {
    proxy_pass http://127.0.0.1:8484;
    client_max_body_size 300m;   # big decks with media
    auth_basic "Kardo";
    auth_basic_user_file /etc/nginx/kardo.htpasswd;
}
```

Raise the upload limit (`client_max_body_size` in Nginx, *Custom Nginx configuration* in Nginx Proxy Manager)
or large `.apkg` imports will fail with a 413.

**Cloudflare Tunnel**: publish the service and protect the hostname with a Cloudflare Access policy.

> [!NOTE]
> iOS Home Screen apps keep their own cookies. With basic auth or an SSO proxy you'll sign in once inside the
> installed app.

## Installing the app

### iPhone and iPad (Safari)

1. Open Kardo's address in **Safari**.
2. Tap **Share** (the square with an arrow) → **Add to Home Screen** → **Add**.
3. Launch Kardo from the icon. It opens full-screen without browser bars.

### Android (Chrome)

1. Open Kardo's address in **Chrome**.
2. Tap **⋮** → **Install app** or **Add to Home screen**.

### Desktop

Chrome and Edge show an install icon in the address bar. Or just keep a tab open: keyboard shortcuts are
<kbd>Space</kbd> (flip, then Good), <kbd>1</kbd>–<kbd>4</kbd> (grade) and <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>Z</kbd> (undo).

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Can't reach the server" in the app | Is Tailscale (or your VPN) on? Can you open the address in the phone's browser? |
| Works on Wi-Fi, not on mobile data | You're using the LAN IP. Use the Tailscale name or address instead |
| Import fails with 413 | Raise your proxy's upload size limit |
| Home Screen app shows an old version | Close it fully and reopen. Over HTTPS the service worker refreshes on next launch |
