from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import FastAPI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

_RUN_COOKIE = "hai_view_run"
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


def _selected_run_name(request: Request) -> str:
    explicit = request.query_params.get("hai_run") or request.query_params.get("run")
    if explicit:
        return explicit
    referer = request.headers.get("referer", "")
    referer_query = parse_qs(urlsplit(referer).query)
    referenced = referer_query.get("hai_run") or referer_query.get("run")
    if referenced:
        return referenced[0]
    return request.cookies.get(_RUN_COOKIE, "")


@dataclass(frozen=True)
class ArtifactRun:
    name: str
    jobs_dir: Path
    job_count: int
    modified_at: float
    category: str | None  # formal, temporary, timeout-rerun, or None for legacy


def discover_artifact_runs(artifacts_dir: Path) -> tuple[ArtifactRun, ...]:
    """Discover categorized, timeout-rerun, and legacy top-level artifact runs."""
    runs = []

    # Discover categorized runs (formal/ and temporary/)
    for category_name in ["formal", "temporary"]:
        category_dir = artifacts_dir / category_name
        if category_dir.is_dir() and not category_dir.is_symlink():
            for child in category_dir.iterdir():
                jobs_dir = child / "jobs"
                if not child.is_dir() or child.is_symlink() or not jobs_dir.is_dir():
                    continue
                job_count = sum(
                    job.is_dir() and (job / "config.json").is_file() for job in jobs_dir.iterdir()
                )
                runs.append(
                    ArtifactRun(
                        name=child.name,
                        jobs_dir=jobs_dir,
                        job_count=job_count,
                        modified_at=child.stat().st_mtime,
                        category=category_name,
                    )
                )

    # Timeout campaigns are nested below timeout-rerun/<campaign>/jobs.
    timeout_dir = artifacts_dir / "timeout-rerun"
    if timeout_dir.is_dir() and not timeout_dir.is_symlink():
        for jobs_dir in timeout_dir.rglob("jobs"):
            relative = jobs_dir.relative_to(timeout_dir)
            if (
                not jobs_dir.is_dir()
                or jobs_dir.is_symlink()
                or len(relative.parts) < 2
                or "jobs" in relative.parts[:-1]
                or any(
                    (timeout_dir / Path(*relative.parts[:index])).is_symlink()
                    for index in range(1, len(relative.parts))
                )
            ):
                continue
            run_dir = jobs_dir.parent
            job_count = sum(
                job.is_dir() and (job / "config.json").is_file() for job in jobs_dir.iterdir()
            )
            runs.append(
                ArtifactRun(
                    name=(Path("timeout-rerun") / run_dir.relative_to(timeout_dir)).as_posix(),
                    jobs_dir=jobs_dir,
                    job_count=job_count,
                    modified_at=run_dir.stat().st_mtime,
                    category="timeout-rerun",
                )
            )

    # Discover legacy top-level runs (backward compatibility)
    for child in artifacts_dir.iterdir():
        # Skip category directories
        if child.name in ("formal", "temporary", "timeout-rerun"):
            continue

        jobs_dir = child / "jobs"
        if not child.is_dir() or child.is_symlink() or not jobs_dir.is_dir():
            continue
        job_count = sum(
            job.is_dir() and (job / "config.json").is_file() for job in jobs_dir.iterdir()
        )
        runs.append(
            ArtifactRun(
                name=child.name,
                jobs_dir=jobs_dir,
                job_count=job_count,
                modified_at=child.stat().st_mtime,
                category=None,  # Legacy top-level
            )
        )

    return tuple(sorted(runs, key=lambda run: (-run.modified_at, run.name)))


