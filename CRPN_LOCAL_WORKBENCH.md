# CRPN 局部研究工作台

## 基线与边界

实际本地基线为 `fb5c42ad8cb31f075957243d491f3eb90528af77`，分支
`feature/crpn-danus-substrate`，开始时工作树干净，无后续提交需要回退。
本轮不 push，不做策略优劣对照，不改变自然语言 Verifier 的接受标准。
初始实现为 `a43dad6e7282bc81e73b4ab84c73900f6bf37388`。首次真实短验收的基础设施故障已冻结；修复后重新冻结源码，最终结果另行补入。

唯一数学权威仍是 `WORKSPACE/crpn.json` 内原有 Claim/Support AND/OR 图。
Selector、direct-first、3:1:1、Study、bridge、recurrence/helper/alias 和 COMPOSE
保持原规则。工具不是额外 Study 服务。Worker 可以请求 CRPN 准入，不能直接写图或撤销。

## 实际能力与直接复用

- LocalMemory.search 直接调用 DANUS BM25；精确记录通过既有 JSONL 读取，内容哈希定位，无新记忆库。
- GlobalMemory.search/read 仍提供有界 awareness，精确读回完整记录。研究记录始终不构成前提。
- fact_search/inspect 只发现和查看；proof_read 按字符范围分页完整证明，返回原 statement、scope、定义、来源、实际依赖、全文哈希及行位置。
- premise_request 从当前 CRPN 图检查精确 scope 和有效闭包，再交付完整前提接口。跨 scope 仍需原 bridge。
- candidate_submit 复用 CRPN Admission 和 fresh Verifier；返回完整反馈或图内证据 ID，Worker 可在当前会话继续。
- Verifier 只有明确列入本次候选的前提 proof_read，没有 memory/search/submit 能力，不继承 Worker 会话。

前提权限由原冻结 Worker packet 和其 DurableRounds 中已交付的 capability responses
重建；不存在新的 visible/known/displayed 权限表。每次实际使用重新检查图。正文中的中间
断言不会因为被读到而变成独立 Fact。

## 事务、恢复和计时

Research.step 用服务锁保持单调度拥有者，不跨模型调用持有数学事务锁。Admission 在独立
验证后重新读取当前图，在短事务内发布；外层 Worker 返回后刷新图，再提交一次原调度游标。
同一完整候选的内容与服务身份决定准入 key，重复工具请求以及重复的最终候选使用同一回执。
Worker 超时或中断后，已入图结果保留；仅恢复已有持久预约的准入，未知验证调用不重试、不猜成功。

DANUS DurableRounds 继续是唯一调用生命周期。其原调用目录新增实际工具 manifest、
capability 输入/输出和 timing evidence，与 request/result 一起校验哈希；没有另一套调用日志。
DANUS run_round 的隔离子进程句柄改为调用局部，避免嵌套 Verifier 覆盖外层进程。

默认每个角色仍为 600 秒，允许 CLI 按 worker/selector/verifier 配置并冻结入 fingerprint。
Worker 的非等待时间和同步验证等待分开记录；等待期间独立 Verifier 使用自己的期限。
MCP 等待为 verifier timeout + 60 秒；Node HTTP 代理显式设置期限，移除 fetch 隐含的较短
响应头期限。容器以 host heartbeat 约束孤儿进程，宿主继续负责超时和清理。
所有嵌套调用 tokens、等待及总墙钟都会计入；这一改动不构成数学收益证据。

DANUS 数学工作说明仅参考引用、证明组织、顺序审阅、定位与反馈部分，实际加载为
`contracts.WORKER` 和 `contracts.VERIFIER` 内的明确文本，并留在每份冻结 request。
没有加载 DANUS 主代理、任务分配、分解、选路、重试或分支淘汰流程；闭卷及无新增计算工具不变。

## 回归和真实验收协议

冻结前回归：**127 passed，1 skipped**（跳过默认关闭的 Docker 探针，后续以正式真实运行验收）。

回归覆盖完整工具链、跨 scope 拒绝、读取不授权、Verifier 最小权限、正文分页、反馈后继续、
重复请求、图刷新、撤销、准入三个中断边界、外层超时/中断、真实嵌套进程计时及角色配置漂移。
另支持将当前 authority-2 状态迁移到全新 runtime，保持证明及历史撤销字节，不重写旧证据。

预定真实验收：以已验收 `C:\n\ca2` 的 #67 多步局部研究状态作为只读起点。
先做一个普通服务的短验收，再从同一只读起点迁移另一新 workspace，执行正常五服务及至少
两个服务后的正式 pause/resume。两次均由原 Selector 选择工作，不指定数学路线、Fact、错误
证明或验证反馈。各角色 Sol/xhigh/600 秒；不因首个成果或超时提前结束，不重采直到成功。
自然未使用的工具按未实测报告。真值或状态完整性故障冻结证据。

最终将分别报告工具可用性、数学收益和验证可靠性，以及真实工具轨迹、成本和剩余限制。

## 已冻结的真实故障及修复

首次短验收 `6a97d56acd184c1991230a8492a9277e` 于 2026-09-22 12:11:52 UTC
停止，完成 0 个服务、0 次新证明准入。Windows `os.replace` 在 Docker 正读取 heartbeat
文件时返回 WinError 5，导致 Worker ERROR。这是本轮新增的心跳封装故障，不是数学失败。

保留 `C:\n\wb1` 和 `C:\n\wbo` 原始证据。共 2 次模型调用：Selector 已确认，Worker
未确认；已知 input 47,396 / output 1,381，Worker 用量 UNKNOWN。进程总墙钟 320.28 秒。
没有将 UNKNOWN 填零，也没有重放这次调用或把失败 workspace 改成新源码继续运行。

修复保持同一心跳文件，仅刷新 mtime，容器读取 stat；偶发刷新共享冲突计数并继续，连续
失去心跳仍受 30 秒孤儿 watchdog 约束。新增共享冲突回归验证文件身份不变且不杀死 Worker。
修复后完整回归 **128 passed，1 skipped**。所有失败和后续重新执行成本均计入最终报告。
这是明确基础设施修复后的重跑，不因工具未自然触发而重复采样。
