# Architecture

The control flow is:

```text
experiment config -> infra materializer -> Harbor Job/Trial -> agent adapter
                                                     |
                                                     +-> Harbor trial result
host-side VGB integration -> prompt/evaluation -> domain result projection
```

The Phase 1 materializer validates the external resource profile and immutable agent base
image digest, locks Harbor's native OpenClaw npm version, runs Docker capability
preflight, and emits a native `JobConfig` snapshot.
Infra records identities and relationships. Harbor remains the lifecycle owner, and VGB
evaluation stays outside the agent container.

The Phase 3 OpenClaw adapter extends Harbor's installed adapter without replacing its
Node 22/npm installation path. Its additional contract
is limited to explicit session identity, per-trial state directory, keyed `agents.entries`
configuration, evidence hashes and stable failure codes. Harbor still owns installation,
exec, logs, trajectory download and cleanup.

The Phase 4 VGB integration runs in a separate Python process selected by `VGB_PYTHON`.
It sends JSON requests to the official package's public `load_track`, `prompts`, `task`
and `evaluate_one` APIs. Prompt files contain only public task inputs; scoring output is
kept verbatim inside the projected domain result.
