"""
Fake pkg_resources for Python 3.14 where it was removed.
Provides minimal pkg_resources API that playwright_stealth 2.0.x needs.
"""
import importlib.resources
import pathlib

class _FakeProvider:
    def __init__(self, package: str):
        self.package = package
    def get_resource_reader(self, name):
        return importlib.resources.files(self.package).joinpath(name)

class _FakeDistribution:
    def __init__(self, package: str):
        self._provider = _FakeProvider(package)

def resource_string(package: str, resource: str) -> bytes:
    """pkg_resources.resource_string equivalent using importlib.resources."""
    try:
        # Try new API first
        files = importlib.resources.files(package)
        return files.joinpath(resource).read_bytes()
    except Exception:
        pass
    # Fallback: traverse subpackages
    parts = package.split('.')
    base = importlib.import_module(package)
    base_path = pathlib.Path(base.__file__).parent
    # Handle nested package paths (e.g., playwright_stealth/js)
    for part in resource.split('/'):
        base_path = base_path / part
    return base_path.read_bytes()

class _EntryPoint:
    def load(self): pass

class _WorkingSet:
    def __init__(self):
        self.entries = []
    def iter_entry_points(self, name=None, group=None):
        return []

working_set = _WorkingSet()

def iter_entry_points(group=None, name=None):
    return working_set.iter_entry_points(name=name, group=group)
