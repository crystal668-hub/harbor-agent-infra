# 预装 harness 镜像运维

正式 Trial 使用 runtime-lock.json 的 per-harness 预装镜像。
下载发生在构建阶段；Harbor 仍调用 agent.setup()，但只校验实际程序身份和必要本地初始化。
缺失、错版、路径漂移或文件篡改导致失败，不自动联网补装。

## 输入与身份

| 输入 | 用途 |
| --- | --- |
| [runtime-lock.json](../runtime-lock.json) | base image、harness 发布身份及 harness_images |
| [images/harness/build-inputs.json](../images/harness/build-inputs.json) | 公开安装来源、校验值和构建输入 |
| 镜像内 /opt/hai/harness-manifest.json | 实际版本、入口、依赖、安装文件集合和允许的条件补丁哈希 |

harness_images 按 openclaw、hermes、codex、claude-code 索引，包含 reference、digest、platform、
version、manifest_sha256；Hermes 额外记录 source_commit。确切版本和 digest 读取锁文件，
不在手册重复维护。执行以不可变身份为准，名称中含 latest 也不能作为自动选择新版本的依据。

构建上下文不包含 provider 凭据、实验技能、题面或本机用户配置。
最终 image digest 在构建后确定，不写回镜像自身清单形成自引用。
本地可用不代表 Registry 可拉取；迁移 Docker 主机前核对发布身份和可用性。

## 构建候选

使用独立工作区、Python 3.12 和 locked uv 环境。构建器拒绝在有活跃 Docker 容器时开始，
避免与实验争用；为候选使用新名称和新输出位置，不覆盖运行中的镜像和配置。

    uv run --locked --python 3.12 python scripts/build_preinstalled_image.py codex \
      --reference hai-candidate-codex --output-dir outputs/preinstalled

其他 harness 使用相同入口。--lock 可传入上一候选输出的锁，逐步加入其他执行镜像；
默认读取根锁。输出含安装清单、构建元数据和候选锁，不改写根锁或自动推送 Registry。
基础镜像须在本地通过身份验证；构建临时名称指向已验证 image ID，结束后核对并清理该名称。

Hermes 还固定实际依赖和 PM 环境，并通过 HERMES_DISABLE_LAZY_INSTALLS=1 禁止首次启动重建依赖。
验收包括普通 sessions list，不能只依赖 --version。仅明确允许的运行期字节码指纹和租约/锁
不参与不可变比较，源码和应用依赖仍校验。
--reuse-installed 仅用于已验证的 Hermes 候选修订，须传候选锁并生成新名称、新 digest；不覆盖原候选。

## 离线验收

    LITELLM_LOCAL_MODEL_COST_MAP=True uv run --locked --python 3.12 \
      python scripts/verify_preinstalled_image.py codex \
      --lock outputs/preinstalled/codex-runtime-lock.json \
      --output-dir outputs/preinstalled/codex-offline --concurrent 2

通过真实 Harbor install_only 创建两个新容器，Compose network_mode=none；
healthcheck 在 setup 前确认外网不可达。每次使用新证据目录，失败记录保留。
完整候选锁还需运行 provider-free Docker 门禁：

    RUN_PREINSTALLED_IMAGE_GATES=1 \
    PREINSTALLED_RUNTIME_LOCK=/absolute/path/to/candidate-runtime-lock.json \
    PREINSTALLED_GATE_OUTPUT_DIR=outputs/preinstalled/docker-gates \
    LITELLM_LOCAL_MODEL_COST_MAP=True \
    uv run --locked --python 3.12 pytest -m integration \
      tests/test_preinstalled_image_integration.py

门禁包括离线 setup、化学环境一致性和错版、错清单、缺失、路径漂移、篡改负例。
完整验收必须覆盖锁中的全部目标 harness，缺项 skip 不能计为通过。
此门禁不调用模型；provider-free 单元测试与 Docker 集成测试分别执行。

## 生成独立配置

