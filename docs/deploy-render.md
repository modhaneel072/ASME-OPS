# Putting ASME Ops on the internet: the Render half

This guide takes you from nothing to a working ASME Ops backend that officers and
members can reach from any browser. It assumes you have never deployed anything
before. Every value you need to type or paste is written out in full.

**How ASME Ops is split.** The *screens* (the pages people click) are hosted by
Netlify. The *backend* (the program that stores parts, work orders, members and
purchase requests, plus the database it stores them in) is hosted by Render.
Netlify quietly forwards anything starting with `/api` to Render, so a member's
browser only ever sees one web address. This guide sets up the Render half and
then connects the two. The Netlify half is in
[`deploy-netlify.md`](deploy-netlify.md).

> **Two words you will see everywhere.**
> A **service** is one running program on Render. A **Blueprint** is Render
> reading the file `render.yaml` in this repository and creating all the
> services for you, instead of you filling in forms by hand.

**Roughly how long this takes:** 45–75 minutes the first time, most of which is
waiting for the first build to finish.

---

## Contents

1. [What this costs](#1-what-this-costs)
2. [Before you start](#2-before-you-start)
3. [Create a Render account](#3-create-a-render-account-5-minutes)
4. [Let Render see the GitHub repository](#4-let-render-see-the-github-repository-5-minutes)
5. [Deploy the Blueprint](#5-deploy-the-blueprint-10-minutes)
6. [Check every environment variable](#6-check-every-environment-variable-10-minutes)
7. [Watch the first deploy](#7-watch-the-first-deploy-5-15-minutes)
8. [Find your service address](#8-find-your-service-address-1-minute)
9. [If the database migration did not run](#9-if-the-database-migration-did-not-run)
10. [Sign in the first time and change the password](#10-sign-in-the-first-time-and-change-the-password-5-minutes)
11. [Connect Render and Netlify to each other](#11-connect-render-and-netlify-to-each-other-10-minutes)
12. [Confirm the whole chain works](#12-confirm-the-whole-chain-works-3-minutes)
13. [Every environment variable, explained](#13-every-environment-variable-explained)
14. [What breaks and how to tell](#14-what-breaks-and-how-to-tell)
15. [Before real chapter data goes in](#15-before-real-chapter-data-goes-in)
16. [Setting it up by hand instead of with the Blueprint](#16-setting-it-up-by-hand-instead-of-with-the-blueprint)
17. [Two known quirks to tell officers about](#17-two-known-quirks-to-tell-officers-about)

---

## 1. What this costs

There are two separate things you might pay for on Render: the **web service**
(the program) and the **database** (where the data lives). Netlify's free plan
covers the screens.

| Piece | Free option | What you give up | Paid option |
|---|---|---|---|
| Web service | **$0** — Render's Free instance type | Goes to sleep after 15 minutes with no visitors and takes about a minute to wake up on the next click. No permanent disk, so uploaded files are erased on every restart. No shell access. 750 free running-hours per month across your whole Render account — one always-on free service uses about 720 of them, so you cannot run two. | **About $7/month** — the Starter instance (0.5 CPU, 512 MB). Never sleeps, can have a disk for uploaded files. |
| Database | **$0** — Render's Free PostgreSQL | **Render deletes it.** Render's own documentation says a free database expires 30 days after you create it, and you then have 14 more days to move it onto a paid plan before the data is deleted. Free databases also have **no backups of any kind**. 1 GB of storage, and only one free database per Render account. | **About $6–7/month** — the Basic-256mb instance, 1 GB storage included. Nothing expires. Point-in-time restore for the last 3 days plus downloadable exports. |
| Screens (Netlify) | **$0** | Nothing that matters at chapter scale. | n/a |

Also documented by Render, if you ever grow past the basics: extra database
storage **$0.30 per GB per month**, a persistent disk for uploaded files
**$0.25 per GB per month**, outgoing traffic above the included amount
**$0.15 per GB**.

> **Confirm the two dollar figures yourself.** Render publishes compute prices
> only on <https://render.com/pricing>, and that page builds its price tables in
> your browser, so they could not be read while this guide was written. The
> "about $7" and "about $6–7" figures above are the widely reported ones. Open
> that page once and write down the real numbers for **Starter** (web service)
> and **Basic-256mb** (PostgreSQL) before you commit to paying.

### The recommendation, in one paragraph

**Start the web service on Free and the database on Basic-256mb (about $6–7 a
month).** The web service sleeping is an annoyance — a member waits a minute for
the first page of the day. The free database being deleted after 44 days is not
an annoyance, it is losing the chapter's parts list, work orders and purchase
requests in the middle of a semester, with no backup to fall back on. If the
chapter genuinely cannot spend anything at all, you can start the database on
Free too — but put the deletion date in your calendar on day one and treat
everything entered in that first month as test data.

---

## 2. Before you start

Have these ready:

- **The GitHub account that owns the repository** `modhaneel072/ASME-OPS`. You
  will sign in to Render with it.
- **A browser** and about an hour.
- **A place to write four things down.** A note on your phone is fine; a password
  manager is better. You will collect:
  1. your Render web address (looks like `https://asme-ops-api.onrender.com`)
  2. your Netlify web address (looks like `https://asme-ops.netlify.app`)
  3. the first administrator password you invent in step 6
  4. the date your free database expires, if you choose the free database
- **A credit card**, only if you chose a paid database in section 1. No card is
  needed to create the account or to use anything free.

You do **not** need to install anything on your computer, and you do not need to
touch the code.

> **One thing to check with whoever maintains the code, before you start.**
> Render and Netlify build from a *copy* of the repository on GitHub, so a file
> that exists only on somebody's laptop does not exist for them. Ask for this
> command to be run and for every line to print a path:
>
> ```bash
> git ls-files --error-unmatch render.yaml netlify.toml .python-version \
>   requirements-render.txt docs/deploy-render.md docs/deploy-netlify.md
> ```
>
> If `.python-version` is the one missing, the deploy still works but runs on a
> different Python than the packages were tested against — see the
> `PYTHON_VERSION` box in [section 13](#strongly-recommended) for what to set in
> the meantime. If a guide is missing, the copy you are reading is the only copy,
> and the emergency steps in [section 9](#9-if-the-database-migration-did-not-run)
> tell you to download a copy of the repository that would not contain it.

---

## 3. Create a Render account (5 minutes)

1. Go to <https://render.com>.
2. Click **Get Started** (or **Sign Up**).
3. Choose **GitHub** as the way to sign in, and sign in with the GitHub account
   that owns `modhaneel072/ASME-OPS`. Using the same account here saves you a
   separate linking step later.
4. Render will ask you to name a **workspace** (its word for "your account's
   space"). `ASME` is a fine name. The workspace plan you want is **Hobby**,
   which costs $0.
5. Confirm your e-mail address if Render sends you a message asking you to.

---

## 4. Let Render see the GitHub repository (5 minutes)

Render cannot deploy from a public repository address alone — it needs its
GitHub app installed, even for a public repository.

1. In the Render dashboard, click **New** in the top-right corner, then
   **Blueprint**.
2. The first time, Render shows a **Connect GitHub** button (or sends you
   straight to GitHub). Click it.
3. GitHub asks which repositories Render may access. Either choose **All
   repositories** or choose **Only select repositories** and pick
   **ASME-OPS**. Then click **Install** / **Approve**.
4. GitHub sends you back to Render, and the repository now appears in the list.

If the repository still does not appear, you are signed in to Render with a
different GitHub account than the one that owns it. Sign out of Render and sign
back in with the right one.

---

## 5. Deploy the Blueprint (10 minutes)

The file `render.yaml` at the top of this repository describes everything Render
should create. You do not edit it here; you just point Render at it.

1. In the Render dashboard, click **New** (top right), then **Blueprint**.
2. Find **ASME-OPS** in the repository list and click **Connect** next to it.
3. Render now asks for a few things:

   | Prompt | What it means | What to enter |
   |---|---|---|
   | **Blueprint Name** (or *Name*) | A label for this whole group of services. Only you see it. | `ASME Ops` |
   | **Branch** | Which line of the code to deploy. | `main` |
   | *Custom Blueprint path* (if shown) | Where the description file lives. | Leave it blank — the file is `render.yaml` at the repository root, which is the default. |

4. Render reads `render.yaml` and shows you **every resource it is about to
   create**. You should see **two**: a web service and a PostgreSQL database.

   > **If it shows only a web service and no database, stop.** The description
   > file is missing its database, and deploying now would put the chapter on a
   > throwaway database inside the container that is erased on every restart —
   > with no error message anywhere. Either have the repository owner add it to
   > `render.yaml`, or cancel and follow
   > [section 16](#16-setting-it-up-by-hand-instead-of-with-the-blueprint)
   > instead, which creates the database explicitly.

   > **Write down the web service name shown on this screen.** Your public
   > backend address will be `https://` + that name + `.onrender.com`. This guide
   > writes it as **`asme-ops-api`** and writes the database as
   > **`asme-ops-db`**, which is what `render.yaml` declares. If the screen shows
   > different names, use what you see — everywhere below that says
   > `asme-ops-api`, substitute your name.

5. On the same screen, Render asks you to type in the values it is not allowed to
   invent. As `render.yaml` stands today there are exactly **four**, and two of
   them (the two e-mail ones) may be left blank:

   | Prompt | What to enter |
   |---|---|
   | `ASME_PUBLIC_BASE_URL` | Your **Netlify** address, e.g. `https://asme-ops.netlify.app`. Do not have one yet? Type `https://example.invalid` for now and replace it in step 11. Never a path, never a trailing slash. |
   | `ASME_DEFAULT_ADMIN_PASSWORD` | **Required — do not leave this blank.** A long password you invent now: 16+ characters, letters, numbers and symbols. Write it down; it is how you sign in the first time. If you leave it empty the deploy fails on purpose, with `ASME_DEFAULT_ADMIN_PASSWORD` named in the log, because the value it would otherwise fall back to is printed in this public repository — which would hand an administrator login for the chapter's data to anyone who reads it. |
   | `ASME_SMTP_USER` | Leave blank for now. Section 15 turns e-mail on later. |
   | `ASME_SMTP_PASS` | Leave blank for now. It must be blank whenever `ASME_SMTP_USER` is blank — one without the other makes the app refuse to start. |

   If the screen asks for something not in this list, `render.yaml` has changed:
   look the name up in [section 13](#13-every-environment-variable-explained).
6. If Render shows a red list of validation errors instead of the resource list,
   the description file has a problem. Do not try to fix it in the browser —
   nothing on this screen is editable. Note the error text and have the
   repository owner correct `render.yaml`.
7. Click **Deploy Blueprint** (also seen as **Apply**).

Render now creates the database first and the web service second, and starts the
first build. **Do not close the page.** Move on to the next section while it
works.

---

## 6. Check every environment variable (10 minutes)

An **environment variable** is a setting you give the program without editing
code — a name and a value, like `ASME_ENV` = `production`.

Do this even though the Blueprint set most of them. It takes five minutes and it
is the single most common cause of a deploy that "worked" but has quietly lost
everyone's data.

1. In the Render dashboard, click your web service (**asme-ops-api**).
2. In the left-hand menu, click **Environment**.
3. Compare what you see against the table in
   [section 13](#13-every-environment-variable-explained). For anything missing,
   click **Add Environment Variable**, type the name in the left box and the
   value in the right box.
4. Click **Save Changes** at the bottom. Render will restart the service; that is
   normal and takes a couple of minutes.

The ones that must be right or nothing works:

| Name | Value |
|---|---|
| `ASME_ENV` | `production` |
| `ASME_SECRET_KEY` | Any long random value. If the Blueprint generated one, **leave it alone forever** — changing it signs every single person out and breaks every file-download link already sent. |
| `ASME_DATABASE_URL` | The database's connection address (see below). **Not** `DATABASE_URL` — this program does not read that name, and setting only that one leaves the chapter on a throwaway database that is erased on every restart. |
| `ASME_DEFAULT_ADMIN_PASSWORD` | A long password you invent now, at least 16 characters, letters + numbers + symbols. It cannot be left blank or set to `ChangeMe123!`: that value is written in this repository for anyone to read, so the app refuses to start with it and the log names the variable. |
| `ASME_DEFAULT_USER_PASSWORD` | Set for you by the Blueprint to a random value nobody needs to know. It is only used for accounts created by importing a roster file; those people get in through an invite link or "forgot password". If you are setting the service up by hand, type any long random value — this one cannot be blank or `ChangeMe123!` either. |

### Where `ASME_DATABASE_URL` comes from

If the Blueprint created the database, this variable is already filled in and
linked to it — you will see the database's name rather than a password. Leave it
exactly as it is and skip the rest of this section.

If it is missing, build it yourself:

1. In the Render dashboard, open your database (**asme-ops-db**).
2. Scroll to **Connections**. You will see **Internal Database URL** and
   **External Database URL**. Click the copy icon next to **Internal Database
   URL** — internal means the two services talk over Render's private network,
   which is faster and never exposes the database to the internet.

   > **The external address is switched off, on purpose.** `render.yaml` creates
   > the database with an empty **Access Control** list (`ipAllowList: []`), so
   > nothing outside Render can connect to it — not an attacker who finds the
   > connection string in an old note, and not you. Render's own default is the
   > opposite: a brand-new database accepts connections from **every address on
   > the internet**, with only the generated password in the way, which is not a
   > sensible place to keep a chapter's roster and purchase requests.
   >
   > What it costs you: the **External Database URL** will not work from your
   > laptop until you deliberately open it. To do that, open the database →
   > **Access Control** (some views call it *Connections → Access Control*) →
   > **Add Source**, enter your current IP address (Render offers your own
   > address in the box), do the work, then **delete that entry again**. You need
   > this for exactly two things: the free-instance migration in
   > [section 9](#9-if-the-database-migration-did-not-run) and downloading a
   > backup export. Everyday running never needs it.
3. Paste it into a note. It looks like:

   ```
   postgresql://asme_ops:LONGRANDOMPASSWORD@dpg-abc123xyz/asme_ops
   ```

4. Add `?sslmode=require` to the very end, so it reads:

   ```
   postgresql://asme_ops:LONGRANDOMPASSWORD@dpg-abc123xyz/asme_ops?sslmode=require
   ```

   The `?` and everything after it are required; they tell the program to insist
   on an encrypted connection. Change nothing before the `?`, and never retype
   the password — copy and paste it.
5. **Check the first word.** Prefer `postgresql://`. If your copied address
   starts with `postgres://` (no `ql`) the program rewrites it for you as it
   starts, so either form works — but the long form is what the rest of this
   guide shows, so adding the two missing letters keeps things matching.
6. Back on the web service, **Environment** → **Add Environment Variable** →
   name `ASME_DATABASE_URL`, value the full string ending in `?sslmode=require`
   → **Save Changes**.

---

## 7. Watch the first deploy (5-15 minutes)

1. On the web service page, click **Logs** in the left menu (some views call the
   tab **Events** / **Logs**; it is the scrolling black panel of text).
2. Render's own messages are the ones wrapped in arrows, like
   `==> Building...` and `==> Deploying...`. Everything else is your program
   talking.

**A successful first deploy looks like this, in this order:**

1. `==> Cloning from https://github.com/modhaneel072/ASME-OPS...`
2. A long stretch of `Collecting Flask`, `Downloading ...`, `Installing collected
   packages: ...`. This is the build installing the program's dependencies and is
   the slowest part — **3 to 10 minutes** on a first run, faster afterwards
   because Render caches it.
3. `==> Build successful`
4. Then these two lines from the program itself, which are the proof the database
   worked:

   ```
   schema: upgraded
   seed: {'users': 1}
   ```

   `schema: upgraded` means the database tables were created. `seed: {'users': 1}`
   means the first administrator account was created. On later deploys you will
   see `seed: {'users': 0}`, which is correct — it means it did not need to
   create anything.
5. Then the web server starting:

   ```
   [INFO] Starting gunicorn 23.0.0
   [INFO] Listening at: http://0.0.0.0:10000
   [INFO] Booting worker with pid: ...
   ```

6. Then Render's own line saying the service is live, and the status badge at the
   top of the page turning green and reading **Live**.

If you see `==> Build failed`, `Refusing to start with invalid configuration`, or
the deploy being cancelled after 15 minutes, jump to
[section 14](#14-what-breaks-and-how-to-tell).

---

## 8. Find your service address (1 minute)

On the web service page, directly under the service name at the top, Render shows
the public address with a copy icon next to it:

```
https://asme-ops-api.onrender.com
```

Copy it and write it down. This is what you will paste into Netlify in step 11.
It has no slash on the end.

**Test it right now**, before touching anything else. Open this in a browser —
your address with `/healthz` on the end:

```
https://asme-ops-api.onrender.com/healthz
```

You should see, in plain text on a white page:

```json
{"ok": true, "service": "asme-web", "status": "ok"}
```

(The three parts may appear in a different order. That is fine.) If you see that,
the program is running. It does **not** yet prove the database is working — the
`schema: upgraded` line in step 7 is what proves that.

If the page takes about a minute to appear, that is the free instance waking up
from sleep, not a fault.

---

## 9. If the database migration did not run

"Migration" means creating and updating the database tables. It normally runs
**by itself** at the start of every deploy, which is why you saw
`schema: upgraded` in the log. You only need this section if that line never
appeared.

**First, just redeploy.** Most of the time a transient failure fixes itself:

1. Web service page → **Manual Deploy** (top right) → **Deploy latest commit**.
2. Watch the log for `schema: upgraded`.

**If it still does not appear,** read the actual error in the log and match it
against the "migration fails" row in [section 14](#14-what-breaks-and-how-to-tell).

**To run it by hand — on a paid instance.** Paid instances have a **Shell** tab
in the left menu, which gives you a command prompt inside the running service.
Click it and type:

```
python manage.py upgrade
```

Press Enter and wait. It prints the same two lines, `schema:` and `seed:`.

**To run it by hand — on the free instance.** Free instances have no Shell tab;
Render does not offer one on the free plan. Run it from your own computer
against the database's *external* address instead. You need
[Python 3.13](https://www.python.org/downloads/) — the version named in the
repository's `.python-version` file, which is what the pinned package versions
are built for — and [Git](https://git-scm.com/downloads) installed.

**First, let your computer reach the database.** The database is closed to
everything outside Render (see the box in
[section 6](#where-asme_database_url-comes-from)). Open the database in the
Render dashboard → **Access Control** → **Add Source** → accept the IP address
Render offers (that is the address you are browsing from) → **Save**. Wait about
a minute. **Put a note on your hand to remove it when you are finished** — the
last step below is exactly that.

```bash
git clone https://github.com/modhaneel072/ASME-OPS.git
cd ASME-OPS
python -m venv .venv
.venv/Scripts/activate            # on macOS or Linux: source .venv/bin/activate
pip install -r requirements-render.txt

# Windows PowerShell — paste YOUR External Database URL, with ?sslmode=require
# on the end, and the SAME admin password you typed into the Render dashboard:
$env:ASME_DATABASE_URL="postgresql://...?sslmode=require"
$env:ASME_DEFAULT_ADMIN_PASSWORD="the password you typed into Render"

# macOS / Linux:
export ASME_DATABASE_URL="postgresql://...?sslmode=require"
export ASME_DEFAULT_ADMIN_PASSWORD="the password you typed into Render"

python manage.py upgrade
```

It first prints a block of lines beginning `config:` — including one that says
these settings *would* refuse to start on a hosting platform. That is expected
here and is not the error: your own computer is not the hosting platform, and a
migration does not serve any web pages. What you are looking for is the same two
lines the deploy log shows, at the end:

```
schema: upgraded
seed: {'users': 1}
```

(`seed: {'users': 0}` instead means the accounts were already there, which is
equally good news.)

Three things about that block, because this is the moment when a half-explained
command wastes an evening:

- Use the **External Database URL**, not the internal one — the internal one only
  works from inside Render. Find it on the database page under **Connections**.
- `ASME_DEFAULT_ADMIN_PASSWORD` is there because this command creates the first
  administrator account if one does not exist yet, and it refuses to create one
  with the password published in this repository. If the account already exists
  the value is never used, but setting it costs nothing and a missing one stops
  the command with a message naming it.
- You do **not** need to set `ASME_SECRET_KEY`, `ASME_UPLOADS_EPHEMERAL_OK` or
  `ASME_ENV` here. Those settings are about serving web pages, which this command
  does not do; run from your own computer it reports them and carries on. (If
  you set `ASME_ENV=production` by hand in this shell, it will insist on them —
  so do not.)

**When it has finished, close the door again:** Render dashboard → the database →
**Access Control** → delete the entry you added. Your laptop's address changes
anyway (a different café, a phone hotspot), so a leftover entry is not even
convenient — it is just an address you no longer control with a standing
invitation to your chapter's data.

---

## 10. Sign in the first time and change the password (5 minutes)

Your Netlify site is not connected yet, so sign in on the Render address for now.

1. Open `https://asme-ops-api.onrender.com/` in a browser. It sends you to
   `/app`, which shows the sign-in screen.
2. Sign in with:
   - **E-mail:** `admin@uiowa.edu` (unless you set `ASME_DEFAULT_ADMIN_EMAIL` to
     something else)
   - **Password:** the value you put in `ASME_DEFAULT_ADMIN_PASSWORD`
3. **Immediately** open your account menu and change your password to a new one
   only you know.

   This matters more than it looks. The environment variable is read *only* at the
   moment the account is first created, so changing the variable later does
   nothing to the live account. Changing it inside the app is the real change, and
   it also signs out every other session on that account.

4. Now go back to Render → your web service → **Environment**, and change
   `ASME_DEFAULT_ADMIN_PASSWORD` to a **different** long random value — not the
   password you just set, and not blank. Leaving your real password sitting in
   the dashboard means anyone who can see the Render settings can read it;
   blanking it makes it fall back to `ChangeMe123!`. Click **Save Changes**; the
   restart is harmless.

5. **Never change `ASME_DEFAULT_ADMIN_EMAIL` after this point.** Every deploy
   checks whether an account exists with exactly that address, and if one does
   not, it creates a fresh administrator using whatever
   `ASME_DEFAULT_ADMIN_PASSWORD` currently holds. Changing the e-mail later
   silently mints a second administrator account.

---

## 11. Connect Render and Netlify to each other (10 minutes)

Two addresses have to be told about each other. Get one wrong and everything
still *looks* deployed but nobody can sign in.

### 11a. Tell Netlify where the backend is

1. Open <https://app.netlify.com> and click your ASME Ops site.
2. Left menu → **Site configuration** → **Environment variables**.
3. Click **Add a variable** → **Add a single variable**.
4. **Key:** `ASME_API_ORIGIN`
   **Value:** your Render address with no path and no slash on the end:
   ```
   https://asme-ops-api.onrender.com
   ```
5. Click **Create variable** / **Save**.
6. Left menu → **Deploys** → **Trigger deploy** → **Clear cache and deploy
   site**. This rebuild is what actually wires the screens to the backend; the
   variable alone does nothing until the site is rebuilt. It takes 2–4 minutes.

> Why the rebuild matters: the forwarding rule that sends `/api` traffic to Render
> is written into the site *during the build*. Without this variable the site
> still deploys and looks perfect, and every sign-in fails with a network error —
> the only clue is one warning line buried in the Netlify build log.

### 11b. Tell Render where the people are

1. Netlify site page → copy your site address from the top of the **Site
   overview** page. It looks like `https://asme-ops.netlify.app`.
2. Render → your web service → **Environment** → find `ASME_PUBLIC_BASE_URL`
   (add it if it is not there).
3. **Value:** your **Netlify** address, no slash on the end:
   ```
   https://asme-ops.netlify.app
   ```
4. **Save Changes**.

> This must be the Netlify address, not the Render one, even though you are
> typing it into Render. It is the address that gets written into password-reset
> and invitation e-mails, and it has to be the address people's browsers are
> actually on. It must also be a bare address: no `/app`, no trailing `/`, no
> `?` — the program refuses to start if it has a path on it.

---

## 12. Confirm the whole chain works (3 minutes)

Three checks. Do all three, in order. If check 1 passes and check 2 fails, the
problem is on the Netlify side; if both pass and check 3 fails, the problem is in
the app or the database.

### Check 1 — the backend is alive

Open `https://asme-ops-api.onrender.com/healthz`

**Expected:** `{"ok": true, "service": "asme-web", "status": "ok"}`

*If the browser spins for up to a minute first, that is the free instance waking
up. If it never loads, the service is not running — see section 14.*

### Check 2 — Netlify is forwarding to the backend

Open `https://asme-ops.netlify.app/healthz` — your **Netlify** address this time,
with `/healthz` on the end.

**Expected:** exactly the same `{"ok": true, ...}` text as check 1.

*This is the single most useful test in the whole guide. Netlify has no such page
of its own, so seeing that text proves the forwarding rule was built and points at
the right place. If you get a Netlify "Page not found" instead, `ASME_API_ORIGIN`
is missing or wrong, or you did not rebuild the site — redo step 11a.*

### Check 3 — a real person can sign in and the data is really saved

1. Open `https://asme-ops.netlify.app` — it should land you on the sign-in
   screen.
2. Sign in with `admin@uiowa.edu` and your new password.
   **Expected:** the app loads, and both the Setup Center and the Work Orders
   list open without errors.
3. Create one throwaway record — a location called `Test Room` is easiest.
4. Go to Render → your web service → **Manual Deploy** → **Deploy latest
   commit**, and wait for the status badge to read **Live** again.
5. Sign in again and look for `Test Room`.

   **Expected:** it is still there.

   *This is the proof that the chapter's data lives in PostgreSQL and not in a
   temporary file that gets wiped. If `Test Room` is gone, `ASME_DATABASE_URL` is
   not set correctly — go back to section 6.*

Delete `Test Room` when you are done.

---

## 13. Every environment variable, explained

Set these on the **web service** in Render (**Environment** in the left menu).
Nothing in this table is a secret you have to invent except the two marked
"you invent it", and no real password should ever be written into a file in the
repository.

### Required — the deploy is broken without these

| Name | What it is for | Where the value comes from | Example |
|---|---|---|---|
| `ASME_ENV` | Turns on production behaviour: refuses unsafe settings, does not auto-migrate on every worker. | Type it. | `production` |
| `ASME_SECRET_KEY` | Signs session cookies and file-download links. | Let Render generate it (the Blueprint does). **Never change it afterwards.** | *(generated)* |
| `ASME_DATABASE_URL` | Where the data lives. | The database's **Internal Database URL**, plus `?sslmode=require`. Must start `postgresql://`, not `postgres://`. See [section 6](#where-asme_database_url-comes-from). | `postgresql://asme_ops:…@dpg-abc123/asme_ops?sslmode=require` |
| `ASME_PUBLIC_BASE_URL` | The address written into password-reset and invitation links. | Your **Netlify** site address. Bare origin only — no path, no trailing slash. | `https://asme-ops.netlify.app` |
| `ASME_DEFAULT_ADMIN_PASSWORD` | The password of the very first administrator account. | **You invent it** — 16+ characters. Rotate it after first sign-in (step 10). The app refuses to start if it is blank or left at `ChangeMe123!`, which is published in this repository. | *(you invent it)* |
| `ASME_DEFAULT_USER_PASSWORD` | The password given to accounts created by importing a roster file. | Generated for you by the Blueprint; nobody needs to know it. Type any long random value if you are setting the service up by hand. Blank or `ChangeMe123!` is refused, same as the one above. | *(generated)* |
| `ASME_UPLOADS_EPHEMERAL_OK` | Your written acknowledgement that files people attach are not kept. | Type `1` **on the free instance**, which has no permanent disk. **Leave it out entirely** if you added a paid disk — set `ASME_UPLOAD_ROOT` instead. One of the two is required: with neither, the app refuses to start and the log says so in full. | `1` |

### Strongly recommended

| Name | What it is for | Where the value comes from | Example |
|---|---|---|---|
| `ASME_SESSION_COOKIE_SECURE` | Sends the login cookie only over HTTPS. | Type `1`. Without it the setting depends on a Render-supplied variable this repository does not control. | `1` |
| `ASME_TRUSTED_PROXY_COUNT` | How many forwarding servers sit in front of the app, so it can tell one visitor from another for login rate-limiting and the audit trail. | Type `2` — browser → Netlify → Render. See the warning below. | `2` |
| `ASME_AUTO_MIGRATE` | Stops the app trying to change the database from inside every worker process. | Type `0`. | `0` |

> **About `PYTHON_VERSION`.** Render decides which Python to use in this order:
> a `PYTHON_VERSION` variable, then a `.python-version` file **in the branch it
> clones**, then its own current default — which changes over time and is
> already newer than the `3.13` this repository's pinned packages are tested
> against.
>
> So the file only helps if it is actually committed. Check it in one command,
> from a clone or checkout of the repository:
>
> ```bash
> git ls-files --error-unmatch .python-version
> ```
>
> If that prints `.python-version`, you are set: leave `PYTHON_VERSION` unset,
> and delete it if you find one in the dashboard. If it errors with *did not
> match any file*, the file exists only on somebody's laptop and Render is
> building without it — then **add `PYTHON_VERSION` = `3.13` on the Environment
> page** until the file is committed, and tell whoever maintains the repository
> to commit it (`git add .python-version`). Setting `PYTHON_VERSION` to an
> *older* Python than 3.13 is the one thing to avoid: the pinned packages have no
> ready-built copies for those, so the build tries to compile them and fails.

### Set for you by the Blueprint

These come from `render.yaml`, so after a Blueprint deploy they are already
there. Check them against this table if you set the service up by hand
([section 16](#16-setting-it-up-by-hand-instead-of-with-the-blueprint)), or if
you are chasing an odd symptom.

| Name | What it is for | Value | Safe to change? |
|---|---|---|---|
| `ASME_SESSION_COOKIE_SAMESITE` | How strictly the browser keeps the login cookie to this site. | `Lax` | Leave it. `None` additionally requires `ASME_SESSION_COOKIE_SECURE=1` or the app refuses to start. |
| `ASME_ADMIN_EMAILS` | Addresses treated as chapter administrators by the older parts of the app. Comma-separated. | `admin@uiowa.edu` | Yes — add officers' addresses as they take over. |
| `ASME_LOGIN_RATE_WINDOW_SECONDS` | How long the sign-in attempt count is remembered. | `900` (15 minutes) | Yes. |
| `ASME_LOGIN_RATE_MAX_ATTEMPTS` | Failed sign-ins allowed within that window before the account is made to wait. | `8` | Yes, but do not raise it far. |
| `ASME_STORAGE_BACKEND` | Where attachments are written. | `local` | No. `local` is the only one implemented; `s3` makes the app refuse to start. |
| `ASME_UPLOAD_MAX_MB` | Largest single file someone may attach. | `25` | Yes. |
| `ASME_OUTBOX_WORKER` | Runs background jobs (reset e-mails, overdue-work-order scans) inside the web service. | `1` | No, unless you add a separate paid worker service running `python manage.py worker`. Setting it to `0` with no such service stops the scheduled scans entirely. |
| `ASME_OUTBOX_POLL_SECONDS` | How often that background worker looks for something to do. | `15` | Yes. |
| `ASME_ONBOARDING_ENFORCE` | Whether new members are forced through the onboarding steps. | `0` (off) | Yes. |
| `ASME_OPS_POLL_SECONDS` | How often open screens check for other people's changes. | `15` | Yes. Minimum 3. |
| `ASME_DEFAULT_ADMIN_EMAIL` | The address of the first administrator. | `admin@uiowa.edu` | **No — see step 10.** It is pinned in `render.yaml` on purpose. |

> **About `ASME_TRUSTED_PROXY_COUNT = 2`.** Render does not document how many
> forwarding servers add their entry to the request, so 2 is a well-reasoned
> figure rather than a documented one, and it has one hole: a request sent
> straight to `https://asme-ops-api.onrender.com` skips Netlify, so its chain is
> one short and the sender can choose what address gets recorded. That is enough
> to pick a different rate-limit bucket or put a wrong address in an audit row —
> not enough to get past the per-account limit that actually stops password
> guessing. If you want certainty, ask whoever maintains the code to log the raw
> `X-Forwarded-For` header of one real request after the first deploy and confirm
> the count.

### Needed before people can reset their own passwords

Leave these unset at first. Set all four together when you are ready — see
[section 15](#15-before-real-chapter-data-goes-in).

| Name | What it is for | Where the value comes from | Example |
|---|---|---|---|
| `ASME_SMTP_HOST` | The mail server that sends reset e-mails. | Your mail provider. | `smtp.office365.com` |
| `ASME_SMTP_PORT` | The mail server's port number. | Your mail provider. Usually this. | `587` |
| `ASME_SMTP_USER` | The mailbox the messages come from. | Your mail provider. | `asme-ops@uiowa.edu` |
| `ASME_SMTP_PASS` | That mailbox's password or app password. | **You get it from your mail provider.** Type it into the Render dashboard only — never into a file in the repository. | *(from your provider)* |

`ASME_SMTP_USER` and `ASME_SMTP_PASS` must be set **together**; setting one
without the other makes the app refuse to start. Once both are set,
`ASME_PUBLIC_BASE_URL` becomes mandatory too, for the same reason.

### Optional

| Name | What it is for | Where the value comes from | Example |
|---|---|---|---|
| `ASME_UPLOAD_ROOT` | Where uploaded attachments are written. | Only set this if you added a paid persistent disk; use the disk's mount path. Setting it replaces `ASME_UPLOADS_EPHEMERAL_OK` — delete that one when you add this one. Must be an absolute path. | `/var/asme-uploads` |
| `ASME_APP_BOOT_TOKEN` | Signs everyone out on purpose. | Leave unset. Set it to any new random value only if you need to force every session to end — unlike changing the secret key, this does not break existing download links. | *(unset)* |

---

## 14. What breaks and how to tell

Find the symptom in the left column. The log lines are in **Logs** on the Render
web service page.

| Symptom | What you will see | What it actually means | What to do |
|---|---|---|---|
| **Build fails** | `==> Build failed` after a screen of `pip` output. Look for the last line before it that says `ERROR:`. | A dependency could not be installed — almost always because the Python version and the pinned package versions no longer match. | Find which Python the build used: the log's first lines say so. It should be 3.13. If it is not, follow the `PYTHON_VERSION` box in [section 13](#strongly-recommended) — usually the `.python-version` file is missing from the branch and the fix is `PYTHON_VERSION` = `3.13` on the Environment page. Then click **Manual Deploy** → **Clear build cache & deploy**, which forces a fresh install instead of reusing yesterday's. |
| **Migration fails** | Build succeeds, then the deploy stops. Log contains `column "is_joinable" is of type boolean but expression is of type integer` or `COALESCE types boolean and integer cannot be matched`. | A defect in one of the database setup steps that only PostgreSQL is strict enough to catch. **It was fixed in this repository**, so seeing it means Render is building an older commit. | Check **Settings** → **Branch** is `main`, then **Manual Deploy** → **Deploy latest commit**. If it persists on the newest commit, tell whoever maintains the code: in `migrations/versions/0002_launchpad_…py` the boolean columns must be written as `true` / `false`, not `1` / `0`. |
| **Migration fails, other error** | Build succeeds, then `sqlalchemy.exc.OperationalError` or `could not connect to server`. | The database address is wrong, or the database is in a different Render region from the web service so the internal address cannot reach it. | Recheck `ASME_DATABASE_URL` (section 6). Open the database page and the web service page and confirm both say the same **Region**. If they differ, use the **External Database URL** instead, or recreate one of them in the matching region. |
| **App refuses to start** | `RuntimeError: Refusing to start with invalid configuration:` followed by dashed lines. | The program checked its settings and found one it will not run with. | The dashed lines name the exact variable. The usual causes are a blank `ASME_DEFAULT_ADMIN_PASSWORD` (see the next row), a missing `ASME_SECRET_KEY`, and an `ASME_PUBLIC_BASE_URL` with a path or a trailing slash on it (`https://x.netlify.app/app` is wrong, `https://x.netlify.app` is right). |
| **App refuses to start, naming a password** | `- ASME_DEFAULT_ADMIN_PASSWORD is still 'ChangeMe123!' …` or `… is empty …`. | You left that Blueprint field blank, so the first administrator would have been created with a password printed in this public repository. This refusal is deliberate and is protecting the chapter's data. | **Environment** → set `ASME_DEFAULT_ADMIN_PASSWORD` to a long password you invent (16+ characters) → **Save Changes**. The same applies to `ASME_DEFAULT_USER_PASSWORD`, which the Blueprint normally generates for you: any long random value will do. |
| **A password reset e-mail never arrived** | The person says nothing came, and a few hours later every administrator gets a notification inside ASME Ops reading *A password reset e-mail could not be sent*, naming the address and the error. | ASME Ops retried for about four hours and the mail server refused every time — most often `ASME_SMTP_USER` / `ASME_SMTP_PASS` no longer valid after an officer handover, or the mailbox needing re-consent. | Reset that person's password for them from the people list so they are not stuck, then fix the mailbox settings and prove it with [section 15's](#15-before-real-chapter-data-goes-in) reset check. If no notification arrives either, e-mail was never configured at all — the screen says the mail was sent whether or not SMTP exists, which is the SMTP row of section 15. |
| **Health check fails** | Render cancels the deploy after 15 minutes and keeps serving the old version, or the status badge flips between **Live** and **Deploying**. | Render asks the service for `/healthz` every few seconds. If nothing answers within 15 minutes of a deploy, it gives up. Usually the program crashed at startup — scroll up in the log past the health-check noise to the first red error. | Fix whatever that first error is. If the log is genuinely clean, confirm the Health Check Path setting is exactly `/healthz` (**Settings** → **Health Check Path**). |
| **Sign-in page loads but sign-in returns 404** | The browser's network panel shows `404` on a `/api/v1/...` address, or the app says it cannot reach the server. | Netlify is not forwarding `/api` to Render. Either `ASME_API_ORIGIN` is unset or misspelled, or you set it but never rebuilt. | Run [check 2](#check-2--netlify-is-forwarding-to-the-backend). If it fails, redo step 11a including **Clear cache and deploy site**. |
| **Sign-in returns 401 / "invalid credentials"** | The app says the e-mail or password is wrong. | Either the password really is wrong, or the first administrator account was never created. | Look in the log for the first deploy's `seed:` line. `seed: {'users': 1}` means an account was created — so use `admin@uiowa.edu` and the exact `ASME_DEFAULT_ADMIN_PASSWORD` value, watching for a stray space at either end. `seed: {'users': 0}` on a brand-new database means the database was not empty and the account already existed. **Locked out with no way in?** As a last resort, change `ASME_DEFAULT_ADMIN_EMAIL` to an address nobody holds yet and redeploy: that mints a fresh administrator using the current `ASME_DEFAULT_ADMIN_PASSWORD`. The old administrator stays, so you then have two — sign in on the new one and deactivate the old one from the people list. This is the one situation in which changing that variable is the right move; step 10 warns against it because doing it *accidentally* is how a chapter ends up with an administrator account nobody remembers creating. |
| **Sign-in works but you are signed out again immediately** | You log in, click once, and land back on the sign-in screen. | `ASME_SECRET_KEY` changed, or `ASME_SESSION_COOKIE_SECURE` is on while you are browsing over plain `http://`. | Never change the secret key. Always use the `https://` address. |
| **First click of the day takes about a minute** | The page spins, then loads normally, and everything is fast afterwards. | Normal free-tier behaviour: the service sleeps after 15 minutes with no visitors and takes about a minute to wake. | Either accept it, or point a free uptime monitor at `https://<your-netlify-address>/healthz` every 10 minutes to keep it awake — but that burns through your 750 free monthly hours much faster. The real fix is the paid instance, which never sleeps. |
| **Background jobs seem stuck** | Someone requests a password reset and no e-mail arrives for a long time, then several arrive at once. | The background worker lives inside the web service, so it sleeps when the service sleeps. Any visit — including a health check — wakes it. | Same answer as the row above. |
| **Database full** | Writes start failing; the database page shows storage at or near its limit. | The free database is fixed at 1 GB and cannot be grown. A paid one can. | On a paid database: open it, **Settings**, raise **Storage**. Storage can only ever be increased, at $0.30 per GB per month. On the free database: there is no fix other than moving to a paid plan. |
| **Free database about to expire** | Render e-mails you, or the database page shows an expiry date. | Free databases are deleted 30 days after creation, with 14 more days of grace. | Upgrade it to **Basic-256mb** from the database's **Settings** page before the grace period ends, or export the data and accept the loss. Do not let this date pass unread. |
| **Uploaded files will not download** | An attachment row exists, the download button gives an error. | Free instances have no permanent disk, so uploaded files are erased on every restart while the database rows that point at them survive. | See the uploads decision in [section 15](#15-before-real-chapter-data-goes-in). |

---

## 15. Before real chapter data goes in

Work down this list. Until every box is ticked, treat whatever is in ASME Ops as
practice data you would not mind losing.

- [ ] **The administrator password is changed inside the app** (step 10), and
      `ASME_DEFAULT_ADMIN_PASSWORD` in Render has been rotated to a *different*
      value afterwards. Not blank: blank stops the next deploy dead, because the
      value it would fall back to is published in this repository.
- [ ] **`ASME_DEFAULT_ADMIN_EMAIL` will never be changed again.** Changing it
      creates a second administrator on the next deploy.
- [ ] **Password resets actually work.** Set `ASME_SMTP_HOST`, `ASME_SMTP_PORT`,
      `ASME_SMTP_USER` and `ASME_SMTP_PASS` together, and make sure
      `ASME_PUBLIC_BASE_URL` is the Netlify address. Then prove it: on
      `/app/auth/forgot-password`, ask for a reset on an address you can read, and
      confirm a message arrives with a link to
      `https://<your-netlify-address>/app/auth/reset-password#token=…`. Note the
      `#` — the token is deliberately after a `#` so it never lands in any
      server's access log. Until SMTP is set, nobody can reset their own
      password: the screen says the mail was sent, and nothing is sent.
      Invitations are different and do not need e-mail at all — the inviting
      administrator copies the invite link out of the dialog and sends it
      themselves.
- [ ] **Backups exist.** On a paid database, Render keeps a 3-day point-in-time
      restore automatically; that is not enough on its own, because a mistake
      nobody notices until Monday is already out of range. Once a semester — put
      it in your calendar — open the database, find the recovery/backup section
      (likely labelled **Recovery** or **Backups**; it is the page with a
      restore button and an export button), click the export button, and save the
      file to the chapter's shared drive. Downloading it from your own computer
      needs your address added to **Access Control** first, exactly as in
      [section 9](#9-if-the-database-migration-did-not-run) — add it, download,
      remove it. On the free database there are **no backups at all**, which is
      the main reason not to keep real data on it.
- [ ] **You have read the restore paragraph below, before you need it.**

**If you ever have to restore.** A Render point-in-time restore does not rewind
the database you have; it creates a **new database instance** with a **new
connection string**. The web service does not follow it on its own: `render.yaml`
links `ASME_DATABASE_URL` to the database named `asme-ops-db`, and that link
still points at the old one. So after any restore:

1. Open the **new** database → **Connections** → copy the **Internal Database
   URL** and add `?sslmode=require` to the end.
2. Web service → **Environment** → find `ASME_DATABASE_URL`. If it shows a link
   to the old database rather than a value, remove it and add a plain variable
   named `ASME_DATABASE_URL` with the string you just copied.
3. **Save Changes** and wait for the redeploy. Confirm `schema:` appears in the
   log and that you can sign in and see the restored data.
4. Set the new database's **Access Control** to match the old one (empty, unless
   you are mid-way through something that needs your own address).
5. Only then delete the old database, and not on the same day.

Restoring from the exported file instead (the semester export, or the only option
on the free plan) is the same shape: create a database, load the export into it
with `psql`, then repoint `ASME_DATABASE_URL` as above. If nobody in the chapter
has used `psql`, that is the moment to ask whoever maintains the code — a restore
attempted for the first time during an emergency is how the data gets lost twice.
- [ ] **You have decided about file attachments.** On the free instance,
      anything anyone uploads is erased on the next restart while the entry in
      the app survives and its download button breaks. Either tell officers not
      to attach files yet, or move the web service to the paid Starter instance,
      add a **Disk** (about $0.25 per GB per month) mounted at
      `/var/asme-uploads`, set `ASME_UPLOAD_ROOT` to `/var/asme-uploads` and
      **delete `ASME_UPLOADS_EPHEMERAL_OK`** — it is the acknowledgement that
      files are thrown away, and it no longer applies once there is a disk. If
      you do turn on attachments, back up the disk at the same time as the
      database — attachment records point at files by name, so a database
      restored on its own leaves every download broken.
- [ ] **You know who has administrator rights, and it is a short list.**
      Administrators can see and change everything, including other people's
      records and the audit trail. Sign in and review the people list; anyone who
      only needs to run their own project should be a team leader or a member, not
      an administrator. Write down who the administrators are and review it at
      each officer handover — the commonest way a chapter system goes wrong is
      graduated officers who still have full access.
- [ ] **If you chose the free database, its deletion date is in your calendar,**
      with a reminder two weeks before.
- [ ] **Someone other than you can get in.** Make one other current officer an
      administrator, and make sure the Render and Netlify accounts are not tied
      to an e-mail address you lose when you graduate.

---

## 16. Setting it up by hand instead of with the Blueprint

Use this only if the Blueprint screen showed validation errors, or you would
rather see every form. The result is the same.

**Create the database first.**

1. Render dashboard → **New** → **Postgres**.
2. **Name:** `asme-ops-db` · **Database:** `asme_ops` · **User:** `asme_ops` ·
   **Region:** `Ohio (US East)` — remember which region you picked ·
   **PostgreSQL Version:** leave the default.
3. **Instance Type:** `Basic-256mb` (recommended) or `Free` (read section 1
   first).
4. Click **Create Database** and wait 1–2 minutes for the status to read
   **Available**.
5. **Close it to the internet.** Open the database → **Access Control**. A
   database created by hand starts out accepting connections from **every
   address on the internet** (Render's default, `0.0.0.0/0`), which the Blueprint
   avoids with `ipAllowList: []`. Delete every entry you find there, leaving the
   list empty. The web service connects over Render's private network and does
   not need any of them; see the box in
   [section 6](#where-asme_database_url-comes-from) for how to let your own
   computer in for an evening when you need to.
6. Copy the **Internal Database URL** from **Connections** and add
   `?sslmode=require` to the end, as in [section 6](#where-asme_database_url-comes-from).

**Then create the web service.**

1. **New** → **Web Service** → connect `modhaneel072/ASME-OPS` → **Branch:**
   `main`.
2. **Region:** the **same region** as the database. This is not optional — the
   internal address only works within one region.
3. **Language / Runtime:** `Python 3`. The version should come from the
   repository's `.python-version` file (`3.13`) — check that file is committed
   and add `PYTHON_VERSION` = `3.13` if it is not, as explained in the
   `PYTHON_VERSION` box in [section 13](#strongly-recommended).
4. **Build Command** — paste exactly:
   ```
   pip install --upgrade pip && pip install -r requirements-render.txt
   ```
5. **Start Command** — paste exactly:
   ```
   python manage.py upgrade && gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app
   ```
   The `--bind 0.0.0.0:$PORT` part is required: without it the web server listens
   somewhere Render cannot reach and the deploy fails with a port-detection
   error. One worker with four threads is the right shape for a free 512 MB
   instance and avoids two copies of the background scheduler running at once.
6. **Health Check Path** — paste exactly:
   ```
   /healthz
   ```
7. **Instance Type:** `Free` or `Starter`.
8. Add every variable from [section 13](#13-every-environment-variable-explained)
   **before** clicking create — the first start will refuse otherwise.
9. Click **Create Web Service**, then continue from
   [section 7](#7-watch-the-first-deploy-5-15-minutes).

> **A note on the pre-deploy command.** Render has a **Pre-Deploy Command** field
> under **Settings** → **Build & Deploy**, which would be a tidier place to run
> `python manage.py upgrade` than the start command. It is only available on paid
> instances. On the free instance the start command is the only option, which is
> why it is written that way above. If you move to a paid instance later, move
> `python manage.py upgrade` into the Pre-Deploy Command field and shorten the
> start command to the `gunicorn …` part alone — a failed migration then fails
> the deploy cleanly instead of taking the running site down with it.

---

## 17. Two known quirks to tell officers about

Neither of these stops the platform working, and neither is something you can fix
from the Render dashboard — they are in the code, written down here so that the
first officer who meets one knows it is known rather than spending an evening on
it. Both are worth passing to whoever maintains the code; each has a one-line
fix.

**1. A milestone is marked "missed" at 7pm on the evening it is due.**
Render's servers run on UTC, which is five hours ahead of Iowa City in term time
(six in the winter). The hourly scan that marks overdue milestones uses the
server's calendar date, so as soon as it is midnight in London, a milestone due
"today" in Iowa is treated as yesterday's. You will see the project screen and
the change feed say *missed its due date* while the team is still in the shop
working on it, and nothing puts the status back afterwards — an officer has to
set it back to *in progress* by hand.

*What to tell officers:* a milestone due Tuesday is really due Tuesday; if it
flips on Tuesday evening, ignore it or set it back. *The fix, for the code
maintainer:* `asme/ops/services/scans.py::_mark_missed_milestones` computes
`today = now.date()` from a UTC instant; it should use the organization's own
timezone, which the reporting screens already do through
`asme.ops.services.dashboard.org_timezone` — `today = now.astimezone(org_timezone(ctx.org)).date()`.

**2. Password reset can lock out the whole chapter for fifteen minutes.**
Everyone on campus wifi reaches ASME Ops from the same university address, and
the reset-password endpoint counts failed attempts per address only. Eight
expired or already-used reset links clicked from campus inside fifteen minutes —
which is an ordinary afternoon after an officer mails invite links to a dozen new
members — and every other member on campus gets *Too many password reset
attempts. Try again later.* for the rest of the window, **including people
holding a perfectly good link**.

*What to tell officers:* if several people report that message at once, it is not
their link; wait fifteen minutes and try again, or reset the password for them
from the people list. Raising `ASME_LOGIN_RATE_MAX_ATTEMPTS` (say to `20`) makes
it much rarer, at the cost of allowing more sign-in guesses per account per
window — a fair trade at chapter scale, but it is a trade. *The fix, for the code
maintainer:* `asme/blueprints/ops/auth.py::reset_password` passes the client
address as both key components (`counter = ip`), which collapses the limiter's
two counters into one bucket for the entire campus; the second counter should
identify the link or the person (`change_password` in the same file already does
this correctly), and a request carrying a valid, unused, unexpired token should
be looked up before the address block is applied.

---

## Where to go next

- The Netlify half, including custom domains: [`deploy-netlify.md`](deploy-netlify.md)
- What every setting does, backups, uploads and background work in more depth:
  [`deployment.md`](deployment.md)
