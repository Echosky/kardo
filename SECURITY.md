# Security

## The threat model in one paragraph

Kardo is a single-user app meant to run on a network you control: your LAN, a Tailscale tailnet, or behind a
reverse proxy that does authentication. **It has no login of its own.** Anyone who can reach the port can study,
import, delete decks and download the backup. Do not expose it directly to the internet.

## What Kardo does to protect you

- The container runs as an unprivileged user (uid 99, gid 100) and only writes to `/data`.
- Media file names from imported packages are reduced to a base name, so a crafted `.apkg` cannot write outside the media folder. Static files are served only from the app folder.
- Card HTML is rendered inside a shadow DOM with the deck's CSS scoped to it. `<script>` elements in card HTML are not executed.
- The SQL Lab runs every query in a private in-memory copy of a practice database, with a time limit, a size limit, and an authorizer that blocks `ATTACH`, `load_extension` and non-read-only `PRAGMA`s. It never sees your flashcard database.
- No outbound network requests, analytics or third-party assets.

## Known limitations

- Inline HTML event attributes (for example `onerror` on an image) in imported cards are not stripped. Import decks only from sources you trust.
- There is no CSRF protection, which matters only if Kardo is reachable from a browser that also visits untrusted sites on the same network path. Keeping it on a private network or behind an authenticating proxy covers this.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** (Security tab → *Report a vulnerability*) rather than a
public issue. Include steps to reproduce and the version or commit. You'll get a response as soon as possible,
and credit in the release notes if you'd like it.
