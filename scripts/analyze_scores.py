#!/usr/bin/env python3
"""分析实验结果中的 VGB 分数分布"""

import json
from pathlib import Path

# 找到所有任务目录
job_dir = Path('run-artifacts/formal/claude-code-deepseek-repeat1/jobs/claude-code-vgb-deepseek-cross-provider-skills_off')

# 收集成功任务的分数
scores = []
for result_file in job_dir.glob('*/result.json'):
    try:
        result = json.loads(result_file.read_text())
        # 检查 verifier_result.rewards.vgb_score
        if result.get('verifier_result') and result['verifier_result'].get('rewards') and result['verifier_result']['rewards'].get('vgb_score') is not None:
            task_id = result_file.parent.name
            scores.append({
                'task': task_id.split('__')[-1],
                'type': 'advanced' if 'advanced' in task_id else 'basic',
                'score': result['verifier_result']['rewards']['vgb_score']
            })
    except Exception as e:
        print(f"Error reading {result_file}: {e}")

# 按分数排序
scores.sort(key=lambda x: x['score'], reverse=True)

print('=== Top 10 任务 (按 VGB 分数) ===')
for i, s in enumerate(scores[:10], 1):
    print(f'{i}. {s["task"]} ({s["type"]}): {s["score"]:.3f}')

print('\n=== Bottom 10 任务 ===')
for i, s in enumerate(scores[-10:], 1):
    print(f'{i}. {s["task"]} ({s["type"]}): {s["score"]:.3f}')

print(f'\n=== 分数分布 ===')
print(f'完美分数 (1.0): {sum(1 for s in scores if s["score"] == 1.0)} 个')
print(f'高分 (0.8-1.0): {sum(1 for s in scores if 0.8 <= s["score"] < 1.0)} 个')
print(f'中高分 (0.6-0.8): {sum(1 for s in scores if 0.6 <= s["score"] < 0.8)} 个')
print(f'中等分 (0.4-0.6): {sum(1 for s in scores if 0.4 <= s["score"] < 0.6)} 个')
print(f'中低分 (0.2-0.4): {sum(1 for s in scores if 0.2 <= s["score"] < 0.4)} 个')
print(f'低分 (0.0-0.2): {sum(1 for s in scores if 0.0 <= s["score"] < 0.2)} 个')

print(f'\n=== 按任务类型统计 ===')
advanced_scores = [s['score'] for s in scores if s['type'] == 'advanced']
basic_scores = [s['score'] for s in scores if s['type'] == 'basic']

if advanced_scores:
    print(f'Advanced 任务: {len(advanced_scores)} 个, 平均分: {sum(advanced_scores)/len(advanced_scores):.3f}')
if basic_scores:
    print(f'Basic 任务: {len(basic_scores)} 个, 平均分: {sum(basic_scores)/len(basic_scores):.3f}')
