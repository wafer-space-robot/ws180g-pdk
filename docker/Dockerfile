# SPDX-License-Identifier: Apache-2.0
# Adapted from mithro/gf180-tcad docker/base/Dockerfile (Apache-2.0)
# ws180g-pdk base image: the pinned gf180-tcad base image (IIC-OSIC-TOOLS: KLayout, Magic, netgen,
# ngspice, the GF180MCU open PDK) plus a locked Python venv /opt/ws180g with the workspace's
# runtime dependencies (docker/requirements.lock). Project code is NOT baked in; build/sandbox-run
# mounts the repo at /work/src. Build with docker/build (reproducible: SOURCE_DATE_EPOCH +
# rewrite-timestamp).
ARG BASE_IMAGE=ghcr.io/mithro/gf180-tcad-base@sha256:aedc07956fa71f33094decf80828a13e75ace36cb2426f720b0817aa9aca99b6
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
ARG SOURCE_DATE_EPOCH

USER root
# Venv from the image's own /usr/bin/python3 (3.12.3): no pip inside it, no bytecode, hashes only,
# wheels only, no dependency resolution (the lock is complete). Bytecode embeds source mtimes, so
# none may be written.
RUN --mount=type=bind,source=requirements.lock,target=/run/ws180g/requirements.lock \
    --mount=type=tmpfs,target=/tmp \
    export HOME=/tmp PIP_CONFIG_FILE=/dev/null PYTHONDONTWRITEBYTECODE=1 \
 && /usr/bin/python3 -m venv --without-pip /opt/ws180g \
 && /usr/bin/python3 -m pip --python /opt/ws180g/bin/python install \
        --no-cache-dir --disable-pip-version-check --no-input --no-compile \
        --require-hashes --no-deps --only-binary=:all: -r /run/ws180g/requirements.lock \
 && test -z "$(find /opt/ws180g -name '*.pyc' -print -quit)"
USER 1000:1000

# PATH deliberately replaces the base PATH: the venv, then the EDA tools, then the system.
ENV PATH=/opt/ws180g/bin:/foss/tools/klayout:/foss/tools/magic/bin:/foss/tools/netgen/bin:/foss/tools/ngspice/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    VIRTUAL_ENV=/opt/ws180g \
    PYTHONDONTWRITEBYTECODE=1 \
    PDK_ROOT=/foss/pdks \
    PDK=gf180mcuD \
    WS180G_BASE_IMAGE=${BASE_IMAGE} \
    HOME=/tmp/home \
    TZ=UTC

LABEL org.opencontainers.image.source="https://github.com/wafer-space-robot/ws180g-pdk" \
      org.opencontainers.image.title="ws180g-pdk-base" \
      org.opencontainers.image.description="gf180-tcad base (IIC-OSIC-TOOLS) plus the locked ws180g Python venv" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.base.name="${BASE_IMAGE}"

# The IIC entrypoint starts a VNC desktop; never run it.
ENTRYPOINT []
CMD ["/bin/bash"]
