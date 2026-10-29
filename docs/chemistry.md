# Chemistry alignment

> 文档类型：实验文档（实验化学工具配置与一致性要求）。不属于通用开发者手册。

The agent image and host verifier share the `chemistry` lock in `runtime-lock.json`:
RDKit 2026.03.2, xTB 6.7.1, and CREST 2.12. VGB Python remains in its isolated
Python 3.12 runtime. Both ordinary xTB and CREST verifiers use the tools from one
explicitly selected `vgb-crest` prefix.

## Install and bind the verifier tools

After provisioning the official VGB runtime, run:

```sh
uv run --locked --python 3.12 python scripts/provision_chemistry.py \
  --prefix /absolute/path/to/vgb-crest --runtime-dir .vgb-runtime
```

A missing prefix is created from the native platform's explicit Conda package list.
An existing prefix is checked without updating its packages. This writes the local,
ignored `.vgb-runtime/chemistry-runtime.json` binding after validation succeeds.
Alternatively set `VGB_CHEMISTRY_PREFIX` and `VGB_CHEMISTRY_LOCK` explicitly.
`scripts/provision_vgb_runtime.py` also accepts `--chemistry-prefix` to perform both
steps. The Conda prefix contains external tools; it does not need a Python interpreter.

The current local deployment uses Miniforge's `envs/vgb-crest`. It contains native
macOS arm64 CREST 2.12 (`hd8c59f4_0`) and xTB 6.7.1 (`gfortran_hc17bbfb_5`).
The Linux arm64 image uses CREST 2.12 (`h0b5e8e2_0`) and xTB 6.7.1
(`gfortran_hcd2ce30_5`). Both platforms' complete package lists include SHA256 checksums.

## Source and parameter identity

The two xTB package recipes were inspected directly. Both use the source archive
SHA256 `79a2a2f50091b3b941e5139c1b38a53203d5d2e9ba496a7ad505d8c31ccd6013`
and conda-forge recipe commit `811e76f7850e403de1b564d2dd449fe0a0d8d9cb`.
All five patch files match byte for byte. The source URL, recipe commit, patch hashes,
platform package hashes, and six common parameter-file hashes are recorded in the lock.
RDKit uses the official PyPI 2026.3.2 wheels for CPython 3.11/Linux arm64 and
CPython 3.12/macOS arm64; archive and installed-content hashes are locked separately.

The runtime sets `XTBPATH` only to the selected prefix's `share/xtb`, sets `XTBHOME`
to that prefix, rejects unmanaged `.xtbrc` overrides, and strips inherited XTB and
dynamic-library overrides. It does not source xTB's activation scripts, which add
the user's home directory to the parameter search path.

## Preflight and failure behavior

`run_paired_jobs` probes the actual verifier and digest-pinned agent image before
materialization or Job creation. `run_group_jobs` delegates to this same mandatory
gate. Direct OpenClaw/Hermes VGB E2E entry points also invoke it. Resumes and reruns
recheck the environments; results with an older/different chemistry lock must use
a new output directory.

The gate checks imported RDKit versions and installed files, xTB/CREST versions and
binary hashes, package metadata, parameter-file names and hashes, image digest, and
platform. Probe errors, missing tools, mismatches and timeouts block execution.
Evidence is saved to `chemistry-preflight.json` even on failure and included in
successful runtime manifests. Every VGB evaluation rechecks the host toolchain.

Verifier subprocesses receive a controlled PATH containing the selected prefix and
system utilities. Conda discovery variables are removed and a PATH exposing `conda`
is rejected. Consequently a missing/wrong CREST or xTB cannot silently switch to
another environment. Docker-based VGB backends retain an absolute Docker executable.

This verifies the preinstalled baseline and the verifier toolchain. Agents can still
install packages inside disposable trials; this is not enforcement against changes
made by an agent during its own run. Equal source/version/parameters do not imply
bitwise-identical results across operating systems or math libraries.

## Build and validate

```sh
./scripts/build_agent_image.sh hai-base-env:chemistry-20261013
uv run --locked --python 3.12 pytest -q -m 'not integration'
VGB_PYTHON=.vgb-runtime/bin/python uv run --locked --python 3.12 pytest -q \
  tests/test_chemistry_integration.py tests/test_agent_image_integration.py \
  tests/test_vgb_integration.py tests/test_vgb_verifier_integration.py
```

The build verifies the explicit package lock and installed chemistry before optional
publication with `--push`. Record the returned immutable RepoDigest in the runtime
lock and active experiment configs when intentionally upgrading. Do not rewrite
historical result manifests. Default experiment validation uses `skills_off` only.

The integration checks include actual image/verifier parity, a provider-free RDKit
evaluation, and an ethanol CREST search followed by an xTB single-point calculation.
The latter checks tool interoperability, not the scientific score of the full pyrene task.
