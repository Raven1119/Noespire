# CRPN 局部研究工作台验收报告

## 基线与实施边界

实际本地基线：`fb5c42ad8cb31f075957243d491f3eb90528af77`。开始时分支
`feature/crpn-danus-substrate` 干净，没有回退本地改动。
初始实现：`a43dad6e7282bc81e73b4ab84c73900f6bf37388`。
真实短验收及五服务周期实现：`7f20c4de03e5ab19aab5b9f8753be70c635d1f2a`。
最终代码实现：`458215642d23dd6caac7aa36138f4182412644eb`，包含运行后发现的参数反馈修复。
最终源码摘要：`f2dd2461d2cb742afa057323292131385afdcba48cf9274a3c92e75018d34a9e`。
正式复验冻结源码摘要：`2e4865b606e76f1c7fab7d80aea17cc478b2afb6b89adf37b7fbec1cbc96a72d`。
本轮只提交本地，不 push。

执行仍是 Windows Python 调度、Linux Docker 内 Codex Worker/Verifier，开发在 Linux。
模型 `gpt-5.6-sol`，effort `xhigh`；所有角色保持 600 秒非等待期限，MCP 工具等待 660 秒。
Docker 镜像 `sha256:5b56b18c4d75478a891d7cdbf01170085d3ab35ed4de38e1022337ae24b2dc46`、
Codex CLI `0.153.4` 不变。没有新 Python/npm 依赖、模型供应商抽象、外部文献检索或数学计算工具。

`source-boundary-audit.json` 对比基线确认：SELECTOR、PROBE、REPRESENTATION 指令以及
`scheduler.py`、`verification.py` 字节内容未变。`model.py` 只添加拒绝覆盖未保存修改的
`Network.refresh()`。AND/OR、direct-first、3:1:1、Study、bridge、recurrence/helper/alias
与 COMPOSE 的数学规则保留。

## 能力与直接复用

唯一事实权威仍是 `WORKSPACE/crpn.json` 内的 CRPN Claim/Support 图；新证明通过
`CRPN Admission` 写入，撤销仍走 CRPN。DANUS 不执行原生主 Agent、分配策略或自动事实准入。
派生卡片、BM25 命中、LocalMemory、GlobalMemory 和准入回执都不能自行改变真值。

| 能力 | 实现与边界 |
|---|---|
| 搜索自己的历史 | 直接调用 DANUS `LocalMemory.search` / BM25；只绑定当前 Study lane |
| 精确研究记录 | 既有 LocalMemory JSONL 内容哈希定位；`local_record`、`gm_read` 范围读取，无新记忆库 |
| 查看完整证明 | `proof_read` 每页最多 8,000 字符，返回全文哈希、范围、行位置以及完整命题、scope、定义、实际依赖、来源；可跟随 `next_start` |
| 动态合法前提 | `premise_request` 从当前图检查 scope 和有效闭包；跨 scope 保留原 bridge；单纯搜索/阅读不授权 |
| 会话内候选 | `candidate_submit` 接原 Admission 与 fresh Verifier，支持完整 Fact、条件 Support、原有 refutation/COMPOSE 约束；反馈包含明确理由或图内证据 ID |
| 独立验证材料 | Verifier 只收到候选、明确前提接口、验证目的；只可分页读这些前提的证明，没有搜索或研究记忆工具 |
| 研究接续 | 接受结果的工具回执可作为本次后续候选的合法前提来源；未完成推导继续写原 LocalMemory |

Worker 的实际工具清单为 `fact_search/inspect`、`proof_read`、`gm_search/read/add`、
`local_search/record/read/append`、`premise_request`、`candidate_submit`。每次实际绑定的
manifest、冻结指令和工具请求/返回均保存在原 DurableRounds 目录，不能仅凭代码存在宣称实测。

前提授权由冻结 Worker packet 和同一次调用中已交付的 capability responses 重建；没有
visible/known/displayed 权限表。实际提交再次检查当前图，撤销后不能继续使用。证明正文内
的中间断言不自动成为独立 Fact。初始 packet 上限 256,000 字节、单个工具结果 64,000 字节；
查询与分页按需进行，不自动灌入全部项目材料。

直接复用 DANUS 的 Local/GlobalMemory、BM25、WorkerLayout、DurableRounds、内容存储、
immutable/atomic IO、文件锁、Docker 隔离和现有回执。通用执行层只补足嵌套调用所需的
工具证据、等待计时、独立进程句柄和存活检测；没有另造调用日志或研究产物权威。

