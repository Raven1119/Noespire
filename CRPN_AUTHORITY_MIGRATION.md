# CRPN 唯一事实权威：架构、迁移与真实验收

结论：**权威收敛通过验收。** 数学状态由 CRPN 的 Claim/Support AND/OR 图掌握；DANUS 提供基础工具。完成五个正常 Study services、正式 pause/resume，未发现生产 runtime 或真值完整性 blocker。两处外部审计器错误及由此增加的一次暂停完整保留，见下文。

## 实际基线与源码

- 原本地 HEAD：`35a898bb5c3c5e59922f0cfdc9e53cc0472fe941`。
- 当时已通过真实验收的权限补丁 SHA-256：`7a71ecceed03c55d01aa721c89a06d54b75d6dfd51e086cd5195a45f25c97b27`。
- 将该补丁原样提交后的基线：`a67ac3c44dd35d290959f7db6d31cf92b41397e8`。
- 本轮实现与真实运行源码：`97eb403685ddea33aba0f50023d60ee059675a38`。
- 运行源码指纹：`9addd0d4ccef460b2035032403804a7688f43a490333a1c8d537eea7630da0a3`。
- DANUS 上游出处仍为 `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`，许可证和 vendor 历史保留。

未回退 GitHub 版本，未 push。开发在 Linux 中进行；正式 CLI 在 Windows 运行，Codex 进程在原有 Linux Docker 镜像中运行。本轮没有策略优劣对照或 Truth Gate 提示研究。

## 唯一事实图在哪里，谁能改变它？

唯一数学权威是 `WORKSPACE/crpn.json`，schema 为 `crpn-authority-2`，由 `src/crpn/model.py::Network` 实现。在原 Claim/Support 图内扩展证明归属：

| 图内位置 | 含义 |
|---|---|
| Claim `proofs` | 该精确作用域命题的备选证明，构成 OR |
| Claim `refutations` | 该命题的精确否定证明 |
| Support `certificates` | 条件证书及其 representation/helper 传输证书 |
| 证明记录 | 原证据 ID、正文、实际前提、作者、历史验收、来源、状态、撤销历史 |

不再有独立 FactGraph 文件库、`fact_bindings` 真值表或顶层 refutation 真值表。证据查找、BM25 结果和材料卡是此图的派生视图。新 workspace 不创建 `fact_graph`。

新证明只能通过 `src/crpn/admission.py::Admission.submit` 进入图。独立 Verifier 返回判断；CRPN 检查完整绑定后，将证明、Claim/Support 归属及相应关系一次原子发布。显式迁移器是历史证据导入入口，保留过去验收状态，不进行新的数学认证。显式撤销也由 CRPN 完成。

普通图保存拒绝未验证的新证明、正文改写、历史删除、证明归属转移和已撤销证据复活。提交回执只提供审计证据；回执的历史 accepted 不能覆盖图中的 revoked。

## 沿真实入口核对的调用链

改造前：

```text
crpn CLI → Research.step → prepare_candidate / prepare_compose
→ DANUS SubmissionGate → fresh VerifierBackend → DurableRounds
→ FactGraph.add → CRPN accept_verified / binding → next schedule
```

Fact 与 CRPN 归属分两次发布。查询、closure、撤销仍依赖 DANUS FactGraph。

改造后：

```text
crpn CLI → 原 CRPN 策略与候选准备
→ CRPN Admission → fresh VerifierBackend → 原 DANUS DurableRounds
→ CRPN 图事务：证明 + 数学归属 + 关系
→ 提交回执 → 原服务/游标转换 → next schedule
```

必要的 SubmissionGate 语义已经接入 CRPN：冻结请求、独立验证回执、前提有效性、幂等恢复和拒绝复活。继续使用 DANUS 的 `locked`、`immutable_json`、`atomic_json`，以及原有 `submissions` 回执布局。没有新增模型调用日志。图已提交而回执尚未完成时，恢复不重复验证或写入证明。

`status`、材料查询/检查、前提读取、COMPOSE-ready、closure、`export`、`revoke` 全部由同一个 CRPN 图计算。旧快照不能继续授权前提读取，需重新读取当前图。

## DANUS 还能执行什么？旧入口是否退出？

保留 DurableRounds、WorkerLayout、原进程执行器、Docker 隔离、认证 capability broker、通用 IO、LocalMemory、GlobalMemory、BM25 和通信回执。Gateway 仅转发 CRPN 材料读取与研究记忆动作；Worker 没有事实提交/撤销工具。Verifier 只返回验证结果。

活动导入链不再加载 DANUS FactGraph、SubmissionGate、原生 gateway fact-submit、main-role 策略表、研究分配或 scaffolder。独立进程回归核对了这些导入边界。旧 FactGraph API 对 `crpn-authority-2` workspace 明确拒绝操作；原生 gate/事实 CLI 无法在该 workspace 建立另一套事实权威。vendor 旧实现保留出处和历史兼容读取用途，不是新运行入口。当前支持的状态/导出入口是 CRPN CLI。

