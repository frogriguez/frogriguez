# Setup guide

## Step 1 — Create the profile repo

On GitHub, create a new **public** repository named exactly `frogriguez`
(same as your username). Initialize it with a README. This is your profile repo.

## Step 2 — Add files to the repo

Copy the contents of this folder into that repo:

```
.github/workflows/update-stats.yml
scripts/collect_stats.py
scripts/render_readme.py
README.md          ← replace the auto-generated one
stats.json         ← seed file; will be overwritten by the Action
```

## Step 3 — Create a Personal Access Token (classic)

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
2. Click **Generate new token (classic)**
3. Set expiry to **1 year** (reminder: rotate annually)
4. Grant these scopes:
   - `repo` (full — needed to read private repo contents and commit data)
   - `read:org` (needed to list org repos)
   - `read:user`
5. Copy the token — you will not see it again

## Step 4 — Allow the PAT in each org

For each of your 4 organizations (you need admin access, which you have):

1. Go to **org → Settings → Personal access tokens → Settings**
2. Set **"Allow access via fine-grained personal access tokens"** or
   **"Allow access via personal access tokens (classic)"** → enabled
3. If **Token access policy** is set to "Require approval", either:
   - Switch it to "Allow", or
   - Approve your own token after adding it in Step 5

## Step 5 — Add repo secrets

In your `frogriguez/frogriguez` repo:
**Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `GH_STATS_TOKEN` | The PAT you created in Step 3 |
| `GH_USERNAME` | `frogriguez` |
| `GH_ORGS` | `org1,org2,org3,org4` (your actual org names, comma-separated) |

## Step 6 — Run the workflow

Go to **Actions → Update contribution stats → Run workflow**.

The first run takes ~5–20 minutes depending on how many repos are in your orgs
(each commit's diff stats requires one API call per commit — the script is
rate-limit-aware and will wait automatically).

After it completes, check:
- `stats.json` has been committed with real data
- `README.md` has the `<!-- STATS_START -->` section filled in

## Step 7 — Customize the README bio

Edit `README.md` and update:
- Your name and title
- The skills/stack badges (add/remove from https://shields.io or https://simpleicons.org)
- Any pinned projects you want to call out by name

## Ongoing maintenance

- The workflow runs **every Monday at 03:00 UTC** automatically
- Rotate your PAT before it expires (GitHub sends an email reminder)
- If a new org is added, update the `GH_ORGS` secret

## Rate limit notes

The GitHub API allows 5,000 requests/hour for authenticated requests.
With 4 orgs and typical clinical bioinformatics repo counts (~10–50 repos),
a full run uses roughly 200–2,000 API calls. If you hit the limit mid-run,
the script will sleep until the reset window and continue automatically.
