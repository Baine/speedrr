FROM ghcr.io/astral-sh/uv:python3.12-alpine AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /home

COPY pyproject.toml uv.lock ./

# --frozen fails the build if uv.lock is stale rather than silently
# resolving something new. That is the property that would have prevented
# the qBittorrent 5.2 breakage in the first place.
RUN uv sync --frozen --no-dev


FROM python:3.12-alpine

# Links the GHCR package to this repository. Without image.source the
# package is orphaned: no repo, no README, reduced settings page.
LABEL org.opencontainers.image.source="https://github.com/Baine/speedrr"
LABEL org.opencontainers.image.description="speedrr, patched to run on qBittorrent 5.2+"
LABEL org.opencontainers.image.licenses="GPL-3.0"

WORKDIR /home

COPY --from=builder /home/.venv /home/.venv
COPY . /home

ENV PATH="/home/.venv/bin:$PATH"

CMD ["python", "./main.py"]
