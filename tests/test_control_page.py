"""The Control page and its script must agree on the DOM.

control.js reaches for elements by id with a `$("...")` helper that is
`document.getElementById`. If the id is not in index.html, the call
returns null and the next property access throws -- and because
`render()` runs the sections in order, one missing id blanks every
section after it. That is exactly how "the whole Control is stuck on
Loading" happened once: `renderStatus` set `$("device-seen").textContent`
and there was no `#device-seen`, so devices, tasks, sources and settings
never rendered.

This is a plain text check on the two files. It needs no browser and no
framework, so it runs everywhere.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CONTROL = Path(__file__).resolve().parent.parent / "control"

# ids that control.js creates itself with el(...) and then looks up, so
# they are legitimately absent from the static HTML. Keep this list
# short and specific.
CREATED_IN_JS = set()


def _ids_referenced_by_js() -> set[str]:
    js = (CONTROL / "control.js").read_text(encoding="utf-8")
    return set(re.findall(r'\$\(\s*"([a-zA-Z0-9_-]+)"\s*\)', js))


def _ids_present_in_html() -> set[str]:
    html = (CONTROL / "index.html").read_text(encoding="utf-8")
    return set(re.findall(r'id="([a-zA-Z0-9_-]+)"', html))


def test_every_id_the_script_reaches_for_exists_in_the_page():
    referenced = _ids_referenced_by_js()
    present = _ids_present_in_html()

    missing = referenced - present - CREATED_IN_JS
    assert not missing, (
        "control.js calls $(...) for ids the page does not contain: "
        f"{sorted(missing)}. One missing id blanks every section after it."
    )


def test_the_device_last_seen_line_is_in_the_page():
    """The specific regression: renderStatus writes the device's last-seen
    time into #device-seen."""
    html = (CONTROL / "index.html").read_text(encoding="utf-8")
    assert 'id="device-seen"' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_malformed_tasks_do_not_replace_last_known_list_with_empty():
    source = (CONTROL / "control.js").read_text(encoding="utf-8")
    refresh = source.split("async function refresh() {", 1)[1].split(
        '\n$("refresh").addEventListener', 1
    )[0]
    script = f"""
const vm = require('node:vm');
const body = {json.dumps('async function refresh() {' + refresh)};
async function run(tasksPayload) {{
  const context = {{
    state: {{ tasks: [{{ id: 'last-known' }}], online: true, auth: null }},
    getJSON: async (path) => path === '/auth/state' ? {{ required: false }} :
      path === '/tasks' ? tasksPayload : path === '/settings' ? {{}} : {{ drafts: [] }},
    document: {{ activeElement: null }},
    $: () => null,
    render: () => {{}},
  }};
  vm.createContext(context);
  vm.runInContext(body + '\\nrefresh()', context);
  await new Promise((resolve) => setTimeout(resolve, 0));
  return {{ online: context.state.online, ids: context.state.tasks.map((t) => t.id) }};
}}
(async () => console.log(JSON.stringify({{
  malformed: await run({{ tasks: null }}),
  empty: await run({{ tasks: [] }}),
}})))();
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    states = json.loads(result.stdout)
    assert states["malformed"] == {"online": False, "ids": ["last-known"]}
    assert states["empty"] == {"online": True, "ids": []}
