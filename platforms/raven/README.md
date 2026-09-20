# Raven Prism platform

`agent_hud/` is the Raven runtime and keeps the Python import name `agent_hud`.
`main.py` adds this platform directory to `sys.path` because Raven's deployer
copies files instead of installing the package. Local/CI installs use the
package mapping in `pyproject.toml`.

The Raven Framework is a separate proprietary dependency and is never committed.
Only `main.py` and this runtime directory may enter the `.rav` payload. Raven's
current evidence is simulator and automated testing; physical hardware is not
claimed by this repository.