class _RunDispatcher:
    def __init__(self, artifacts_dir: Path, static_dir: Path | None) -> None:
        self.artifacts_dir = artifacts_dir
        self.static_dir = static_dir
        self._apps: dict[str, FastAPI] = {}

    def find_run(self, name: str) -> ArtifactRun | None:
        """Find run by name. Prefers categorized runs over legacy top-level."""
        candidates = [
            run for run in discover_artifact_runs(self.artifacts_dir) if run.name == name
        ]
        if not candidates:
            return None
        # Prefer categorized (formal or temporary) over legacy None
        categorized = [r for r in candidates if r.category is not None]
        return categorized[0] if categorized else candidates[0]

    def _cache_key(self, run: ArtifactRun) -> str:
        """Generate cache key that isolates runs by category."""
        if run.category is None:
            return run.name
        return f"{run.category}/{run.name}"

    def app_for(self, run: ArtifactRun) -> FastAPI:
        from harbor.viewer import create_app

        cache_key = self._cache_key(run)
        app = self._apps.get(cache_key)
        if app is None:
            app = create_app(run.jobs_dir, mode="jobs", static_dir=self.static_dir)
            self._apps[cache_key] = app
        return app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        run_name = _selected_run_name(request)
        run = self.find_run(run_name)
        if run is None:
            if scope["path"].startswith("/api/"):
                response = JSONResponse(
                    {"detail": "Select a run-artifacts directory first."}, status_code=409
                )
            else:
                response = RedirectResponse("/", status_code=303)
            response.delete_cookie(_RUN_COOKIE, path="/")
            await response(scope, receive, send)
            return
        await self.app_for(run)(scope, receive, send)


def create_multi_run_viewer(
    artifacts_dir: Path, *, static_dir: Path | None = None
) -> Starlette:
    artifacts_dir = artifacts_dir.expanduser().resolve()
    dispatcher = _RunDispatcher(artifacts_dir, static_dir)

    async def index(request: Request) -> HTMLResponse:
        selected_name = request.query_params.get("run") or request.query_params.get("hai_run")
        if selected_name is not None:
            run = dispatcher.find_run(selected_name)
            if run is None:
                return HTMLResponse(
                    _not_found_page(selected_name),
                    status_code=404,
                    headers=_NO_STORE_HEADERS,
                )
            if static_dir is None or not (static_dir / "index.html").is_file():
                response = HTMLResponse(
                    _missing_viewer_page(), status_code=503, headers=_NO_STORE_HEADERS
                )
            else:
                response = HTMLResponse(
                    _viewer_page(static_dir, run.name), headers=_NO_STORE_HEADERS
                )
            response.set_cookie(
                _RUN_COOKIE,
                run.name,
                httponly=True,
                samesite="strict",
                path="/",
            )
            return response
        return HTMLResponse(
            _directory_page(discover_artifact_runs(artifacts_dir)),
            headers=_NO_STORE_HEADERS,
        )

    async def page_or_delegate(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope)
        if scope["path"].startswith(("/api/", "/assets/", "/fonts/", "/favicon")):
            await dispatcher(scope, receive, send)
            return
        run_name = _selected_run_name(request)
        run = dispatcher.find_run(run_name)
        if run is None:
            response = RedirectResponse("/", status_code=303, headers=_NO_STORE_HEADERS)
            response.delete_cookie(_RUN_COOKIE, path="/")
        elif static_dir is None or not (static_dir / "index.html").is_file():
            response = HTMLResponse(
                _missing_viewer_page(), status_code=503, headers=_NO_STORE_HEADERS
            )
        else:
            response = HTMLResponse(
                _viewer_page(static_dir, run.name), headers=_NO_STORE_HEADERS
            )
        await response(scope, receive, send)

    return Starlette(routes=[Route("/", index), Mount("/", app=page_or_delegate)])


def run_multi_run_viewer(artifacts_dir: Path, *, host: str, port: int) -> None:
    import uvicorn
    from harbor.cli.view import STATIC_DIR

    static_dir = STATIC_DIR if STATIC_DIR.is_dir() else None
    app = create_multi_run_viewer(artifacts_dir, static_dir=static_dir)
    print("Starting Harbor multi-run Viewer")
    print(f"  Artifacts directory: {artifacts_dir}")
    print(f"  Server: http://{host}:{port}")
    if static_dir is None:
        print("  Warning: Harbor Viewer static files are not installed.")
    uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="info")).run()


