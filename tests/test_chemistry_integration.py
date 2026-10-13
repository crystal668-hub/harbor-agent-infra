from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from integrations.vgb.chemistry import (
    controlled_environment,
    preflight_chemistry,
    runtime_settings,
)
from integrations.vgb.runtime import VgbRuntime

pytestmark = pytest.mark.integration


def runtime():
    python = os.environ.get("VGB_PYTHON")
    if not python:
        pytest.skip("VGB_PYTHON and provisioned chemistry environment required")
    return VgbRuntime.from_executable(python)


def test_actual_image_and_verifier_match(tmp_path):
    report = preflight_chemistry(
        runtime(), Path("runtime-lock.json"), output_path=tmp_path / "chemistry-preflight.json",
    )
    assert report["status"] == "passed"
    assert report["agent"]["parameters"] == report["verifier"]["parameters"]


def test_crest_and_xtb_work_in_the_same_controlled_environment():
    vgb = runtime()
    prefix, _ = runtime_settings(vgb.python_executable)
    code = r'''
import json, tempfile
from pathlib import Path
from unittest.mock import patch
from rdkit import Chem
from rdkit.Chem import AllChem
from verifier_grounded_benchmark.evaluation import external_dependencies as dependencies
from verifier_grounded_benchmark.evaluation.open_generation.verifiers.xtb.crest_pyrene import (
    CrestRunner,
)
from verifier_grounded_benchmark.evaluation.open_generation.verifiers.xtb.backend import (
    XTBRunner, parse_xtb_output,
)
import os, shutil
with patch.object(dependencies, '_find_conda_environment', side_effect=AssertionError('fallback')):
    dependencies.preflight_external_dependencies([{'external_dependencies':[
        {'executable':'crest','version':'2.12','conda_environment':'vgb-crest'},
        {'executable':'xtb','version':'6.7.1','conda_environment':'vgb-crest'},
    ]}])
mol=Chem.AddHs(Chem.MolFromSmiles('CCO'))
assert AllChem.EmbedMolecule(mol, randomSeed=61453)==0
AllChem.MMFFOptimizeMolecule(mol)
spec={'backend':{'method':'GFN2-xTB','threads':1,'search_level':'-mquick',
                 'xtb_executable':shutil.which('xtb')}}
with tempfile.TemporaryDirectory() as temp:
    work=Path(temp)
    search=CrestRunner().search(Chem.MolToXYZBlock(mol), work, 90, spec=spec)
    assert search.conformers
    selected=min(range(len(search.conformers)),key=lambda i: search.relative_energies[i])
    xyz=work/'selected.xyz'; xyz.write_text(search.conformers[selected])
    result=XTBRunner().run('singlepoint',xyz,30,spec=spec)
    assert result.returncode==0
    print(json.dumps({'conformers':len(search.conformers),
                      'energy':parse_xtb_output(result.stdout)['total_energy_hartree']}))
'''
    env = controlled_environment(prefix)
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    result = subprocess.run(
        [str(vgb.python_executable), "-c", code], env=env,
        capture_output=True, text=True, timeout=150,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["conformers"] > 0


def test_real_vgb_evaluation_uses_controlled_chemistry():
    result = runtime().evaluate(
        "open_generation_rdkit",
        {"task_id": "rdkit_001_qed_max", "candidates": [{"smiles": "CCO"}]},
    )
    assert result["status"] == "scored"