数学工作说明只取引用、证明组织、逐段核对、错误定位和反馈使用，实际放入冻结
`contracts.WORKER/VERIFIER`；未导入 DANUS 原生分解、选路、重试、淘汰指导。

## 事务、恢复和期限

`Research.step()` 以 `.service.lock` 保持一个调度拥有者，不跨模型调用持有数学事务锁。
Admission 持有本候选的原持久预约，独立验证后才短暂获取 `.crpn.lock`，刷新图并事务发布。
外层 Worker 返回后也刷新 Network，重新绑定 pending/control，最后只提交一次服务游标。
已经入图的结果不会被外层旧快照覆盖，也不依赖 Worker 最终输出是否成功。

准入 key 由原 round key 和完整候选内容决定。同一候选工具重发、最终输出原样重复，以及
确认后的恢复共用验证与准入回执。中断后只结算已经预约的提交；DurableRounds 中未确认的
调用不会猜测成功或自动再调用。语义相同但重新措辞的候选具有不同内容身份，仍可能重复花费
验证成本；本轮如实记录，不新增语义去重策略。

CLI 支持 `run/resume WORKSPACE --worker-timeout N --selector-timeout N --verifier-timeout N`；
未提供参数时恢复已有冻结配置，默认各为 600 秒。改变已有 workspace 的配置会 fail closed。
角色期限、MCP 期限和等待策略进入 runtime fingerprint。同步验证等待从 Worker 非等待
期限中扣除，但等待墙钟、Verifier 调用和 tokens 全部计入。Node HTTP 代理使用显式期限；
Verifier 保持独立期限。每轮记录 total wall / tool wait / non-wait，UNKNOWN 不填零。

## 回归

正式运行前回归：128 passed，1 skipped。最终代码回归：**130 passed，1 skipped**，13.75 秒。
命令与原输出见 `postrun_repair/regression.json/stdout/stderr`。
跳过的是默认关闭的 Docker 探针；下述正式运行实际使用了 Docker。

覆盖整条真实 broker HTTP 回调线程与 DurableRounds 链路：搜索、精确/分页读取、阅读不授权、
动态前提、跨 scope 拒绝、独立验证权限、拒绝定位后修正、接受后再推导、完全相同请求去重、
外层图刷新、一次游标提交、撤销、准入在验证确认/图发布/回执记录三处中断的恢复，以及
Worker TIMEOUT/INTERRUPTED 后保留已接受结果。还验证了真实嵌套子进程等待、进程句柄隔离、
角色配置漂移 fail closed、已入图 target 在中断后先完成当前服务，以及 Windows 心跳共享冲突。
这些测试中的数学判定是 fixture，不能当作 Verifier 可靠性证据。

支持将现有 `crpn-authority-2` 状态正式迁移到新 runtime；命题、证据 ID、正文、历史验收/
撤销、依赖、来源与记忆原字节保留。复验起点有 17 条有效证明、0 条撤销证明，所以真实运行
本身没有覆盖活跃撤销事件；撤销及 OR/AND/cycle/alias 语义由回归覆盖。

## 预注册与首次故障

只读起点为已验收的 `C:\n\ca2`（run `8b3211e1915f4c8ca25bd9f15065d7e0`），包含 #67
既有多步局部推导及未完成 AND 接口。先一个普通服务短验收，再从同一来源独立迁移五服务
周期；各次使用正式 `python -m crpn migrate/run/pause/resume`。不指定 Study、Fact 或路线，
不制造错误证明或反馈，不将短验收的新结果传给周期，不为触发工具重复采样。

首次短验收 run `6a97d56acd184c1991230a8492a9277e` 在 `a43dad6` 上失败：Windows
`os.replace` 替换 Docker 正读取的 heartbeat 文件时发生 **WinError 5**，Worker ERROR，
完成 0 服务/0 新证明。12:11:52 UTC 冻结 `C:\n\wb1` 和 `C:\n\wbo` 全部证据。
这是本轮新增执行封装的故障，不能归类为数学失败。

按照用户“遇到故障就修复并记录到报告”，改为固定心跳文件身份，只刷新 mtime；容器通过
stat 读取。短暂共享冲突计数并继续，连续 30 秒失去存活信号仍触发孤儿 watchdog。
添加回归后提交 `7f20c4de`，重新预注册并迁移新 workspace，没有在旧 runtime 中改源码续跑。
失败的 2 次调用和 Worker UNKNOWN 用量仍计入总成本。

