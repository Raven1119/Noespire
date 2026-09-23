# CRPN 单一提交与可接续研究会话：实现及配对验收

## 基线、假设与范围

参考基线 `458215642d23dd6caac7aa36138f4182412644eb`；实际干净本地起点为 `6390a24b3543920f3619f8f11a59407a93acd8c9`，保留其后的验收报告。冻结实现 SHA 为 `0437959f4a3ec906a817b08b0c07205505c2c6f6`。假设是：普通 Worker 只经 `candidate_submit` 准入、最终回复只交接，能消除已观察到的收尾重述再验证；把旧结果、未完工记录和验证反馈放回有界局部现场，能让同一会话继续处理当前义务。没有改 Selector、3:1:1、AND/OR、scope、bridge、recurrence/helper/alias、COMPOSE、Verifier 判定、DANUS runtime 或外部知识配置。

原始数学源为只读 `C:\n\ca2`，source run `8b3211e1915f4c8ca25bd9f15065d7e0`；`crpn.json` SHA-256 `35b73643e4b39f80c8f7100c4002b8aed73426f785d35d93ecf8098a8a490ea8`。两臂分别经正式 `crpn migrate` 建立新 workspace，旧 runtime 未 resume、没有互相传递研究结果。迁移初态同为 17 条有效证明、16 Claims、4 Supports、5 Studies，目标 `OPEN`；命题、证明、依赖、调度及源文件均核对保持。两臂 runtime 指纹除源码摘要外逐字段相同：`gpt-5.6-sol` / `xhigh`，所有角色 600 秒 active deadline，MCP 660 秒，Docker 镜像 `sha256:5b56b18c4d75478a891d7cdbf01170085d3ab35ed4de38e1022337ae24b2dc46`。

预注册边界是现有开放的矩阵证书 Claim `study-ob-b3664c95f22d4dfc3c76237a`，它已有条件 Support，尚须解决严格 prime-torus/minimax 前提。为使两臂任务完全相同，在各自派生 workspace 的正常 ADVANCE 曝光中预置同一 `RESEARCH` pending action；任务只要求研究该 Claim 及现有条件义务，`fact_ids=[]`，不指定证明路线、Fact 或结论。这样比较的是**同任务的一次真实 Study Worker/Admission 服务**，不比较 Selector 选路；每臂仅执行一次，`visit 33→34`，没有重采。原始 action 和预算在 `preregistration.json`。

## 根因与最小改动

旧普通 Worker schema 同时允许 `candidate_submit` 和最终 `candidate`。`Research.step()` 先恢复工具准入，随后把最终候选再送 Admission；内容字节相同可以复用回执，但语义相同而措辞不同会得到新的 key、Verifier 调用和图内证明。旧五服务验收已出现四对。本轮没有加入语义去重器，因为另一份真正有价值的证明必须仍能成为 AND/OR 的备选路线。

普通 Worker 的结构化最终输出现在只有 `submission_receipts`、原有 `continuation` / `next_work` 和 `new_study`；完整 Fact、Support、refutation 只能通过会话内 `candidate_submit → CRPN Admission → fresh Verifier`。外层结果以已有 durable 工具回执汇总，不读取最终数学文字作为真值；接受结果在 Worker 最终输出不完整、TIMEOUT 或 INTERRUPTED 时仍由准入事务和恢复机制保留。确有新候选可再次调用同一工具。特殊 `BRIDGE_WORKER_SCHEMA` 保留原 bridge 内部候选/准入，recurrence 与 COMPOSE 未变。没有增加说明字段、持久研究权威或调用日志。

局部 packet 从当前图显示相关 Support 的真实 requirement/ready 状态，按**具体任务**检索最多四条只读相关已接受结果；读取不会授权前提，仍须 `premise_request`。上次服务的验证理由从原回执/LocalMemory event 派生，当前 Study 的历史及 DANUS GlobalMemory 仍由现有 BM25 搜索。跨三个查询的同一 LocalMemory 原始记录按其完整记录哈希、同一 GlobalMemory 记录按 `(kind,id)` 保守去重，并在保留项列出命中查询；不同 ID、不同条件不合并。完整证明仍由 `proof_read` 按需分页；packet 不加载全库。`crpn.json` 仍是唯一事实权威，研究摘要、检索结果及最终回复均无准入权限。