依赖变化集中在 CRPN 图和准入、材料读取、CLI、迁移器，以及三个 vendor 导入/拒绝边界。没有安装或升级依赖。以下内容相对已验收基线未改动，证据见 `current_migration_audit.json`：

- `substrate/runtime.py`、CRPN scheduler、contracts、VerifierBackend；
- DANUS DurableRounds、process loop、Docker runner、capabilities、容器 launcher、MCP proxy；
- DANUS durable IO、LocalMemory、GlobalMemory、BM25。

## AND/OR 和策略语义

Claim solved/refuted 从有效证明及其实际前提闭包计算。Support 的条件证书本身不解决结论；所有 AND 前提有效后才可 COMPOSE，组合仍须独立验证并保留精确依赖。撤销沿具体证明边传播，另一条有效 OR 证明不会被连带清除。循环和 alias 不产生自证。

原 direct-first、3:1:1、固定 REVISIT、Study、局部注意力、bridge、recurrence/helper/alias、COMPOSE 和研究行动语义保留，没有新增策略字段。非关键研究说明、对象卡和摘要仍不获得真值权限，格式问题继续 fail-soft。

回归：**116 passed，1 skipped**；跳过项为默认关闭的 Docker 探针。覆盖多 OR 路线撤销、AND 前提未齐、循环/alias、helper 激活、scope bridge、已撤销证据不可复活、验证/图提交/回执三个中断边界、真实子进程中断恢复、伪造准入拒绝、历史证明不可改写及 packet 投影。

## 无损迁移核对

通过正式 `python -m crpn migrate SOURCE DESTINATION`，再做零模型历史 replay：

| 输入 | 有效 / 已撤销证据 | Claims | Supports | Studies | 深度 | Local / Global 记录 |
|---|---:|---:|---:|---:|---:|---:|
| n3d-13 | 8 / 0 | 7 | 3 | 4 | 2 | 27 / 4 |
| 冻结 #67 `C:\n\e67` | 9 / 0 | 8 | 4 | 5 | 3 | 37 / 5 |
| rp2 `C:\n\rp2` | 16 / 1 | 16 | 3 | 4 | 2 | 502 / 4 |
| 当前已验收 `C:\n\dsr2` | 13 / 0 | 12 | 4 | 5 | 3 | 107 / 13 |

所有现有证据、Claim、Support、Study ID 保留；映射显式记录。正文、实际依赖、真值、ready Supports、alias/helper、调度和历史服务顺序核对一致。全部源文件按内容哈希归档，包含原验收、撤销、调用及研究记录；源文件字节未改变。再次迁移字节幂等。历史回执只读，不成为新 run 的执行预约。

本轮真实运行选择迁移**当前已验收状态 dsr2**，包含其已有 13 条证据；三份更早状态用于迁移对照。新目录 `C:\n\ca2`，新 run ID；没有原地 resume 旧 runtime。当前状态的命题接口、完整证明内容、记忆字节及全部归档另经独立核对通过。

## 正常五服务真实验收

RUN ID：`8b3211e1915f4c8ca25bd9f15065d7e0`。

运行配置：GPT-5.6 Sol / xhigh / 600 秒；Codex CLI `0.153.4`；Docker 镜像
`sha256:5b56b18c4d75478a891d7cdbf01170085d3ab35ed4de38e1022337ae24b2dc46`。
正式使用 `python -m crpn run/pause/resume`，未手工指定 Study、候选、数学路线、handover 或检索提示。五份 Worker 任务、操作、Study 和材料均逐项匹配真实确认的 Selector 输出。

| Visit | Channel | Worker 所属 Study 后缀 | 服务结果 | 新证明 |
|---|---|---|---|---|
| 28 | ADVANCE | `9b4114db9e727d0ccc1effc5` | COMPLETED | `a6655a4ec450be10` |
| 29 | EXPLORE | `d2ad26a229e580ad341d0fb6` | VERIFIER_REJECTED | 无 |
| 30 | REVISIT | `d2ad26a229e580ad341d0fb6` | COMPLETED | `a1fbca1a2dc11bf2` |
| 31 | ADVANCE | `9b4114db9e727d0ccc1effc5` | COMPLETED | `505035b33d5f9efa` |
| 32 | ADVANCE | `9b4114db9e727d0ccc1effc5` | COMPLETED | `72e68892873e4a53` |

共 15 次真实调用：5 Selector、5 Worker、5 Verifier，均 COMPLETED。四次验证 correct，一次 wrong；拒绝原因是声明了未实际使用的前提，未写入图。新增 4 条证明及对应 Claim，Support/Study 数量不变。本轮没有自然触发 bridge、recurrence、COMPOSE，相关语义由历史状态和回归覆盖。

实际证明复用链：`a6655a4ec450be10 → 505035b33d5f9efa → 72e68892873e4a53`。另一条新证明 `a1fbca1a2dc11bf2` 独立。数学结果属于有限端点障碍扩展；目标仍 OPEN，不据此评价策略强弱或宣称整体定理推进。

