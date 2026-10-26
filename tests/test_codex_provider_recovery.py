from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test_codex_config import custom_spec

from harbor_agent_infra.contracts.experiment import AgentSpec
from harbor_agent_infra.contracts.failure_types import FailureCategory, FailureClassification
from harbor_agent_infra.harbor.job_config import JobConfig
from harbor_agent_infra.harness_runner import harness_runner_for
from harbor_agent_infra.preparation.runtime_lock import load_runtime_lock
from harbor_agent_infra.recovery.codex_provider import SCHEMA
from harbor_agent_infra.recovery.executor import RecoveryExecutor
from harbor_agent_infra.recovery.manifest import RecoveryManifest, RecoverySlot
from harbor_agent_infra.recovery.native_plan import _is_authorized_condition_change


@pytest.fixture(params=['deepseek', 'qwen'])
def configured_recovery(request, tmp_path):
    spec = AgentSpec(**custom_spec(request.param, installation_mode='preinstalled'))
    lockpath = Path('runtime-lock.json').resolve()
    lock = load_runtime_lock(lockpath)
    target = harness_runner_for('codex').build_agent_config(spec, lock)
    old = target.model_copy(deep=True)
    old.kwargs.pop('config')
    original = JobConfig(
        agents=[old], tasks=[{'path': str(tmp_path / 'track__task')}],
        n_concurrent_trials=2, n_attempts=1, retry={'max_retries': 0},
    )
    slot = RecoverySlot(
        'original-job', 'track__task', 'trial-uuid',
        FailureClassification(FailureCategory.ENGINEERING, 'remote compact format', True, {}),
        original_run='original-run', approved=False,
    )
    change = {
        'schema_version': SCHEMA, 'condition_id': 'codex-custom-responses',
        'authorization': 'Configure custom provider; execution needs separate slot approval',
        'statistical_role': 'new_condition_observation',
        'task_names': [slot.task_id], 'agent_spec': spec.model_dump(mode='json'),
    }
    manifest = RecoveryManifest('original-run', None, datetime.now(), slots=[slot],
                                metadata={'condition_change': change})
    run_config = SimpleNamespace(experiment=SimpleNamespace(
        agent=spec, groups=[SimpleNamespace(id='skills_off')],
        benchmark=SimpleNamespace(package_lock=str(lockpath)),
        image=SimpleNamespace(digest=lock.execution_image('codex', 'preinstalled').digest),
    ))
    executor = RecoveryExecutor(manifest, run_config, tmp_path / 'not-created')
    executor._load_original_job_config = AsyncMock(return_value=original)
    return executor, original, target, slot


@pytest.mark.asyncio
async def test_prepare_preserves_frozen_job_and_applies_provider(configured_recovery):
    executor, original, target, slot = configured_recovery
    before = original.model_dump(mode='json')
    with patch('harbor_agent_infra.recovery.executor.Job.create', new_callable=AsyncMock) as create:
        result = await executor.prepare_job_config(slot)
        create.assert_not_called()
    assert result.agents[0] == target
    assert result.tasks == original.tasks
    assert result.environment == original.environment
    assert result.n_concurrent_trials == original.n_concurrent_trials
    assert original.model_dump(mode='json') == before
    assert not executor.output_dir.exists()
    # Config approval must never implicitly approve execution.
    outcome = await executor.execute()
    assert outcome.executed == 0
    assert not executor.output_dir.exists()


@pytest.mark.asyncio
async def test_stale_manifest_cannot_silently_keep_old_provider(configured_recovery):
    executor, _, _, slot = configured_recovery
    executor.manifest.metadata.clear()
    with pytest.raises(ValueError, match='explicit condition_change'):
        await executor.prepare_job_config(slot)


@pytest.mark.asyncio
@pytest.mark.parametrize('drift', ['model', 'effort', 'image', 'config', 'scope', 'declaration'])
async def test_provider_transition_rejects_other_changes(configured_recovery, drift):
    executor, original, _, slot = configured_recovery
    if drift == 'model':
        original.agents[0].model_name = 'other-model'
    elif drift == 'effort':
        original.agents[0].kwargs['reasoning_effort'] = 'low'
    elif drift == 'image':
        original.agents[0].kwargs['preinstalled']['image'] = 'other@sha256:' + 'a' * 64
    elif drift == 'config':
        original.agents[0].kwargs['config'] = {'model_provider': 'unrelated'}
    elif drift == 'scope':
        executor.manifest.metadata['condition_change']['task_names'] = []
    else:
        executor.manifest.metadata['condition_change']['agent_spec']['codex_config'][
            'model_provider'
        ] = 'openai'
    with pytest.raises(ValueError):
        await executor.prepare_job_config(slot)


@pytest.mark.asyncio
async def test_changed_provider_metadata_persists_on_approved_mock_run(configured_recovery):
    import json

    executor, _, target, slot = configured_recovery
    executor.manifest.approve_slot(slot.slot_id)
    job = AsyncMock()
    job.run.return_value = MagicMock(stats=MagicMock(n_errored_trials=0, n_cancelled_trials=0))
    with patch('harbor_agent_infra.recovery.executor.Job.create', new_callable=AsyncMock) as create:
        create.return_value = job
        outcome = await executor.execute()
    assert outcome.succeeded == 1
    saved = create.await_args.args[0]
    assert saved.agents[0] == target
    metadata = json.loads((saved.jobs_dir / saved.job_name / 'recovery-metadata.json').read_text())
    assert metadata['condition_change']['schema_version'] == SCHEMA
    assert metadata['statistical_role'] == 'new_condition_observation'


def test_merge_recognizes_only_the_declared_provider_change(configured_recovery):
    executor, original, target, slot = configured_recovery
    old = {'config': {'agent': original.agents[0].model_dump(mode='json')},
           'task_checksum': 'unchanged'}
    new = deepcopy(old)
    new['config']['agent'] = target.model_dump(mode='json')
    change = executor.manifest.metadata['condition_change']
    assert _is_authorized_condition_change(old, new, slot.task_id, change)
    new['task_checksum'] = 'different-task'
    assert not _is_authorized_condition_change(old, new, slot.task_id, change)
    new['task_checksum'] = old['task_checksum']
    new['config']['agent']['kwargs']['reasoning_effort'] = 'low'
    assert not _is_authorized_condition_change(old, new, slot.task_id, change)
