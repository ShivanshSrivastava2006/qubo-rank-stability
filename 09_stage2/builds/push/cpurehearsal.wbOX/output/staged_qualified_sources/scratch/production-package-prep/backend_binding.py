"""Load the audited V2 source closure; grants no production authority."""
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys

BACKEND_REL = 'research/g9/kaggle_wp7b/wp7b_launcher.py'
BRIDGE_REL = 'research/g9/cuda_qualification_v2/wp7b_v2_bridge_compat.py'

def load_reviewed_backend(root, pins_path, *, expected_pins_sha256, provider):
    """Require an independent manifest pin before importing any candidate code.

    The caller supplies the reviewed provider module and manifest hash. Neither
    this function nor the manifest accepts the identity for scientific writing.
    """
    root = Path(root).resolve()
    raw = Path(pins_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_pins_sha256:
        raise ValueError('Refused: independently pinned source manifest mismatch')
    manifest = json.loads(raw)
    if manifest.get('schema') != 'decisions_os/reviewed_prerun_python_sources/v1':
        raise ValueError('Refused: source manifest schema')
    pins = manifest['source_sha256']
    for required in (BACKEND_REL, BRIDGE_REL):
        if required not in pins:
            raise ValueError('Refused: required source absent from reviewed manifest')
    def checked_path(rel):
        p = root / rel
        if Path(rel).is_absolute() or p.is_symlink() or p.resolve() != p or not p.is_file():
            raise ValueError('Refused: source path escapes or is not a regular file')
        if hashlib.sha256(p.read_bytes()).hexdigest() != pins[rel]:
            raise ValueError('Refused: reviewed source mismatch: ' + rel)
        return p
    # Verify the complete Python closure BEFORE executing its module imports.
    for rel in pins:
        checked_path(rel)
    def check_imported_sources():
        for name, module in tuple(sys.modules.items()):
            if name != 'research' and not name.startswith('research.'):
                continue
            filename = getattr(module, '__file__', None)
            if filename is None:
                continue
            p = Path(filename).resolve()
            try:
                rel = str(p.relative_to(root))
            except ValueError:
                raise ValueError('Refused: cached research module belongs to another root: ' + name)
            if rel not in pins:
                raise ValueError('Refused: imported research source is not reviewed: ' + name)
            checked_path(rel)
    check_imported_sources()
    source = checked_path(BACKEND_REL)
    name = '_reviewed_wp7b_backend_' + pins[BACKEND_REL][:16]
    if name in sys.modules:
        raise ValueError('Refused: backend module name already loaded')
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(root))
    try:
        spec.loader.exec_module(module)
        if module.D013_V2_BRIDGE_REL != BRIDGE_REL:
            raise ValueError('Refused: backend resolves a different bridge')
        backend = module.Wp7bDeviceBackend
        if Path(inspect.getsourcefile(backend)).resolve() != source:
            raise ValueError('Refused: backend class does not belong to reviewed source')
        if backend.__init__.__globals__ is not module.__dict__:
            raise ValueError('Refused: constructor globals do not belong to reviewed module')
        # Use the actual resolver used by this constructor, not a separate clone.
        bridge = module._d013_v2_bridge()
        if Path(bridge.__file__).resolve() != checked_path(BRIDGE_REL):
            raise ValueError('Refused: actual backend bridge source mismatch')
        check_imported_sources()
        binding = provider.ReviewedV2Backend(
            backend_class=backend, backend_source=source,
            d013_bridge_module=bridge, backend_source_sha256=pins[BACKEND_REL],
            d013_bridge_source_sha256=pins[BRIDGE_REL],
            release_profile='d013_v2', d013_version='v2')
        binding._validate()
        return binding
    finally:
        sys.path.pop(0)
