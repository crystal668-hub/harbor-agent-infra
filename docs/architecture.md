# Architecture

The control flow is:

```text
experiment config -> infra materializer -> Harbor Job/Trial -> agent adapter
                                                     |
                                                     +-> Harbor trial result
host-side VGB integration -> prompt/evaluation -> domain result projection
```

The Phase 1 materializer validates the external resource profile and immutable agent image
digest, locks Harbor's native OpenClaw npm version, records the agent Python/pip toolchain,
runs Docker capability preflight, and emits a native `JobConfig` snapshot. The locked agent
image contains the fixed chemistry baseline (RDKit 2025.09.6, NumPy 2.2.6, Pillow 11.3.0
and xTB 6.5.1); other third-party Python packages are deliberately agent-managed at Trial time.
Infra records identities and relationships. Harbor remains the lifecycle owner, and VGB
evaluation stays outside the agent container.

The Phase 3 OpenClaw adapter extends Harbor's installed adapter without replacing its
Node 22/npm installation path. Its additional contract
is limited to explicit session identity, per-trial state directory, OpenClaw 2026.6.9
`agents.list` projection,
configuration, evidence hashes and stable failure codes. Harbor still owns installation,
exec, logs, trajectory download and cleanup.

The agent image is built by `images/openclaw-agent/Dockerfile` from the locked Node base.
The Dockerfile installs Debian's Python 3 interpreter, pip, venv support, RDKit and xTB.
`PIP_BREAK_SYSTEM_PACKAGES=1` allows an agent-selected
`pip install` in the disposable container; agents may instead create a venv.

The Phase 4 VGB integration runs in a separate Python process selected by `VGB_PYTHON`.
It sends JSON requests to the official package's public `load_track`, `prompts`, `task`
and `evaluate_one` APIs. Prompt files contain only public task inputs; scoring output is
kept verbatim inside the projected domain result.
