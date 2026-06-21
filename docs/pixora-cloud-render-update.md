# Pixora Cloud Render Update Runbook

Use this file when the user says to update Render, Pixora Cloud, `pixora-cloud`, or the cloud dashboard.

## What This Means

Render deploys from the separate GitHub repository:

`https://github.com/bptworld/pixora-cloud.git`

In this local checkout, that repository is configured as the git remote named:

`cloud`

Do not push the local Pixora public repo `HEAD` directly to `cloud/main`. The public Pixora repo and `pixora-cloud` have different histories. A direct push of this repo's `HEAD` to `cloud/main` would overwrite the cloud deployment repo with the wrong tree.

## Required Workflow

1. Confirm the cloud remote exists:

```powershell
git remote -v
```

Expected remote:

```text
cloud   https://github.com/bptworld/pixora-cloud.git (fetch)
cloud   https://github.com/bptworld/pixora-cloud.git (push)
```

2. Fetch the cloud deployment branch:

```powershell
git fetch cloud main
```

3. Create a temporary worktree from `cloud/main`:

```powershell
if (Test-Path tmp\pixora-cloud-worktree) {
  git worktree remove tmp\pixora-cloud-worktree --force
}
git worktree add tmp\pixora-cloud-worktree cloud/main
```

4. Make cloud deployment edits inside:

```text
tmp\pixora-cloud-worktree
```

Typical files:

```text
cloud/render/index.html
cloud/render/mobile.html
cloud/render/app.py
cloud/render/graphics/registry.json
cloud/render/graphics/assets/*
```

For cloud card library work:

- Pixora Cloud does not install or remove card source files from the dashboard.
- All public registry cards should be available directly through `/api/cards`.
- Keep card add/remove controls focused on device decks, not on the Card Library itself.
- Do not reintroduce visible `Browse Cards`, `Install`, or card-library remove buttons in the cloud dashboard.
- `/api/addons/install` and `/api/addons/remove` may remain harmless compatibility no-ops, but they must not block users with local-only source-file errors.
- Card addon source is fetched or cached by the cloud renderer at render time. Bundle only the cloud-specific addon overrides/assets that Render must use immediately.

For cloud mobile work:

- `cloud/render/mobile.html` is the smartphone-first Render page.
- `cloud/render/app.py` must serve it with a `/mobile.html` route.
- `cloud/render/index.html` should include a dashboard entry point, usually a `Mobile` button that opens `/mobile.html`.
- Cloud mobile uses the same admin token convention as the Render dashboard: `localStorage.pixora.cloud.token` and `Authorization: Bearer <token>`.
- Pause/resume deck state is stored on queued cards as `disabled: true`; keep the cloud renderer preserving and skipping disabled cards.

5. Run relevant checks from the cloud worktree:

```powershell
python -m py_compile cloud\render\app.py
node -e "const fs=require('fs'); const html=fs.readFileSync('cloud/render/index.html','utf8'); const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]); scripts.forEach((s,i)=>{try{new Function(s)}catch(e){console.error('script',i,e.message); process.exitCode=1;}}); if(!process.exitCode) console.log('scripts ok');"
```

When `cloud/render/mobile.html` changes, validate both dashboard pages:

```powershell
node -e "const fs=require('fs'); for (const file of ['cloud/render/index.html','cloud/render/mobile.html']) { const html=fs.readFileSync(file,'utf8'); const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]); scripts.forEach((s,i)=>{try{new Function(s)}catch(e){console.error(file,'script',i,e.message); process.exitCode=1;}}); } if(!process.exitCode) console.log('scripts ok');"
```

For route verification, use FastAPI's test client from the worktree:

```powershell
@'
from fastapi.testclient import TestClient
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('cloud_render_app_test', Path('cloud/render/app.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
client = TestClient(module.app)
for path in ['/', '/mobile.html']:
    resp = client.get(path)
    print(path, resp.status_code)
'@ | python -
```

For card library verification, confirm the cloud API exposes the public registry and that install/remove are no-ops:

```powershell
@'
from fastapi.testclient import TestClient
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('cloud_render_app_test', Path('cloud/render/app.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
client = TestClient(module.app)
cards = client.get('/api/cards').json().get('cards', [])
ids = {card.get('id') for card in cards}
print('cards', len(cards), 'has_overhead', 'flights_overhead' in ids, 'has_launch', 'launch_countdown' in ids)
print('install_noop', client.post('/api/addons/install', json={'url': '/cards/addons/flights_overhead.py'}).json().get('ok'))
print('remove_noop', client.post('/api/addons/remove', json={'id': 'flights_overhead'}).json().get('ok'))
'@ | python -
```

6. Review the cloud-only diff:

```powershell
git status -sb
git diff --stat
git diff
```

7. Commit from the cloud worktree.

The local hooks are designed to protect the public Pixora repo and may reject cloud files. For the `pixora-cloud` worktree only, bypass those hooks with an empty hooks path:

```powershell
$noHooks = Join-Path (Get-Location) ".no-hooks"
New-Item -ItemType Directory -Force -Path $noHooks | Out-Null
git add cloud/render/index.html cloud/render/mobile.html cloud/render/app.py
git -c core.hooksPath=$noHooks commit -m "Short cloud deploy message"
```

Adjust the `git add` paths to the actual cloud files changed.

8. Push explicitly to `pixora-cloud/main` through the `cloud` remote:

```powershell
git -c core.hooksPath=$noHooks push cloud HEAD:main
```

9. Verify the remote head moved:

```powershell
git ls-remote --heads cloud main
```

10. Clean up the temporary worktree from the main Pixora checkout:

```powershell
cd C:\Pixora
git worktree remove tmp\pixora-cloud-worktree
```

## Final Response Checklist

Tell the user:

- the commit SHA pushed to `pixora-cloud/main`
- the commit message
- the validation commands that passed
- that Render should auto-deploy from the `pixora-cloud/main` push

## Important Rules

- Never run `git push cloud HEAD:main` from the normal `C:\Pixora` public repo checkout.
- Always use a worktree based on `cloud/main`.
- Always inspect the diff before committing.
- Only commit cloud deployment files from the temporary cloud worktree.
- Keep the cloud worktree temporary; remove it after a successful push.
