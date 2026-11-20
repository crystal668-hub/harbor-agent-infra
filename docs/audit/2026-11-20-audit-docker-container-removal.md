# 孤儿容器存储回收与Docker删除阻塞诊断

日期：2026-11-20（Asia/Shanghai）
类型：audit
状态：已定位并等待旧层GC完成；自动删除、手动删除及完整化学预检均恢复通过，诊断容器已清理。

## 存储是否释放

两个旧实验容器已从Docker容器列表删除。清理前宿主机Data可用约39GiB；
16:11核对时可用约48GiB，Docker容器占用仅剩1.876MB的既有历史容器。
后台回收继续推进后，可用空间进一步达到约58GiB，Docker.raw实际分配约25.4GiB。
Docker.raw逻辑上限仍为128GiB，这是稀疏磁盘容量上限，不是实际宿主机占用。
宿主机空间变化包含同期后台回收，不将每一字节差异全部归因于两个容器本身。
镜像8.058GB和构建缓存11.41GB本次未清理。

## 最小复现与阻塞位置

用本地原锁定镜像、关闭网络、仅打印固定文本：

| 操作 | 观测 |
| --- | --- |
| 不带自动删除的docker run | 约0.16秒正常返回，exit 0 |
| 对已退出容器执行docker rm | 12秒观察窗口超时，进入removing |
| docker run --rm | 已输出文本、进程exit 0，但12秒窗口仍未返回，容器removing |

因此现象不局限于`--rm`，是共享的容器层释放路径等待，不是Agent未退出或预检计算失败。
抓取Docker及containerd官方SIGUSR1线程栈，等待链如下：

```text
dockerd cleanupContainer / autoRemove
  → ImageService.ReleaseLayer
  → containerd leases.Delete（同步等待垃圾回收）
  → gcScheduler.ScheduleAndWait
  → metadata.DB.GarbageCollect / WaitGroup
  → overlay.snapshotter.Cleanup
  → os.RemoveAll / unlinkat
```

containerd还在执行递归删除，未证实存在永久锁死。它正在删除旧可写层snapshot 15143中的
`/tmp/solv/wk`；通过进程已打开的目录FD将阻塞位置定位到该目录及不同`slot*`子目录。
这一GC等待让无关的微型诊断容器删除也排队，从而使化学预检的`docker run --rm`
超过90秒时限。之前反复重启只能暂时解除容器状态，不能消除尚待回收的大量目录。

## 目录数量异常的来源

Basic 002旧Trial UUID为`a3899d7d-0c33-416f-9428-7a846eec37b4`，
其已归档会话保存Agent生成的`/tmp/solv/scripts/popt.py`修改：

```python
def _dir_for(self, idx):
    while len(self.dirs) <= idx:
        k = len(self.dirs)
        d = os.path.join(self.root, f"slot{k}")
        os.makedirs(d, exist_ok=True)
        self.dirs.append(d)
    return self.dirs[idx]

def energy(self, coords):
    return self._one((100000, coords))

def full_report(self, coords):
    d = self._dir_for(100001)
```

`_one`调用`_dir_for(idx)`。高编号被当作连续列表下标，因此单个工作根目录会创建
slot0至slot100000/100001，共100001/100002个目录。多个不同计算工作根重复这一行为，
导致旧层包含数百万目录；采样的部分slot目录为空，空目录仍消耗inode和删除操作。
这是该Trial中Agent生成计算脚本的目录分配问题，不能表述为Harbor代码生成了这些目录。

一次只读盘点仍有2,282,664个slot目录；153.17秒后的盘点为1,231,811个，
至少1,050,853个已被删除。containerd读取字节数及正在遍历的目录同时变化，
证明回收持续推进。该计数是回收中的剩余量，不是原始总量，也不是逐目录字节归因。

## 处置边界

- 保留原始实验会话、评分和归档结果，不修改已冻结Agent脚本或实验条件。
- 不再反复重启打断本轮回收，让GC清理完成后复测容器自动删除与正式化学预检。
- 本次只创建命名明确、无网络的诊断容器；导出线程栈的容器临时使用host PID命名空间，
  读取进程根目录时临时添加SYS_PTRACE，未改Docker配置或持久权限。
  仅删除本次创建的诊断容器，保留既有历史容器、镜像和缓存。
- 后续计算脚本应使用有界worker目录池或按实际索引直接创建单个目录，
  不为稀疏高编号补齐全部中间目录；任何正式实验条件变更仍需另行记录。
- 本次是诊断与回收验证，不自动改写campaign manifest或启动实验。

## 最终验证（16:22，上海）

不再重启打断回收后，旧层的目标目录已删除，排队的容器删除请求陆续完成。
自动删除微型容器0.146秒返回0，普通微型容器0.141秒返回0、手动删除0.027秒返回0；
原锁定镜像及VGB runtime的完整`preflight_chemistry`通过。
这证实本次故障为旧层数百万目录GC导致同步删除等待，不是已确认的永久死锁。

宿主机Data最终可用约62GiB，相比此前39GiB约增加23GiB；
Docker.raw实际分配22,076,579,840字节（约20.6GiB），逻辑上限仍128GiB。
Docker容器列表只保留既有`review_system-review-system-1`历史退出容器，
旧实验孤儿及全部本次诊断容器均不存在。镜像和构建缓存占用保持不变。
campaign本次未重新启动，9项有效完成结果和29项待执行范围不变。

[最终验证与存储测量](../../run-artifacts/audit/docker-auto-remove-20261120/final-verification.json)
及[完整化学预检](../../run-artifacts/audit/docker-auto-remove-20261120/chemistry-preflight-after-gc.json)
已保存。后续可按已有授权清单续跑；不应为本次已消失的GC等待关闭预检或改实验镜像。

证据：[最小复现](../../run-artifacts/audit/docker-auto-remove-20261120/reproduction.json)、
[dockerd删除栈](../../run-artifacts/audit/docker-auto-remove-20261120/removal-stacks.log)、
[containerd回收栈](../../run-artifacts/audit/docker-auto-remove-20261120/containerd-gc-stacks.log)、
[目录索引触发代码](../../run-artifacts/audit/docker-auto-remove-20261120/scratch-index-trigger.json)、
[首次目录盘点](../../run-artifacts/audit/docker-auto-remove-20261120/snapshot15143-all-counts.json)、
[后续回收进度](../../run-artifacts/audit/docker-auto-remove-20261120/gc-progress-latest.json)、
[存储测量](../../run-artifacts/audit/docker-auto-remove-20261120/storage-and-progress.json)。
