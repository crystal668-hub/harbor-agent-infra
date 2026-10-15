ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY . /opt/hai/build/
RUN python3 /opt/hai/build/install.py \
    && rm -rf /root/.npm /root/.cache /root/.nvm/.cache /tmp/hai-downloads \
    && rm -rf /opt/hai/build
# The pinned native Claude binary supports this switch; the per-Trial native
# configuration also already disables nonessential traffic.
ENV DISABLE_AUTOUPDATER=1
