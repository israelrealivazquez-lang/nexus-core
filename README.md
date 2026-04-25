# NEXUS Remote-First Workspace

This repository is the light local anchor for NEXUS work. The Lenovo should stay lean: use `C:\Nexus_Core` as the local workspace, Google Drive as cloud-only storage, and GitHub Codespaces/GitHub Actions/CircleCI/Colab/Hugging Face for heavy compute.

Do not open or initialize repositories at `G:\` root. Google Drive may disappear or remount, and roots of virtual drives are fragile for Git and language servers.

## Local Rule

- Open Antigravity and Codex on `C:\Nexus_Core`, not `G:\`.
- Keep devcontainers remote through GitHub Codespaces.
- Do not install or depend on local Docker on this 4 GB RAM machine unless there is a separate maintenance window.
- Launch Antigravity in lite mode: local Docker, Python, Jupyter, Colab and duplicate ChatGPT extensions are disabled at boot; use cloud runners for that work.
- Keep corpus exports and cold material in Google Drive cloud-only.
- Run `scripts\nexus_remote_first_boot.ps1` after login or whenever Antigravity feels stuck.

## Remote Compute

- GitHub Codespaces: primary devcontainer runtime.
- GitHub Actions: remote inventory, thesis compilation, data processing and cleanup reports.
- CircleCI: secondary remote health runner.
- Google Colab: notebooks and experimental parsing outside the Lenovo.
- Hugging Face Jobs or Spaces: NLP, embeddings and corpus viewers.
- Cloudflare or Netlify: lightweight dashboards and APIs only, not local compute.

## Useful Commands

```powershell
.\scripts\nexus_remote_first_boot.ps1
```

```powershell
.\scripts\nexus_remote_first_boot.ps1 -LaunchAntigravity
```

```powershell
.\scripts\nexus_cloud_dispatch.ps1 -Task health-check
```

```powershell
.\scripts\nexus_control_plane.ps1 -Command full-health -RunRemote
```

```powershell
.\scripts\nexus_control_plane.ps1 -Command repair-local -Aggressive
```

```powershell
gh workflow run nexus-cloud-engine.yml --ref main -f task=health-check
```

```powershell
gh workflow run nexus-cloud-engine.yml --ref main -f task=process-data
```

```powershell
gh codespace list --limit 10
```

## Safety

- Do not commit credentials, browser profiles, cookies, exports, takeouts, vaults or raw corpus dumps.
- Keep Git remotes clean, without tokens embedded in the URL.
- Use GitHub CLI or Git Credential Manager for authentication.
- Treat `Credential_Vault`, `Data_Exports`, `Takeout_Processing`, `Cloud_Storage` and logs as local/private material.

## Control Plane

`scripts\nexus_control_plane.ps1` is the single cockpit for the remote-first mesh:

- `measure`: records RAM, CPU, disk, Drive, Docker, tools and top processes.
- `repair-local`: trims memory and clears old temp files; `-Aggressive` also closes Antigravity helpers so they can relaunch cleanly.
- `dispatch-github`: runs or lists GitHub Actions and Codespaces through `gh` keyring auth.
- `dispatch-hf`: records the Hugging Face remote-job policy without installing local heavy tooling.
- `dispatch-gcloud`: records local Google Cloud SDK auth/config status.
- `drive-report`: makes a shallow Drive report without recursively downloading streamed files.
- `full-health`: creates a complete evidence bundle under `logs\control_plane`.
