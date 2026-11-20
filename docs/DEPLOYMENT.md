# Deployment guide

This guide prepares Tritobol for a later deployment. It does not change DNS, Netlify, a VPS, or any production setting.

## What the application is

The web application is one Python process. Flask serves the HTML, CSS, and JavaScript, injects a per-process session token into the home page, and exposes the JSON API on the same origin. The optimizer is the `tritobol` package imported in-process. There is no separate frontend build and no database.

`npm run build` only checks that the static files and page sections are present. It does not produce a bundle to upload.

## Why this build does not go on Netlify

Netlify can host static files. It does not run this Flask application. The checked-in UI also cannot be split onto Netlify while the API stays on a VPS, for three reasons that are intentional in the current code:

1. `GET /` rewrites `__TRITOBOL_TOKEN__` in `index.html`. A static copy of that file does not contain a valid token, so `POST` requests are rejected.
2. `tritobol_app/server.py` answers only when the `Host` header is `localhost`, `127.0.0.1`, or `[::1]`.
3. `POST` requests with an `Origin` outside those same hosts are rejected.

A browser pointed at a public hostname, including a Netlify domain or an nginx site that forwards the public `Host`, receives HTTP 403. Do not work around that by publishing the Flask development server on `0.0.0.0`.

The repository homepage and the open pull requests already have Netlify preview comments. Those previews are not this Flask application. Leave that Netlify project as it is.

## Supported way to run it

On the machine where someone will use the app:

```bash
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
python -m pip install -r requirements-app.txt
python -m tritobol_app
```

macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install -r requirements-app.txt
python -m tritobol_app
```

The process binds to `127.0.0.1` only. If port 5000 is busy it tries the next ports, up to 19 above the one you asked for. Open the printed `http://127.0.0.1:<port>/` address. Stop it with Ctrl+C.

Useful flags: `--port 8080` and `--no-browser`.

Windows can also start it with `start.bat` from the project folder. The first run creates `.venv` and installs dependencies, which needs network access once.

## Environment

No API keys are required. The DeepSeek tokenizer JSON is bundled. Do not put secrets in the repository. Uploaded `tokenizer.json` files stay in memory for the life of the process.

The browser keeps settings and history in `localStorage` on that computer. A backup file is created only when the user exports one.

## HTTPS, reverse proxy, and a VPS

Use a VPS only for a future change that is not part of this tree. A safe shape, when that work is done on purpose, is:

- The Flask process still listens on `127.0.0.1` on the VPS.
- nginx (or Caddy) on the same machine is the only public listener.
- TLS certificates are issued on that proxy.
- The application is changed to accept one configured public host, and the browser is same-origin with that host so the session token and `Origin` check still apply.
- The proxy does not log request bodies.

Until that host allowlist exists, do not put nginx in front of this build and expect optimization requests to succeed. Local loopback HTTP is the privacy-preserving deployment: the traffic does not leave the computer, and the development server is not exposed on a network.

## Local-first behavior after deployment

Running the current application on a laptop keeps prompt processing on that computer. Statistics stay in the browser. Prompt text is stored only after the user confirms, and it is not written into the account database.

Accounts are local to this installation. Flask creates `tritobol_app/data/tritobol.sqlite` on first use, or uses the file in `TRITOBOL_DB`. Copy that file while the app is stopped to back it up. Set `TRITOBOL_COOKIE_SECURE=1` only when a reverse proxy serves the app over HTTPS. There is no external account service to configure. See `docs/AUTH.md`.

Putting the same process on a public VPS would move processing onto that server. That is a different privacy story and needs the host-allowlist work above plus a decision about logs, disk, and who can reach the port. This guide does not do that.
