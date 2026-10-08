ARG BASE_IMAGE=node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
ARG RDKIT_VERSION=2025.9.6
ARG RDKIT_WHEEL_SHA256=d0ec921fee7f2908e1da8c4ea1185dbb6d0a22787bcf9749b442691c121c02ef
ARG NUMPY_VERSION=2.2.6
ARG NUMPY_WHEEL_SHA256=b64d8d4d17135e00c8e346e0a738deb17e754230d7e0810ac5012750bbd85a5a
ARG PILLOW_VERSION=11.3.0
ARG PILLOW_WHEEL_SHA256=7d1aa4de119a0ecac0a34a9c8bde33f34022e2e8f99104e47a3ca392fd60e37d
ARG XTB_DEBIAN_VERSION=6.5.1-3
FROM ${BASE_IMAGE}
ARG RDKIT_VERSION
ARG RDKIT_WHEEL_SHA256
ARG NUMPY_VERSION
ARG NUMPY_WHEEL_SHA256
ARG PILLOW_VERSION
ARG PILLOW_WHEEL_SHA256
ARG XTB_DEBIAN_VERSION

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
        ca-certificates \
        curl \
        git \
        procps \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        xz-utils \
        xtb=${XTB_DEBIAN_VERSION} \
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

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONDONTWRITEBYTECODE=1
