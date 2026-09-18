# The Form in the browser, in a container.  Two stages: the first builds the virtual
# environment, the second keeps only that environment — no uv, no compiler, no sources.
FROM python:3.13-alpine AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=0
WORKDIR /app

# Two sets of packages are left out of the image, about 25 MB together.
#   The terminal Form: only `generate` without --web opens it, and this image only serves the
#   browser Form.  These are textual and the packages nothing else here needs.
ARG WITHOUT_TERMINAL_FORM="--no-install-package textual --no-install-package rich \
    --no-install-package pygments --no-install-package markdown-it-py \
    --no-install-package mdit-py-plugins --no-install-package mdurl \
    --no-install-package linkify-it-py --no-install-package platformdirs"
#   Uvicorn's speed-ups and extras: it works without them, on asyncio and h11.  The Form serves
#   one small page and one PDF at a time, so they change nothing here.  Websockets, reloading
#   and --env-file go with them; the Form uses none of the three.
ARG WITHOUT_UVICORN_EXTRAS="--no-install-package uvloop --no-install-package httptools \
    --no-install-package websockets --no-install-package watchfiles \
    --no-install-package pyyaml --no-install-package python-dotenv"

# The dependencies first, so a change to the code does not download them again.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project $WITHOUT_TERMINAL_FORM $WITHOUT_UVICORN_EXTRAS

# Then the package itself, installed as a copy (--no-editable), so the sources stay behind.
COPY src ./src
COPY app.py ./
RUN uv sync --frozen --no-dev --no-editable $WITHOUT_TERMINAL_FORM $WITHOUT_UVICORN_EXTRAS \
    && .venv/bin/python -c "import app"   # the server must start with the packages left out


FROM python:3.13-alpine
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app.py ./
# The server writes nothing: each PDF is built in memory and downloaded by the browser.
RUN adduser -D -H form
USER form
EXPOSE 5001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5001"]