def _directory_page(runs: tuple[ArtifactRun, ...]) -> str:
    rows = "".join(_run_row(run) for run in runs)
    if not rows:
        rows = """
          <div class="empty">
            <strong>No Harbor runs found</strong>
            <span>Directories with a <code>jobs/</code> folder will appear here.</span>
          </div>
        """
    run_label = "run" if len(runs) == 1 else "runs"
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Run artifacts | Harbor</title>
    <style>
      :root {{
        color-scheme: light dark;
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      }}
      * {{ box-sizing: border-box; }}
      body {{ margin: 0; min-height: 100vh; background: #f7f8f6; color: #17201b; }}
      main {{ width: min(920px, calc(100% - 32px)); margin: 0 auto; padding: 56px 0 80px; }}
      header {{
        display: flex;
        align-items: end;
        justify-content: space-between;
        gap: 24px;
        padding-bottom: 20px;
        border-bottom: 1px solid #cbd1cc;
      }}
      h1 {{
        margin: 0;
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 3.25rem;
        font-weight: 500;
        line-height: .95;
        letter-spacing: 0;
      }}
      .summary {{ margin: 0 0 4px; color: #5d675f; font-size: .8125rem; white-space: nowrap; }}
      .list {{ margin-top: 24px; border-top: 1px solid #dce0dc; }}
      .run {{
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto auto;
        align-items: center;
        gap: 24px;
        min-height: 72px;
        padding: 12px 4px;
        color: inherit;
        text-decoration: none;
        border-bottom: 1px solid #dce0dc;
      }}
      .run:hover, .run:focus-visible {{ background: #edf1ed; outline: none; }}
      .name {{
        overflow: hidden;
        font-size: .9375rem;
        font-weight: 650;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .category {{
        display: inline-block;
        margin-left: 8px;
        padding: 2px 8px;
        font-size: .75rem;
        font-weight: 600;
        border-radius: 4px;
        text-transform: uppercase;
      }}
      .category.formal {{
        background: #d4f4e2;
        color: #0f6d38;
      }}
      .category.temporary {{
        background: #fee;
        color: #b71c1c;
      }}
      .category.timeout-rerun {{
        background: #e8eaf6;
        color: #303f9f;
      }}
      .category.legacy {{
        background: #e0e0e0;
        color: #616161;
      }}
      .count {{ color: #68726a; font-size: .8125rem; }}
      .open {{ color: #17653a; font-size: .8125rem; font-weight: 700; }}
      .empty {{
        display: grid;
        gap: 8px;
        padding: 56px 4px;
        color: #68726a;
        border-bottom: 1px solid #dce0dc;
      }}
      .empty strong {{
        color: #17201b;
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 1.35rem;
        font-weight: 500;
      }}
      code {{ font-family: inherit; color: #17653a; }}
      @media (max-width: 600px) {{
        main {{ width: min(100% - 24px, 920px); padding-top: 32px; }}
        header {{ align-items: start; flex-direction: column; gap: 12px; }}
        h1 {{ font-size: 2.25rem; }}
        .run {{ grid-template-columns: minmax(0, 1fr) auto; gap: 8px 16px; }}
        .count {{ grid-column: 1; grid-row: 2; }}
        .open {{ grid-column: 2; grid-row: 1 / span 2; }}
      }}
      @media (prefers-color-scheme: dark) {{
        body {{ background: #101411; color: #e6ebe7; }}
        header {{ border-color: #3a433c; }}
        .summary, .count, .empty {{ color: #a6b0a8; }}
        .list, .run, .empty {{ border-color: #303832; }}
        .run:hover, .run:focus-visible {{ background: #19201b; }}
        .category.formal {{ background: #1a3d2a; color: #72d796; }}
        .category.temporary {{ background: #3d1a1a; color: #ff6b6b; }}
        .category.timeout-rerun {{ background: #202b50; color: #b3c4ff; }}
        .category.legacy {{ background: #2a2a2a; color: #9e9e9e; }}
        .open, code {{ color: #72d796; }}
        .empty strong {{ color: #e6ebe7; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>Run artifacts</h1>
        <p class="summary">{len(runs)} {run_label}</p>
      </header>
      <section class="list" aria-label="Artifact directories">{rows}</section>
    </main>
  </body>
</html>"""


def _run_row(run: ArtifactRun) -> str:
    query = urlencode({"run": run.name})
    name = escape(run.name)
    job_label = "job" if run.job_count == 1 else "jobs"

    # Add category badge
    if run.category == "formal":
        category_badge = '<span class="category formal">Formal</span>'
    elif run.category == "temporary":
        category_badge = '<span class="category temporary">Temporary</span>'
    elif run.category == "timeout-rerun":
        category_badge = '<span class="category timeout-rerun">Timeout rerun</span>'
    else:
        category_badge = '<span class="category legacy">Legacy</span>'

    return f"""
        <a class="run" href="/?{query}">
          <span class="name">{name}{category_badge}</span>
          <span class="count">{run.job_count} {job_label}</span>
          <span class="open">Open jobs &rarr;</span>
        </a>"""


def _not_found_page(name: str) -> str:
    return _message_page("Run not found", f"No browsable run named {escape(name)}.")


def _missing_viewer_page() -> str:
    return _message_page("Viewer unavailable", "Harbor Viewer static files are not installed.")


def _message_page(title: str, message: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p>{message}</p>
    <p><a href="/">Back to run artifacts</a></p>
  </main>
</body>
</html>"""


def _viewer_page(static_dir: Path, run_name: str) -> str:
    document = (static_dir / "index.html").read_text(encoding="utf-8")
    javascript_name = json.dumps(run_name).replace("<", "\\u003c")
    script = f"""
<style>
  #hai-run-nav {{
    position: fixed;
    z-index: 9999;
    top: 0;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 48px;
    padding: 8px 20px;
    background: #17201b;
    color: #f4f7f4;
    font: 600 13px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}
  #hai-run-nav a {{ color: #9be2b4; text-decoration: none; }}
  #hai-run-nav a:hover, #hai-run-nav a:focus-visible {{ text-decoration: underline; }}
  #hai-run-name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  body {{ padding-top: 48px !important; }}
</style>
<script>
  (() => {{
    const run = {javascript_name};
    window.__haiRun = run;
    const mountNav = () => {{
      if (document.getElementById('hai-run-nav')) return;
      const nav = document.createElement('nav');
      nav.id = 'hai-run-nav';
      nav.setAttribute('aria-label', 'Harbor run navigation');
      const back = document.createElement('a');
      back.href = '/';
      back.textContent = '\u2190 All runs';
      const label = document.createElement('span');
      label.id = 'hai-run-name';
      label.title = run;
      label.textContent = `Run: ${{run}}`;
      nav.append(back, label);
      document.body.prepend(nav);
    }};
    const keepNavMounted = () => {{
      mountNav();
      new MutationObserver(mountNav).observe(document.body, {{childList: true}});
    }};
    if (document.readyState === 'complete') keepNavMounted();
    else window.addEventListener('load', keepNavMounted);
    const withRun = (value) => {{
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin) return value;
      if (url.pathname.startsWith('/api/')) url.searchParams.set('hai_run', run);
      else if (!url.pathname.startsWith('/assets/') && !url.pathname.startsWith('/fonts/'))
        url.searchParams.set('hai_run', run);
      return url.pathname + url.search + url.hash;
    }};
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {{
      const request = input instanceof Request
        ? new Request(withRun(input.url), input)
        : withRun(input);
      return originalFetch(request, init);
    }};
    for (const method of ['pushState', 'replaceState']) {{
      const original = history[method].bind(history);
      history[method] = (state, title, url) => original(state, title, url ? withRun(url) : url);
    }}
  }})();
</script>
"""
    return document.replace("</head>", script + "</head>")
