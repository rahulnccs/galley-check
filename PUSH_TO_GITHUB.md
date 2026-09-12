# Putting this on GitHub

One-time setup, about ten minutes. Everything below runs in Terminal from inside
this folder.

## 1. Create the empty repository

On github.com, click **New repository**. Name it `galley-check`, set it to
**Public**, and do **not** tick "Add a README" — this folder already has one.

## 2. Replace USERNAME

Three files contain the placeholder `USERNAME`. Swap in your GitHub username:

```bash
grep -rl USERNAME README.md CITATION.cff | xargs sed -i '' 's/USERNAME/your-username/g'
```

(On Linux, drop the `''` after `-i`.)

## 3. Push it

```bash
git init
git add .
git commit -m "Galley: figure, table, citation and reference checks"
git branch -M main
git remote add origin https://github.com/your-username/galley-check.git
git push -u origin main
```

If Git asks for a password, use a personal access token, not your account
password: GitHub → Settings → Developer settings → Personal access tokens →
Tokens (classic) → Generate new token, with the **repo** scope ticked.

## 4. Watch the first build

Open the **Actions** tab on your repository. Two workflows run:

- **Tests** — runs the test suite on Mac, Windows, and Linux.
- **Build apps** — builds the Mac `.dmg` and Windows installer.

The first run takes about ten minutes. If a build fails, the log shows which
step; send it to me and I'll fix it.

## 5. Publish the first release

```bash
git tag v0.2.0
git push origin v0.2.0
```

This rebuilds both apps and attaches them to a release. The links on your
repository's releases page are what you give to other people — they download one
file and double-click it, with no Python involved.

## Later: updating

```bash
git add -A
git commit -m "what changed"
git push
```

For a new release, bump the version in `pyproject.toml`, `CITATION.cff`, and
`packaging/installer.iss`, then tag it as in step 5.