experiment.agent.installation_mode 设置为 preinstalled，experiment.image 必须是该 harness 的
执行镜像，不是父镜像；材料化、预检和运行证据使用相同身份。

    uv run --locked --python 3.12 python scripts/prepare_preinstalled_run.py \
      examples/experiments/codex/vgb-gpt.config.yaml \
      --lock /absolute/path/to/candidate-runtime-lock.json \
      --output outputs/preinstalled/codex-gpt.config.yaml \
      --run-directory run-artifacts/temporary/codex-preinstalled-check

先设置模板所需环境变量。生成器验证展开后的配置，但输出保留变量引用，不复制凭据；
拒绝覆盖已有配置或运行目录。生成配置仅含 skills_off，不会启动实验。

    uv run --locked --python 3.12 hai materialize \
      --config outputs/preinstalled/codex-gpt.config.yaml \
      --output outputs/preinstalled/codex-gpt-materialized.json
    uv run --locked --python 3.12 hai run \
      --config outputs/preinstalled/codex-gpt.config.yaml --group skills_off

最后一条会启动真实验收并可能调用 provider/VGB，候选运行不写回正式实验。
scripts/verify_preinstalled_matrix.py 用于单独的 provider/VGB 工程验收，支持 --harness / --provider
子集；它会添加验收 instruction prefix，不能把结果当作原正式题面下的成绩。
子集通过也不能代表完整矩阵。实验条件与化学要求分别引用
[实验方案](experiments/formal-experiment-plan.md)、[化学配置](experiments/chemistry.md)。

## 交付、切换与故障处理

每 Trial 的 agent/harness-setup.json 和正常执行结束的 agent/harness-final.json
记录实际版本、入口、运行时、安装摘要、补丁与镜像身份；配置中的版本字段不构成实际版本证明。

切换前核对候选身份、完整门禁证据及目标配置。已有运行继续使用冻结条件；
新锁或镜像不自动用于旧 slot 的恢复。涉及恢复条件变化时遵循 [恢复手册](RECOVERY-SYSTEM-GUIDE.md)。
回滚须使用仍可用且匹配的代码、锁和镜像组合，不能假定已退役镜像可重新取得。
setup 漂移应检查版本、路径和 manifest，不通过联网重装绕过；保留失败证据，不替换运行中的容器。

实现入口：[build_preinstalled_image.py](../scripts/build_preinstalled_image.py)、
[preinstalled.py](../adapters/preinstalled.py)、[preinstalled_probe.py](../adapters/preinstalled_probe.py)。

## 镜像退役与运行锁清理

### 2026-10-26 清理记录

以下为已执行的运维记录，不是再次删除镜像的指令；当前执行身份仍以运行锁为准。

日期：2026-10-26。用户确认无需复现或恢复使用旧镜像的历史运行，并授权清理。

唯一活动锁为 [runtime-lock.json](../runtime-lock.json)，内容逐字节来自原 runtime-lock.preinstalled.json，SHA256 为 17b64c39058302a948d17ebf3d022c07231460d4bac46ed93660efb1229ec8bf。旧默认锁移除，正式入口、配置更新器、测试及本机 16 份正式配置同步改用唯一锁。四个 harness 的 digest、manifest、版本、父镜像及化学身份未更改。

本次定向删除两个已退役 OpenClaw 镜像：

- sha256:485e1ca1e3962aedc59a7b1486c652a47f0028f2c71c60924ab767a4f276f83f
- sha256:083e6590790627b6f35dc4b771d89d635e724b5b28f29037ea55746c9e05f54f

该次清理保留 OpenClaw sha256:d744a3474f60e123a86f4c9dcb314c12810104e290eb982ac556ecff32c4255c、Claude Code、Codex、Hermes、共用基础及其他项目镜像；不执行全局 prune。

历史运行说明：该镜像已作为旧版本被更新，并没有发生实验条件上的变化。这里指本次清理和锁文件改名没有改变已完成运行的条件或结果；历史运行的原镜像身份、配置、锁快照和恢复证据保持原样。此前补跑中已经记录的镜像切换仍按原 condition-change 证据解释，不能据此宣称不同 digest 的执行环境完全相同。

旧锁路径在历史产物中仅作为原始证据保留，不添加兼容链接，也不把历史任务重绑定到新锁。历史锁内容仍可通过 Git 历史查阅；不再支持从已删除的本机旧镜像恢复运行。
