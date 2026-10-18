import os
from pathlib import Path
from .native import SPECS, factory
from .runtime import create_runtime


def create_app(data_dir=None, port=None):
    port = port or int(os.environ.get("HERMES_PORT", "5221"))
    root = Path(__file__).parent
    data_dir = Path(data_dir or os.environ.get("HERMES_DATA_DIR") or root.parent / "data")
    return create_runtime(name="Hermes's Hoard", product="hermes", root=root, data_dir=data_dir,
                          specs=SPECS, port=port, factory=lambda key, path: factory(key, path, port=port))
