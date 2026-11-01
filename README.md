# kellypage.app

The website for **Kelly Page**, free software for hams: downloads, the Raspberry Pi image, Mesh Buddy, guides and tips.

Plain static HTML and CSS, no build step. Published to Cloudflare Pages with `python publish.py` (credentials from a local .env, never in this repo); the big downloads (release zips, the Pi image)
live on Cloudflare R2 at `downloads.kellypage.app`, and `latest.json` says which release is current.

- `index.html`, `download.html`, `raspberry-pi.html`, `mesh-buddy.html`, `guides.html`, `tips.html`, `about.html`
- `guides/` -- standalone guides (Pi, Mesh Buddy starter, shopping list)
- `app/` -- the current Kelly Page release, unzipped at deploy time (the demo, Mesh Buddy flashing, the manual)
- `latest.json` -- written by the release script; `js/latest.js` fills the download pages from it

Preview locally: `python -m http.server 8080` in this folder, then http://localhost:8080/.

MIT licence.