## 真实短验收

Run `0aa4dfb444244d8a960d6a8487ef060d`，workspace `C:\n\wb2`：一个 ADVANCE 服务正常
停止，4 次 DurableRounds 调用（Selector 1、Worker 1、Verifier 2）。原图 17 条证明全部未变。

实际轨迹：Worker 使用 `local_search` 两次、`local_append` 一次、`candidate_submit` 一次。
独立 Verifier 在 Worker 尚未返回时接受 `94750362210ef975`；97.07 秒工具等待后，公开 MCP
结果与 broker 回执一致，Worker 最终 continuation 明确引用这一证据 ID。外层收尾后结果保留，
服务与调度游标各只提交一次。

Worker 又在最终输出中缩写重述同一结论，产生第二次验证与证据 `eb4fed9f57d85e33`。
这是两个不同候选的语义重复，不是同一请求重放；只计 **一项** 数学结果：有限端点从 1469
延至 1781，确定该固定 witness 在 1782 失效。目标仍 OPEN，没有全 B 证明或新证明接口。

这一短验收没有自然使用精确旧记录读取、proof_read、动态前提、拒绝后修正或接受结果后的
第二项推导；不能声称单次会话完整覆盖所有新能力。

## 正常五服务周期与真实暂停

Run `a6bdae930cb344ec96da673c2a6a7f4d`，workspace `C:\n\wb6`。从原只读起点新迁移，
未导入短验收结果。5 个真实 Worker 服务全部按正常调度执行：

| 服务 / 原 visit | 通道 | Study（末段） | 结果与数学分类 |
|---|---|---|---|
| 1 / 33 | ADVANCE | 9b4114… | COMPLETED；有限端点 1469 → 1781，固定 witness 在 1782 失效 |
| 2 / 34 | EXPLORE | 4a2283… | COMPLETED；重证已有 836 边界，显式写出二维 Gram kernel |
| 3 / 35 | REVISIT | 4a2283… | COMPLETED；复用上次结果重证已有 1469 边界及二维 Gram kernel |
| 4 / 36 | ADVANCE | 9b4114… | COMPLETED；暂停后复用服务 1 的结果，有限端点 1781 → 1808 |
| 5 / 37 | ADVANCE | 9b4114… | TIMEOUT；保存两条未验证研究笔记，无候选准入 |

第 2 个服务后发出正式 pause；当时第 3 个已开始，因此正常排空到第 3 个服务后退出。
13:11:00 UTC 原进程退出，438 个文件的快照连续 3 秒不变，无 DANUS 容器；13:11:03 UTC
正式 resume，以同一 run ID 继续。最终 13:35:14 UTC 停在五服务边界，pending=false。
visit 从 33 到 38，channel_cursor 从 32 到 37，各只推进 5 次。暂停前 124 个已确认 round/
submission 文件在恢复后全部不变，Local/GlobalMemory 原始前缀均保留。

同一 Study `study-ob-9b4114db9e727d0ccc1effc5` 在暂停前后使用原 lane，后续 packet 含已有
continuation，并交付原会话入图的 `08e1eca2a224858b`；不是重新编写的 handover。持久性属于
Study lane 和记忆，不声称不同服务共享一个永不结束的 Codex 会话。

原 17 条证明、历史与来源全部保持；新增 8 条证明记录是 4 对同义结果。每个 COMPLETED
Worker 都在工具接受后重写最终证明，分别触发独立验证；没有完全相同请求被重复验证或
重复发布，但存在明确的语义重复及其额外成本。新增 Support / Study 均为 0，bridge /
recurrence / COMPOSE 未自然触发。所有 graph validation 通过，目标仍 OPEN。

第五个 Worker TIMEOUT 的两条 `local_append` 回执与最终 LocalMemory 记录 ID 一致
（`b859e3b2…`、`73eed746…`）。这些笔记没有验证结果，不能计作新 Fact 或数学成果。
实际运行证明了超时后记忆保留；“同一 Worker 已接受结果后再超时”的组合由回归覆盖，
本次没有自然发生。运行后 CLI status 同样读取这张图；export 按既有规则拒绝导出未完成根目标。

## 局部注意力与实际工具覆盖

按预注册 seed `7f20c4de03e5ab19aab5b9f8753be70c635d1f2a:workbench-local-attention`
随机抽出的 3 个实际 Worker packets：

