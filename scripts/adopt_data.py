"""Point at existing histories without opening, moving or copying their contents."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCT = "talos" if (ROOT / "talos_hoard").exists() else "hermes"
FOLDERS = {"screen": "Argus's Hoard", "clipboard": "Echo's Hoard", "activity": "Funes's Hoard",
           "audio": "Funes's Hoard", "services": "Cassandra's Hoard", "disk": "Disk Hoard"} if PRODUCT == "talos" else {
           "products": "Tantalus's Hoard", "shipments": "Phileas's Hoard"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, default=ROOT.parent)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get(PRODUCT.upper() + "_DATA_DIR") or ROOT / "data"))
    args = parser.parse_args()
    path = args.data_dir / "modules.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"enabled": [], "data_paths": {}}
    if config.get("enabled"):
        raise SystemExit("Switch all modules OFF before changing their data locations.")
    for module, folder in FOLDERS.items():
        original = (args.parent / folder / "data").resolve()
        if module == "audio":
            original /= "audio"
        if original.is_dir():
            config.setdefault("data_paths", {})[module] = str(original)
            print(f"{module}: {original}")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
    print("All modules remain OFF. Existing histories have not been opened or changed.")


if __name__ == "__main__":
    main()