## 回归与旧重复研究审计

最终实现回归 **168 passed、1 skipped、1 warning**，其中受影响 CRPN 定向回归 46 passed。覆盖工具接受后最终文字无第二次验收、不同完整候选仍可分别验收、同请求与中断恢复幂等、拒绝理由进入下一局部 packet、接受后超时/中断保留图结果、动态前提与撤销重检、scope、一次服务游标，以及同一原始记忆命中的查询来源。fixture Verifier 不代表数学可靠性。唯一 skipped 是默认关闭的 Docker 探针；配对运行确实使用 Docker。第一次全回归因 WSL 传给 Windows Python 的 `PYTHONPATH` 未传入其子进程而出现一个 `ModuleNotFoundError`；在 Windows 父进程内设置路径后同源码全套通过，未改测试断言或产品逻辑。

历史 836/1469 审计区分如下。visit 34 的 Selector 任务是 735→836；旧图已有被接受的 836 结果 `a6655a4ec450be10`，但交付的前提只有 735 结果 `28555270ab4db864`，因此这里有**材料/任务重叠**，不是 DurableRounds 重放。把旧任务交给新版只读任务检索可找到 836 结果，但是否采用仍取决于 Worker 的精确检查和合法前提请求。visit 35 的任务从新 836 结果继续修补该 witness；旧图另有 1469 边界 `72e68892873e4a53`，未在该服务交付。两次是不同 Study services、不同 Worker 调用；新版不能保证 Selector 不再选择重叠任务，本轮也没有调整选路。旧 visit 33 的 30 条共享命中仅 13 条唯一记录。配对边界基线包 73,219 字节、9 条本 lane 曝光、25 条共享曝光/14 唯一；新版真实包 55,076 字节、3 条本 lane 唯一记录、14 条共享唯一记录，另有 4 条只读相关结果和 3 个相关 Support 接口。两臂初始 `accepted_facts=[]`；新版没有把发现结果偷变成合法前提。

## 一次真实配对轨迹

| | 基线 `6390a24` | 新版 `0437959` |
|---|---|---|
| Run ID | `78489bfd49514e589386da8fddcf582f` | `c0b40091f9cf4b0cbd9c2b5eb6f643eb` |
| 会话 | 1 Worker；自然触发 1 recurrence probe | 1 Worker；未触发 probe |
| 旧材料 | 成功 `proof_read` 既有条件证书 `62bd0febd52f8668`，动态请求该前提；后又请求 `72e68892873e4a53` | 检索/检查既有条件证书 `93cea28672be5d18`，动态请求该前提；首次接受后请求 `72e68892873e4a53` 并继续 |
| 会话内提交 | 一条条件 Support，Verifier 接受 | 两次主动 `candidate_submit`，均获接受，命题与前提不同 |
| 最终回复 | 将同一条件 Support 换词重述为最终 candidate，再触发一次 Verifier 和第二条同义 Support | 仅交接两条证据 ID、已完成工作及未完义务；没有最终候选或额外准入 |
| 图结果 | 2 条新证明、2 个 Support ID、1 个新 requirement Claim；旧条件归约的同义重证 | 2 条新 Fact、0 新 Support、2 个新 Claim；一个双向证明接口和一个有限方法限制 |
| 核心义务 | all-B 严格 prime-torus 前提仍 OPEN | 同一前提仍 OPEN；根目标也 OPEN |