| visit | 数学 packet / 完整 prompt（UTF-8 字节） | 交付 Fact | 本 lane 记录曝光数 | 共享搜索返回数 / 唯一记录数 |
|---|---:|---|---:|---:|
| 33 | 92,872 / 96,258 | 72e68892873e4a53 | 9 | 30 / 13 |
| 34 | 48,249 / 51,635 | 28555270ab4db864 | 3 | 10 / 10 |
| 35 | 63,738 / 67,124 | 23c3b0837f86b65e | 6 | 20 / 12 |

曝光数包括多条 query 重复返回的记录，不等于全库唯一记录数。每次 query 最多 3 条本 lane
笔记及每个共享类别 3 条命中；每 packet 最多 3 条 query。本周期全部 5 个数学 packet 为
48,249–93,581 字节，均只交付 1 个 Fact 接口。完整结果 ID、类别、query、范围、工具清单、
指令与原始 prompt 留在 `supplemental-audit.json` 和 request evidence。没有全图 proof 对象、
其他 Study 的整份私有 LocalMemory、全库装载或新的真值权限表。DANUS 存储，CRPN 局部投影。

周期实际成功工具响应：local_search 2、gm_search 2、fact_inspect 1、local_append 6、
candidate_submit 4。15 条成功响应逐一与公开 MCP 记录一致；另有 1 次失败 gm_read，见下节。
短验收另有 4 条成功工具响应。公开轨迹中没有外部搜索、shell 数学计算、CAS 或额外 Agent。

| 能力 | 本轮证据 |
|---|---|
| 本地历史搜索、共享 awareness 搜索 | 真实成功 |
| 会话内 fresh Verifier、返回接受 ID、外层图刷新 | 短验收 1 次 + 周期 4 次真实成功 |
| 后续服务使用新 Fact、同 lane 记忆连续、正常 pause/resume | 真实成功 |
| 精确共享记录读取 | 真实请求因超限失败；最终修复后无模型回放成功 |
| local_record、proof_read、premise_request | 整链路与权限回归通过；未自然实测 |
| Verifier 按需 proof_read、拒绝后修正、接受后新推导 | 回归覆盖；未自然实测 |
| 重复请求、中断恢复、撤销后不能使用 | 回归覆盖；正常真实恢复未见重放 |

不能把工具 manifest 存在算作使用，也不能把收到接受反馈后结束会话算作完成第二项推导。

## 运行后材料读取故障及修复

审计发现 visit 35 的 Worker 请求 `gm_read(kind=conclusion, record_id=59ef1ee49e518ecd,
start=0, length=12000)`，超过公开 schema 的 8,000 字符上限。原代理只给出 `ValidationError`，
Worker 没有纠正重试。边界拒绝正确，但反馈不足，且这次 schema 拒绝未写入 capability journal
（公开 Codex log 保留了完整请求与失败）。没有材料交付、前提授权或误准入。

全部真实运行结束、原证据冻结后，以 `4582156` 修复：拒绝请求进入原 journal；只对工具公开
输入 schema 返回 `INVALID_ARGUMENTS`、字段路径、规则和允许值；MCP 保留这份结构化反馈。
内部 callback 异常仍只返回类型，不能借参数反馈泄露私有状态。页大小、权限、Verifier 与
研究策略不变，没有静默扩容或绕过校验。

原请求在复制状态上经过实际 Node MCP proxy + HTTP broker 无模型回放，收到
`path=[length], rule=maximum, expected=8000`；改为 8000 后读到完整 1,259 字符记录，原
workspace 哈希未变。新增回归还覆盖错误反馈后的连续分页和内部错误脱敏。最终实现未再跑
一轮数学采样，也没有宣称观察到真实 Worker 在该反馈后自行修正。新指纹对旧运行的恢复
在副本上 fail closed；未原地重启旧实验。

审计辅助脚本的问题另行记录：Windows 默认 GBK 读取 UTF-8、跨环境 `python` 路径、以及
误以为 OPEN target 可以 export。分别改用显式编码/解释器和既有 export 拒绝断言；这些修复
没有修改 CRPN 数学语义，也没有新增模型调用。


## 调用、用量与墙钟

| 实验 | 模型调用 | 已知 input（含 cached） | cached 子集 | 已知 output | UNKNOWN 调用 | 运行墙钟 |
|---|---:|---:|---:|---:|---:|---:|
| 首次故障短验收 | 2 | 47,396 | 0 | 1,381 | 1 | 320.28 s |
| 修复后短验收 | 4 | 377,168 | 264,064 | 23,566 | 0 | 803.84 s |
| 五服务周期 | 21 | 1,445,852 | 913,024 | 79,896 | 1 | 3,808.78 s |
| **合计** | **27** | **1,870,416** | **1,177,088** | **104,843** | **2** | **4,932.91 s** |

