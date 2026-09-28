ARG BASE_IMAGE=node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e
FROM ${BASE_IMAGE}

# The benchmark skills choose their own third-party Python dependencies at run time.
# Keep the image limited to the interpreter, pip, and venv support.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        ca-certificates \
        python3 \
        python3-pip \
        python3-venv \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && ln -sf /usr/bin/pip3 /usr/local/bin/pip \
    && rm -rf /var/lib/apt/lists/*

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONDONTWRITEBYTECODE=1
