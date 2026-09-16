# Putting ASME Ops on the internet: the Netlify half

Netlify hosts the **screens** — the pages officers and members click. It does not
run the program that stores data; that lives on Render. This guide covers setting
the Netlify site up, the one setting you have to fill in, how to make the site
rebuild, where to find your address, and how to put a real chapter web address in
front of it later.

Do the Render half first: [`deploy-render.md`](deploy-render.md). You need the
Render address before this side can work.

**Roughly how long this takes:** 20 minutes, plus 3 minutes per rebuild.

---

## 1. What Netlify is doing here

Two jobs, and it is worth understanding the second one because almost every
"it deployed but nothing works" problem lives there.

1. **Serving the screens.** Netlify builds the React app in `apps/ops-web` into a
   folder of plain files and serves them. No Python runs on Netlify.
2. **Forwarding `/api` to Render.** When a screen needs data, it asks its *own*
   address for `/api/v1/...`. Netlify catches that and passes it through to
   Render behind the scenes. The browser only ever sees one web address.

That second job is not cosmetic. The sign-in cookie is only sent back to the
address that set it, so the screens and the data have to *look* like one site.
Calling Render directly from the browser would send no cookie and nothing would
work.

> **The database is not on this side, and it is closed.** Netlify never touches
> it; only the Render service does, over Render's private network. The Blueprint
> creates it with no public access at all (`ipAllowList: []` in `render.yaml`).
> What that costs you: you cannot connect to the chapter's database from your own
> laptop until you deliberately add your address on the database's **Access
> Control** page — and you should remove it again straight afterwards. See
> [`deploy-render.md` section 9](deploy-render.md#9-if-the-database-migration-did-not-run).

---

## 2. What is already in the repository

You do not type any of this into Netlify — Netlify reads it from `netlify.toml`
at the top of the repository. It is listed here so you recognise it on screen.

| Setting | Value | What it means |
|---|---|---|
| Build command | `npm ci --prefix apps/ops-web && npm run build:netlify --prefix apps/ops-web` | Installs the screen app's dependencies, compiles it, then writes the forwarding rules. |
| Publish directory | `netlify-dist` | The folder of finished files Netlify serves. |
| `NODE_VERSION` | `22` | Which Node.js the build uses. |
| `VITE_BASE_PATH` | `/` | The screens are served from the site root. |
| `VITE_OUT_DIR` | `../../netlify-dist` | Where the compiled files are written. |

The build also writes two files into the finished folder automatically:

- **`_redirects`** — the forwarding rules. `/api/*` and `/healthz` go to Render;
  `/app/*` is handed to the screen app's own router; `/` sends people to `/app/`.
- **`_headers`** — security headers, plus a rule that stops browsers caching the
  app shell.

> **A second copy of the screens exists and that is on purpose.** The folder
> `static/ops` in this repository is a separate build of the same app that the
> Render backend serves at `https://<render-address>/app`. Keep it. It is the
> emergency front door if Netlify is ever down, and one fallback link inside the
> program depends on it. **Advertise only the Netlify address to members.**

---

## 3. Create the Netlify site (10 minutes)

If a site already exists and you only need to set the API address, skip to
[section 4](#4-the-two-settings-that-connect-the-halves).

1. Go to <https://app.netlify.com> and sign up or sign in. Signing in with the
   same GitHub account that owns `modhaneel072/ASME-OPS` saves a step.
2. Click **Add new site** → **Import an existing project**.
3. Choose **GitHub** (labelled **Deploy with GitHub**). If Netlify asks to be
   installed on your GitHub account, approve it and grant access to **ASME-OPS**.
4. Pick the **ASME-OPS** repository from the list.
5. Netlify shows the build settings. **They are already filled in from
   `netlify.toml`** — the build command and publish directory should match the
   table above. Do not overwrite them. If the boxes are empty, type in the build
   command and publish directory from that table exactly.
6. **Branch to deploy:** `main`.
7. Before clicking deploy, click **Add environment variables** (it may be behind
   a link like *Add environment variables* or *Show advanced*) and add the one
   variable in [section 4](#4-the-two-settings-that-connect-the-halves). If you
   cannot find it on this screen, deploy anyway and add it afterwards — you will
   just have to rebuild once.
8. Click **Deploy** (**Deploy site** / **Deploy ASME-OPS**).

The first build takes 2–5 minutes. When it finishes, the site page shows a green
**Published** badge.

---

## 4. The two settings that connect the halves

Exactly two settings tie Netlify and Render together. One lives on each side.
Both must be a **bare web address**: starting with `https://`, no path, and no
slash on the end.

| Set on | Name | Value | Purpose |
|---|---|---|---|
| **Netlify** | `ASME_API_ORIGIN` | your **Render** address, e.g. `https://asme-ops-api.onrender.com` | Tells the screens where to forward `/api` requests. |
| **Render** | `ASME_PUBLIC_BASE_URL` | your **Netlify** address, e.g. `https://asme-ops.netlify.app` | Tells the backend what address to put in password-reset and invitation links. |

Note that each side is told about the *other* one. Getting these crossed over is
the most common mistake.

### Setting `ASME_API_ORIGIN` on Netlify

1. Netlify site page → left menu → **Site configuration** → **Environment
   variables**.
2. Click **Add a variable** → **Add a single variable**.
3. **Key:** `ASME_API_ORIGIN`
4. **Value:** your Render address, for example
   ```
   https://asme-ops-api.onrender.com
   ```
   No `/api` on the end. No trailing slash. It must be `https`, not `http` — the
   build stops with an error if it is not.
5. **Scopes / deploy contexts:** if Netlify offers a choice, leave it at *all
   scopes* / *all deploy contexts*. See [section 7](#7-deploy-previews) if you
   later want branch builds to talk to a different backend.
6. Click **Create variable**.
7. **Now rebuild** — see [section 5](#5-how-to-make-the-site-rebuild). The
   variable does nothing until the site is rebuilt.

> **Why the rebuild is not optional.** The forwarding rules are written into the
> finished site *during the build*, from this variable. If it is unset at build
> time, the site publishes perfectly, looks completely normal, and every single
> sign-in fails with a network error. The only warning is one line in the build
> log: `netlify-postbuild: ASME_API_ORIGIN is not set, so this deploy has no
> backend.` It is easy to miss and it is almost always the answer.

`ASME_PUBLIC_BASE_URL` is set on the Render side; step 11b of
[`deploy-render.md`](deploy-render.md) covers it.

---

## 5. How to make the site rebuild

Netlify rebuilds by itself every time someone pushes code to `main`. You have to
ask for a rebuild by hand in two cases: after changing an environment variable,
and when you want to be sure nothing stale is being reused.

1. Netlify site page → left menu → **Deploys**.
2. Click **Trigger deploy** (top right of the deploys list).
3. Choose **Clear cache and deploy site**.

   *Plain "Deploy site" reuses cached pieces from last time, which is faster.
   "Clear cache and deploy site" throws all that away and builds from scratch —
   slower, but it is what you want after changing a setting, and it is the fix
   whenever a change refuses to take effect.*

4. The new build appears at the top of the list. Click it to watch the log.

**What a good build looks like.** Near the end of the log:

```
netlify-postbuild: wrote _redirects (5 rules) and _headers into …/netlify-dist
```

Five rules means the two Render forwarding rules were written. **Three rules
means `ASME_API_ORIGIN` was not set** and the site has no backend. Then:

```
Site is live ✨
```

---

## 6. Finding your site address

1. Netlify site page → **Site overview** (the first thing you see).
2. The address is in large text near the top, with a copy icon. It looks like
   `https://fanciful-marzipan-1a2b3c.netlify.app` — Netlify invents a random
   name.
3. To change it to something people can read: **Site configuration** → **Site
   details** → **Change site name**. Type `asme-ops` and save, and the address
   becomes `https://asme-ops.netlify.app` (assuming nobody has taken it).

> **If you change the site name, you must update Render.** The address is what
> goes in `ASME_PUBLIC_BASE_URL` on the Render web service. Change it there too,
> or password-reset e-mails will point at an address that no longer exists.

---

## 7. Deploy previews

When someone opens a pull request, Netlify builds that branch to its own
temporary address. Those previews use the same `ASME_API_ORIGIN` as the live
site by default, which means **a preview writes to the real chapter database**.

For casual use that is usually fine and simpler to reason about. If you later set
up a separate test backend, point previews at it: **Site configuration** →
**Environment variables** → edit `ASME_API_ORIGIN` → set a **different value for
the `Deploy previews` and `Branch deploys` contexts**. `netlify.toml` already
keeps the rest of the preview build settings correct.

---

## 8. A real web address (custom domain), later

Nothing below is needed to go live. Do it when the chapter has a domain it wants
to use, for example `ops.asmeuiowa.org`.

1. **Get a domain.** If the chapter or the university already owns one, ask
   whoever manages it to create a subdomain for you — that is much cheaper than
   buying a new one and easier to hand over to next year's officers.
2. Netlify site page → **Domain management** → **Add a domain** → type the
   domain and click through.
3. Netlify tells you what to add at your domain provider. For a subdomain it is
   normally a **CNAME record** pointing at your Netlify address. Copy the exact
   value Netlify shows and give it to whoever manages the domain.
4. Wait. The change can take anywhere from minutes to a day to spread across the
   internet. Netlify's domain page shows the status.
5. Netlify issues an HTTPS certificate automatically once the domain points at
   it. You do not buy or install anything.
6. **Then update Render.** Change `ASME_PUBLIC_BASE_URL` on the Render web
   service to the new address, for example `https://ops.asmeuiowa.org`, with no
   trailing slash. Save; Render restarts.
7. Re-run the three checks in section 12 of [`deploy-render.md`](deploy-render.md)
   against the new address.

You do **not** need a custom domain on Render. The backend address is never
typed by a member; only Netlify talks to it.

---

## 9. What breaks on this side and how to tell

| Symptom | What it means | What to do |
|---|---|---|
| Build fails with `ASME_API_ORIGIN must be an https origin with no path` | The value has a path, a trailing slash, or starts with `http://`. | Fix it to a bare `https://…` address and redeploy. |
| Build log says `ASME_API_ORIGIN is not set, so this deploy has no backend` | The variable is missing, or it was added after this build started. | Add it, then **Clear cache and deploy site**. |
| Site loads, sign-in fails with a network error or a 404 | The forwarding rules are missing or point at the wrong backend. | Open `https://<your-netlify-address>/healthz`. It should return `{"ok": true, …}`. If you get a Netlify "Page not found", the rules are not there — redo section 4 and rebuild. |
| `/healthz` works but the app never loads past the sign-in screen | The backend is reachable but something is wrong on the Render side. | Go to section 14 of [`deploy-render.md`](deploy-render.md). |
| First sign-in of the day takes about a minute | The free Render backend was asleep. Netlify is fine. | Normal. See the cold-start row in `deploy-render.md`. |
| A page refresh inside the app gives "Page not found" | The rule that hands `/app/*` to the app's own router did not get written. | Check the build log for the `wrote _redirects` line and redeploy with the cache cleared. |
| Old screens keep appearing after a code change | The browser is holding the old files. | Hard-refresh (Ctrl+F5, or Cmd+Shift+R on a Mac). If it persists for everyone, **Clear cache and deploy site**. |

---

## 10. Checklist

- [ ] Site created from the `ASME-OPS` repository, deploying from `main`.
- [ ] Site renamed to something readable, and the address written down.
- [ ] `ASME_API_ORIGIN` on Netlify = the Render address, no trailing slash.
- [ ] `ASME_PUBLIC_BASE_URL` on Render = the Netlify address, no trailing slash.
- [ ] Rebuilt with **Clear cache and deploy site** after setting the variable.
- [ ] `https://<your-netlify-address>/healthz` returns `{"ok": true, …}`.
- [ ] You can sign in at the Netlify address and the Setup Center loads.
- [ ] The Netlify account is not tied to an e-mail address that disappears when
      the current officers graduate.
- [ ] `netlify.toml` and both deployment guides are **committed** to the branch
      Netlify builds — `git ls-files --error-unmatch netlify.toml
      docs/deploy-netlify.md docs/deploy-render.md` prints all three. Netlify and
      Render build a clone: a file that lives only in someone's working copy is
      not there, and next year's officers inherit a repository whose instructions
      exist on one laptop.
