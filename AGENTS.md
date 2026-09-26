# Harbor Agent Infra development notes

This repository is the thin control plane described in the handoff document.

- Harbor owns Job/Trial scheduling, retry, cancellation, Docker lifecycle, logs and cleanup.
- The VGB package is used directly from a host-side isolated runtime.
- Do not import `benchmarking.*` from the legacy workspace.
- Do not put VGB private scoring data, provider secrets, or mutable image tags in tracked files.
- Keep tests separated into provider-free unit/contract tests and Docker/Registry integration tests.

Use Python 3.12 and the locked uv environment for repository commands.

Keep each commit focused on one small feature or module, and commit changes in implementation dependency order.