基线工具接受 `a1b021f11a45ee32` 后，最终重述产生 `1f7a84efc2ad1d70`；两个 statement 和实际 predecessor 相同，证明正文措辞不同。额外**收尾** Verifier 的独立成本为 55.46 秒、10,057 input tokens、1,470 output tokens。基线在工具反馈后请求了既有 1469 Fact 并保存准确的 B=2 后续义务，却没有完成第二项证明。新版先接受 `186095167de5143c`：以原有 Q⇒P 证书为前提，再用 rank-two torus Gram kernel 证明 P⇒Q，得到矩阵证书命题 P 与全 B 严格 torus 命题 Q 的等价；随后接受 `810d1dfbb687c1dd`：用旧 1469 witness 排除 A=2、N≤1469 的矩阵证书。两条证明分别经新鲜 Verifier，未见明显条件遗漏；它们仍只是自然语言 LLM 验收。第二条并不依赖第一条作为前提，而是复用旧 Fact `72e68892873e4a53`；这证明了**反馈后同会话继续**，未证明形成了一条新证据依赖链，更未完成 Q。没有自然拒绝反馈，真实会话的“拒绝后修正”仍只由回归覆盖。

| 成本，含全部嵌套模型调用 | 基线 | 新版 |
|---|---:|---:|
| DurableRounds 调用 | 4（Worker 1 / Verifier 2 / probe 1） | 3（Worker 1 / Verifier 2） |
| 已知 input tokens（其中 cached） | 841,665（732,672） | 657,314（565,376） |
| 已知 output tokens | 12,518 | 9,979 |
| UNKNOWN usage | 0 | 0 |
| Worker 同步工具等待 | 42.99 秒 | 62.79 秒 |
| 同口径服务墙钟：Worker request→CRPN graph commit | 471.14 秒 | 363.63 秒 |

模型 round 墙钟求和分别为 513.41/425.67 秒，已包含 Worker 内部同步验证等待，**不能**再把等待或 Verifier 墙钟加到服务墙钟。基线外层计时另为 471.31 秒，与文件时间窗相差 0.17 秒。新版外层一次性打印脚本在服务已经提交后，因 Windows 控制台 GBK 无法编码最终回复中的 Unicode 符号而退出码 1；CRPN 图 `visit=34, pending=false`、Worker `COMPLETED`、两条回执和全部 runtime 文件完整，故没有重跑模型。新版服务墙钟使用与基线同口径的持久文件时间窗，未把该打印故障记为模型超时。另有实验前 Docker Desktop 未启动造成的预检失败，零模型调用；启动既有 Linux engine 后才开始基线采样。两个环境故障及处理保留在证据中。

## 结论与边界

**单一提交协议验收通过。** 基线可复现的工具成功后最终重述再验证，在新版真实会话中消失；最终文字不能入图，两个不同完整候选仍各自经过 Verifier，回执、图和服务游标一致。新版检索更紧凑，也自然发生了接受反馈后的第二次不同候选提交。此次 1 对配对的总调用和可比墙钟更低，但自然数学路线、probe 触发和检索行为不同，不能把全部差额归因于协议，也不能据此宣称普遍数学收益。

**剩余义务未完成。** 双向接口是新的证明接口；有限 N≤1469 排除是旧 witness 在矩阵表示中的方法限制，不是 all-B 正向证书或根定理推进。两个 Fact 的 LLM 验收不等于形式证明。真实拒绝后的接续、跨会话依赖链及 Selector 是否避免再次选择已覆盖任务均未在这对样本中自然验证。后续架构保持现有 CRPN 权威和策略；若再做研究实验，应单独预注册直接针对仍开放的 Q 义务，不把本轮有限翻译当作已解决。

完整原始 request/result、capability journal、Verifier/Admission 回执、图、记忆、runtime 指纹、迁移归档以及逐文件 SHA-256 位于 `/home/wmywb/Noespire/experiments/crpn_single_submission/evidence/`；其中 `baseline_workspace/`、`new_workspace/` 为只读源的冻结副本，`pair_audit.json` 与 `audit_pair.py` 可复算成本和新增证明，`preregistration.json` 与 `regression.json` 保留预算、任务及回归证据。旧实验证据未改动。本轮仅本地提交，不 push。
