# Vesper Relay sandbox image: the locked room where brains and gates run (P1-T9).
#
# Build for this machine:   vesper sandbox build            (tag: vesper-sandbox:<digest of this file>)
# Both architectures:       docker buildx build --platform linux/arm64,linux/amd64 -t vesper-sandbox sandbox/
#
# Debian slim with Python 3, Go, Node LTS + pnpm, Playwright for Node and Python (each
# with the Chromium build it expects, sharing one set of OS libraries), the v1.0 agent CLIs
# (Claude Code, Codex, Gemini CLI) and tinyproxy, which guards brain traffic. Every version
# is pinned below; Go and Node downloads are checked against their published SHA-256 sums.
# Vesper runs the container as your own uid with a read-only root filesystem, so nothing
# here needs to be writable at run time.
ARG BASE_IMAGE=debian:trixie-slim
FROM ${BASE_IMAGE}

ARG TARGETARCH
ARG GO_VERSION=1.27.4
ARG NODE_VERSION=26.13.1
ARG PNPM_VERSION=12.21.0
ARG PLAYWRIGHT_VERSION=1.65.1
ARG GREENLET_VERSION=3.5.6
ARG CLAUDE_CODE_VERSION=2.1.327
ARG CODEX_VERSION=0.170.0
ARG GEMINI_CLI_VERSION=0.68.0

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PATH=/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    NPM_CONFIG_UPDATE_NOTIFIER=false

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl xz-utils git libatomic1 python3 python3-pip tinyproxy ripgrep \
 && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH:-$(dpkg --print-architecture)}" in \
      arm64) go_arch=arm64; node_arch=arm64 ;; \
      amd64) go_arch=amd64; node_arch=x64 ;; \
      *) echo "unsupported architecture ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    cd /tmp; \
    go_file="go${GO_VERSION}.linux-${go_arch}.tar.gz"; \
    curl -fsSLO "https://go.dev/dl/${go_file}"; \
    go_sum="$(curl -fsSL 'https://go.dev/dl/?mode=json&include=all' | python3 -c 'import json, sys; \
print(next(f["sha256"] for r in json.load(sys.stdin) for f in r["files"] if f["filename"] == sys.argv[1]))' "${go_file}")"; \
    echo "${go_sum}  ${go_file}" | sha256sum -c -; \
    tar -C /usr/local -xzf "${go_file}"; \
    node_file="node-v${NODE_VERSION}-linux-${node_arch}.tar.xz"; \
    curl -fsSLO "https://nodejs.org/dist/v${NODE_VERSION}/${node_file}"; \
    curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/SHASUMS256.txt" | grep " ${node_file}\$" | sha256sum -c -; \
    tar -C /usr/local --strip-components=1 -xJf "${node_file}"; \
    rm -f "${go_file}" "${node_file}"; \
    go version; node --version

RUN npm install -g --no-fund --no-audit \
      "pnpm@${PNPM_VERSION}" \
      "playwright@${PLAYWRIGHT_VERSION}" \
      "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
      "@openai/codex@${CODEX_VERSION}" \
      "@google/gemini-cli@${GEMINI_CLI_VERSION}" \
 && npm cache clean --force \
 && rm -rf /root/.npm

RUN playwright install --with-deps chromium \
 && chmod -R a+rX "${PLAYWRIGHT_BROWSERS_PATH}" \
 && rm -rf /var/lib/apt/lists/* /tmp/*

# Python gates (python3 -I checks/*.py) use Python Playwright. It may pin a different Chromium
# build than the Node package of the same version (1.65.1: 1254 against 1255), so it installs
# its own into PLAYWRIGHT_BROWSERS_PATH; the OS libraries are already there.
RUN python3 -m pip install --no-cache-dir --break-system-packages --only-binary=:all: \
      "playwright==${PLAYWRIGHT_VERSION}" \
      "greenlet==${GREENLET_VERSION}" \
 && python3 -m playwright install chromium \
 && chmod -R a+rX "${PLAYWRIGHT_BROWSERS_PATH}" \
 && rm -rf /tmp/*

# Vesper passes --user (your uid); 10001 is the fallback when nothing else is given.
RUN mkdir -p /home/vesper /work && chmod 1777 /home/vesper /work
USER 10001
WORKDIR /work
