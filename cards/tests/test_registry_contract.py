import ast
import json
import unittest
from pathlib import Path


CARDS_DIR = Path(__file__).resolve().parents[1]
ADDONS_DIR = CARDS_DIR / "addons"
REGISTRY_FILE = CARDS_DIR / "registry.json"


def literal_assignments(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value_node = node.value
        for target in targets:
            if not isinstance(target, ast.Name) or target.id not in {"CARD_ID", "CARD_NAME", "CARD_OPTIONS"}:
                continue
            try:
                values[target.id] = ast.literal_eval(value_node)
            except Exception:
                pass
    return values


class RegistryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        cls.cards = [item for item in payload.get("cards", []) if isinstance(item, dict)]

    def test_registry_and_addon_files_match_exactly(self):
        registered = {str(item.get("id") or "") for item in self.cards}
        files = {path.stem for path in ADDONS_DIR.glob("*.py") if not path.stem.startswith("_")}
        self.assertEqual(registered, files)

    def test_literal_card_ids_match_filenames_and_are_unique(self):
        ids = []
        for path in ADDONS_DIR.glob("*.py"):
            if path.stem.startswith("_"):
                continue
            card_id = literal_assignments(path).get("CARD_ID")
            self.assertEqual(card_id, path.stem, str(path))
            ids.append(card_id)
        self.assertEqual(len(ids), len(set(ids)))

    def test_option_keys_are_unique_and_registry_defaults_match_source(self):
        registry = {item["id"]: item for item in self.cards}
        for card_id, item in registry.items():
            source_options = literal_assignments(ADDONS_DIR / f"{card_id}.py").get("CARD_OPTIONS")
            if not isinstance(source_options, list):
                continue
            source_by_key = {str(option.get("key")): option for option in source_options if isinstance(option, dict) and option.get("key")}
            self.assertEqual(len(source_by_key), len([option for option in source_options if isinstance(option, dict) and option.get("key")]), card_id)
            registry_options = item.get("options") or []
            registry_by_key = {str(option.get("key")): option for option in registry_options if isinstance(option, dict) and option.get("key")}
            self.assertEqual(set(source_by_key) - set(registry_by_key), set(), card_id)
            for key in source_by_key.keys() & registry_by_key.keys():
                if "default" in source_by_key[key]:
                    self.assertEqual(source_by_key[key].get("default"), registry_by_key[key].get("default"), f"{card_id}.{key}")


if __name__ == "__main__":
    unittest.main()
