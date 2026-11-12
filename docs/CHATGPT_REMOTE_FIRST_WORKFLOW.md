# ChatGPT remote-first workflow for NEXUS

**Status:** proposed operating guide  
**Checked:** 2026-11-12  
**Scope:** keep the phone out of the critical path, use the Dell as the signed-in browser console, and send long-running work to a supported cloud executor when the account and task type permit it.

## The key distinction

A second ChatGPT client is not a second model worker.

- Keeping ChatGPT open in Brave on the Dell gives the user a stable, larger-screen client with the Dell's local RAM, keyboard, display, network path, and browser profile.
- The model's inference is a server-side service. Adding Dell RAM does not donate memory or compute to the hosted model, and keeping a normal Chat tab open is not a durable background job queue.
- Chat and Work/Codex are different execution modes. Use the mode intended for the job rather than assuming every normal Chat response can be detached and resumed like an agent task.

The desktop browser is still useful: keep the correct ChatGPT account signed in, pin the current thread, and use that thread from the Dell when the phone is unreliable. Chat histories sync across supported ChatGPT clients.

## Select the right execution mode

| Need | Use | What persists |
|---|---|---|
| Conversation, Q&A, analysis in a normal thread | Chat on web/desktop | The conversation history syncs. Do not treat the normal response turn as a guaranteed unattended worker. |
| Multi-step research or a finished document/report | ChatGPT Work, where available | Work is the agent experience for longer work and deliverables. Work on web/mobile runs in the cloud; task progress and results are reviewed in its chat. |
| Coding, tests, repository edits | Codex | Codex is for software development and technical tasks. |
| Coding task independent of the local PC | Codex Cloud, where eligible | Cloud tasks run on OpenAI-managed computers and can continue while the local computer sleeps. Prepare and publish a reusable environment on desktop/web first. |
| Known command, inventory, compilation or report | GitHub Actions / NEXUS Remote Engine | Workflow jobs run on hosted runners and publish artifacts. They are deterministic automation, not a general-purpose ChatGPT model. |
| Reminder, scheduled check, or supported event monitoring | ChatGPT Scheduled Tasks | A scheduled task runs separately and can send supported push/email notifications. It does not resume an arbitrary normal Chat response. |

### Plan and eligibility caveat

OpenAI's current documentation says:
- ChatGPT Work is available only on eligible plans/workspaces.
- Codex is included across ChatGPT plans, but Codex Cloud is not included with Free or Go; cloud access also depends on rollout and workspace permissions.
- Scheduled Tasks are available subject to account/app eligibility. Free supports a one-time task or a recurring task no more than once per day, with up to three active tasks; event-triggered Work tasks are not available on Free or Go.

Check the account's current feature picker and usage page rather than assuming a feature is enabled.

## Existing NEXUS infrastructure (already present)

This repository already has a remote-first skeleton. Do not create a duplicate repository merely to get started.

- `.devcontainer/devcontainer.json`: reusable Codespaces/devcontainer definition; requests 4 CPUs, 8 GB memory and 32 GB storage.
- `.github/workflows/nexus-cloud-engine.yml`: remote workflow with `health-check`, `process-data`, `compile-thesis`, `clean-artifacts`, `hf-job`, `gcloud-health`, `drive-index`, and `dashboard-publish` tasks, plus a weekly scheduled health check.
- `scripts/nexus_cloud_dispatch.ps1`: dispatches a task using GitHub CLI authentication.
- `scripts/nexus_control_plane.ps1`: local control surface for measurements, local repair, remote dispatch, Drive report and health bundle.
- `README.md`: documents Codespaces and Actions as the remote-first execution model.

GitHub Actions has historical successful runs for this workflow, including a scheduled run on 2026-06-29 and a manually dispatched run on 2026-04-28. This is evidence that the workflow has run before, not proof that every current secret, schedule or runner setting is still valid. Recheck the latest run before relying on it.

## Operating procedure

### A. Phone-free normal Chat

1. On the Dell, open Brave with the intended ChatGPT account.
2. Open the exact conversation URL, confirm the visible title and keep the tab pinned.
3. Submit a request from the Dell browser when possible. Once the message is submitted, the phone is no longer needed for that browser session.
4. Return to the same thread from the Dell. Check whether the assistant turn completed; if it did not, continue from the last visible point rather than assuming it kept running unattended.
5. Keep the Dell powered, connected and awake if the browser needs to remain immediately available. Its local resources improve client responsiveness, not the hosted model's inference speed.

### B. Longer multi-step research or deliverables

1. Use ChatGPT Work when the plan/workspace offers it.
2. State the deliverable, scope, evidence standard, files/apps it may use, and actions requiring approval.
3. Let Work execute in the cloud and review the written result in its Work conversation.
4. For a supported follow-up schedule or monitor, create a separate Scheduled Task and enable push/email/browser notifications as needed.
5. Do not use a Scheduled Task as a substitute for an arbitrary long-running answer in a regular Chat thread.

### C. Technical/repository work

1. Use Codex for code, scripts, tests and repository tasks.
2. Use Codex Cloud for unattended coding only when the account exposes cloud environments. Publish and test a reusable environment first.
3. Otherwise use the existing NEXUS GitHub Actions workflow for its listed deterministic tasks. Do not send private user archives, browser profiles, cookies, access tokens, or raw research corpora to a public repository or public Actions artifact.
4. Check workflow output/artifacts and validate results before merging or deploying.
5. No new API key, paid cloud resource, GitHub secret or paid runner is authorized by this guide. Obtain explicit approval before enabling a chargeable service or adding credentials.

## Current device constraints noted 2026-11-12

- Dell NEXUS is reachable through Desktop Commander; its root partition was measured at 98% used with about 442 MiB free. Its 234.5 GiB exFAT data partition had about 200 GiB free. Avoid new clones, package installs, model downloads or cache cleanups on the root partition until it has been inspected and safely relieved.
- Lenovo was offline in the latest Desktop Commander/Tailscale check.
- Moto G23 was offline in Tailscale at the latest check; SSH ports 22 and 8022 were unreachable. Reconnect Tailscale and start Termux `sshd -p 8022` locally before expecting remote Android diagnostics.
- The current ChatGPT thread was previously opened in Dell Brave and its window title was verified. Recheck the full conversation title after navigation; a generic `ChatGPT - Brave` title alone does not identify which conversation is active.

## Official references

- ChatGPT Work and Codex: https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex
- Using Codex with your ChatGPT plan: https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
- Using Codex Cloud: https://help.openai.com/en/articles/20001545-using-codex-cloud
- Scheduled Tasks in ChatGPT: https://help.openai.com/en/articles/10291617-scheduled-tasks-in-chatgpt