### Pause / resume 与审计异常

外部审计器第一次在原子图更新期间读到了过期快照，错误地将正常的“重新读取”拒绝分类为完整性故障，并在首服务后额外请求 pause。第二服务正常收尾后退出。冻结图独立验证通过；这是审计器错误，没有生产 runtime/真值故障。

恢复观察脚本随后遇到 Windows 默认 GBK 解码 UTF-8 的错误。保留了原脚本和错误信息，改为显式 UTF-8；生产源码未修改，正在运行的正式 CLI 未重启或重复调用。

预定的“两服务后 pause”于 `2026-09-22 10:17:28 UTC` 正式发出，第三服务正常收尾后停止。进程和容器停止、两次 workspace 哈希一致，随后正式 resume 同一 run。第四服务回到原 Study lane，实际读入 2 条暂停前 LocalMemory 记录，包括 visit 28 的 worker-return continuation。第五服务启动后正式请求最终 pause，完成五服务后正常退出。

因此，本轮有一次额外审计暂停，也完成了预定的真实暂停/恢复边界。该协议偏差没有隐藏或从证据中删除。暂停前 74 份已确认调用/提交文件保持原样；全部原记忆保持追加前缀。没有重复调用、证明准入、服务、note source key 或游标提交。visit 从 28 到 33，channel cursor 从 27 到 32。

### 实际局部注意力

固定随机种子 `97eb403:ca2:worker-packet-audit` 抽到 visits 29、28、30，并检查全部五份 packet：

| Visit | Packet UTF-8 bytes | Facts exposed | Local records | Global 命中去重数 | 随机抽查 |
|---|---:|---:|---:|---:|---|
| 28 | 91,281 | 1 | 3 | 11 | 是 |
| 29 | 59,033 | 1 | 3 | 12 | 是 |
| 30 | 30,767 | 0 | 3 | 10 | 是 |
| 31 | 64,945 | 1 | 3 | 11 | 否 |
| 32 | 32,101 | 1 | 3 | 10 | 否 |

packet 保留当前 Study/命题接口、选定有效材料、局部研究与 continuation；未带入 Claim/Support 内部证明存储。相关 AND readiness 仍由图计算，本轮不存在 ready COMPOSE。每次研究查询每种 GlobalMemory 类别最多 3 个结果；完整查询、结果 ID 和去重计数保存在 `actual_global_searches.json`。这些 BM25 结果直接投影进 packet，本轮额外 `gm_search` MCP 调用为 0，外部检索为 0。

LocalMemory 是 Study 未完成工作，GlobalMemory 是 awareness，CRPN 图是验证后的数学权威。运行结束共有 144 条 local、19 条 global 记录；原有记录和暂停前记录均保留。DANUS 保存研究记忆，CRPN 决定局部投影，没有新增平行 research-artifact authority。

### Truth / revocation / accounting

最终图含 17 条有效证明记录、16 Claims、4 Supports、5 Studies；原 13 条证明及全部原接口保持不变。每条新证明都匹配 CRPN 请求、独立验证和提交回执。所有闭包仅含有效前提，DANUS 事实目录不存在。

在最终状态的**离线副本**撤销 `a6655a4ec450be10`，恰好撤销它及依赖它的 `505035b33d5f9efa`、`72e68892873e4a53`。独立证明 `a1fbca1a2dc11bf2` 和其余 13 条历史证据保留；重提撤销证明在调用 Verifier 前被拒绝。正式运行字节未改变。多 OR 路线、AND 未齐和 alias 自证等集中回归亦全部通过。

- Input tokens：842,077；其中 cached input：456,064。
- Output tokens：57,102；总 input + output：899,179。
- UNKNOWN：0；本次没有 timeout。超时记忆保留、UNKNOWN 和指纹漂移拒绝由原真实验收及本轮回归覆盖，未在新 run 中人为制造。
- 调用 wall 合计：2,398.79 秒；包含暂停与收尾的总 wall：2,416.28 秒（40 分 16.28 秒）。
- 15 份回执的证据哈希、运行指纹匹配；每次调用各有一个 thread start 和 turn start。运行源码指纹全程不变。

## 完整证据与验收决定

Windows 原始运行：`C:\n\ca2`；观察、历史迁移、初始/暂停/最终快照及离线检查：`C:\n\ca2o`。
Linux 完整归档：`/home/wmywb/Noespire/experiments/crpn_authority_convergence/evidence`，入口为 `INDEX.md` 和 SHA-256 `MANIFEST.json`。审计脚本、随机 packet 样本、普通 Selector 来源核对、22 项验收断言及原始审计异常均保留。

**ACCEPTED — CRPN SOLE AUTHORITY。** Noespire 的数学状态与策略由 CRPN 掌握；更换 DANUS 的 IO、调用、隔离、记忆或检索基础实现，不需要改变 Claim/Support 图的数学语义。后续保持该边界，不恢复 DANUS 原生真值入口。当前验证仍是自然语言 LLM 验证，不等同于 Lean kernel 证明。
