import json

import pytest

from integrations.vgb.catalog import locked_cases


class Runtime:
    def metadata(self):
        return {
            "package": "vgb",
            "version": "rc",
            "tracks": ["open_generation_rdkit", "open_generation_xtb"],
        }

    def prompts(self, track):
        return [{"task_id": track + "_001"}]


def test_catalog_is_loaded_from_matching_runtime(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"vgb": Runtime().metadata()}))
    cases = locked_cases(Runtime(), lock, "open-generation")
    assert cases[1]["task_ids"] == ["open_generation_xtb_001"]
    lock.write_text(json.dumps({"vgb": {**Runtime().metadata(), "version": "old"}}))
    with pytest.raises(ValueError, match="differs"):
        locked_cases(Runtime(), lock, "open-generation")
