ARG BASE_IMAGE=node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
ARG RDKIT_VERSION=2026.3.2
ARG RDKIT_WHEEL_SHA256=d273ef9c6ba8ef56a4cc4ae3c91e086afe54a6f9849f9fb5b3d6e459b861c664
ARG NUMPY_VERSION=2.2.6
ARG NUMPY_WHEEL_SHA256=b64d8d4d17135e00c8e346e0a738deb17e754230d7e0810ac5012750bbd85a5a
ARG PILLOW_VERSION=11.3.0
ARG PILLOW_WHEEL_SHA256=7d1aa4de119a0ecac0a34a9c8bde33f34022e2e8f99104e47a3ca392fd60e37d
FROM ${BASE_IMAGE}
ARG RDKIT_VERSION
ARG RDKIT_WHEEL_SHA256
ARG NUMPY_VERSION
ARG NUMPY_WHEEL_SHA256
ARG PILLOW_VERSION
ARG PILLOW_WHEEL_SHA256

# Keep Harbor's system dependency checks off the network-dependent package path.
RUN for attempt in 1 2 3 4 5; do \
      apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=120 update \
        && break; \
      test "$attempt" -lt 5 || exit 1; \
      sleep 5; \
    done \
    && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=120 \
      install --no-install-recommends --yes \
        bash \
        bzip2 \
        ca-certificates \
        curl \
        git \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        xz-utils \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && ln -sf /usr/bin/pip3 /usr/local/bin/pip \
    && rm -rf /var/lib/apt/lists/*

RUN printf '%s\n' \
      "numpy==${NUMPY_VERSION} --hash=sha256:${NUMPY_WHEEL_SHA256}" \
      "Pillow==${PILLOW_VERSION} --hash=sha256:${PILLOW_WHEEL_SHA256}" \
      "rdkit==${RDKIT_VERSION} --hash=sha256:${RDKIT_WHEEL_SHA256}" \
      > /tmp/agent-python-requirements.txt \
    && python3 -m pip install --break-system-packages --no-cache-dir \
      --only-binary=:all: --require-hashes -r /tmp/agent-python-requirements.txt \
    && rm -f /tmp/agent-python-requirements.txt

# The two platform locks use the same xTB source tarball, recipe commit and patches.
COPY chemistry-linux-aarch64.explicit /tmp/chemistry.explicit
RUN curl --fail --location --retry 5 --max-time 180 \
      https://conda.anaconda.org/conda-forge/linux-aarch64/micromamba-2.3.2-0.tar.bz2 \
      -o /tmp/micromamba.tar.bz2 \
    && echo '7ded447a291cd1a05efe42c895a43f11fa3446011957cffe899aeabda8c3ee25  /tmp/micromamba.tar.bz2' | sha256sum -c - \
    && tar -xjf /tmp/micromamba.tar.bz2 -C /tmp bin/micromamba \
    && MAMBA_ROOT_PREFIX=/tmp/mamba /tmp/bin/micromamba create --yes \
      --prefix /opt/vgb-crest --file /tmp/chemistry.explicit \
    && rm -rf /tmp/mamba /tmp/bin /tmp/micromamba.tar.bz2 /tmp/chemistry.explicit

# Login shells reset PATH; retain the same tools through the standard system entry points.
RUN ln -s /opt/vgb-crest/bin/xtb /usr/local/bin/xtb \
    && ln -s /opt/vgb-crest/bin/crest /usr/local/bin/crest

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/vgb-crest/bin:$PATH \
    XTBPATH=/opt/vgb-crest/share/xtb