Calls 指 DurableRounds 的 Codex 模型会话：Selector 10、Worker 7、Verifier 10，包含失败和
超时。provider 内部 HTTP/推理往返次数没有单独暴露。已知 token 合计不是完整费用估计：
两次 UNKNOWN 仍保留为未知，没有填零。一次服务内的工具使用计入该 Worker 的累计 usage，
嵌套 Verifier 另计。

同步验证等待合计 **525.26 秒**，已包含在实际运行墙钟中。各调用 wall 相加为 5,440.72 秒，
其中嵌套等待会重复包含 Verifier 时间；扣除这层重叠为 4,915.46 秒，不能把原始相加值冒充
端到端时间。所有原始逐轮 timing 保留。表中运行墙钟包含正常排空/暂停恢复，不包括开发、
回归和审计耗时。运行后修复的确定性工具回放新增模型调用为 **0**。

## 结论与限制

**工具与执行：** 工程闭环可用。完整链路、权限、恢复和等待边界通过回归；真实一服务短验收、
正常五服务周期、真实 pause/resume、独立会话内准入及超时记忆保留完成。首次 Windows
心跳故障和最终发现的材料读取反馈问题均已修复、记录并回归。真实周期的失败参数读取
不是成功读取；最终修复仅有无模型真实代理回放证据，没有追加数学采样。

**数学收益：** 有有限端点延伸，但没有证明工作台提升研究质量或解题率。EXPLORE/REVISIT
重复了已有有限边界；所有成功 Worker 在收到反馈后都结束了本次推导，并重述同义候选，
额外消耗一次验证。没有观测到会话内新 Fact 再用于第二项推导，也没有新 all-B 证明、
新证明接口或整类方法的不可能性结论。不能用 10 条新证明记录（短验收 2 + 周期 8）计作
10 项研究进展，更不能用总墙钟变长证明能力提升。

**验证可靠性：** 仍是独立自然语言 LLM Verifier。审阅这些有限计算与已接受证明未发现明显
错误，但没有形式核验或估计错误率。没有人为错误证明、注入反馈、多数投票或新的 Truth Gate
实验。未自然触发的读取/动态授权/反馈修正继续能力明确保持“仅回归覆盖”。

保留本轮工具与执行修复，不改变 CRPN 策略。CRPN 继续决定研究什么、什么能作前提以及
什么进入唯一 AND/OR 图；Worker 已有材料访问、动态授权和即时独立反馈的可用入口。
下一步应依据新的预注册研究任务观察尚未触发的完整会话接续，不能把本轮重采直到成功，
也不能据此作策略优劣结论。


## 证据与交付位置

主报告随代码提交为 `CRPN_LOCAL_WORKBENCH.md`。完整证据保存在：

- Windows 原始运行：`C:\n\wb1`（故障）、`C:\n\wb2`（短验收）、`C:\n\wb6`（五服务）。
- 预注册、迁移对照、原始运行审计：`C:\n\wbo`、`C:\n\wbo2`。
- 最终代码回归、原请求回放、CLI/指纹检查与源代码归档：`C:\n\wbo3`。
- Linux 完整副本：`/home/wmywb/Noespire/experiments/crpn_local_workbench/evidence/`。
  包含 `failed_attempt_audit`、`failed_attempt_workspace`、`accepted_attempt_audit`、
  `accepted_short_workspace`、`accepted_cycle_workspace`、`postrun_repair`。

共 **4,606 个文件**，复制前后与副本逐文件 SHA-256 一致。
`MANIFEST.json` 的 SHA-256：`2f3babea26bcb132f776dd8df9cb3606fd6b3b179eb214ca6487b329063e958f`。
索引与核对结果为同目录上一层的 `INDEX.md`、`archive-verification.json`、`final-accounting.json`。

保留了初始/暂停/最终状态、完整 proof 与历史、所有 request/result/public log、实际指令和
工具 manifest、能力调用及回执、准入预约/独立验证/发布回执、Local/GlobalMemory、
迁移 source blobs、错误、timeout、用量和 timing。首次预创建但未运行的 `C:\n\wb5`
也保留，没有模型调用。最终代码与报告均本地提交，未 push。
