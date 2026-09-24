# CRPN 局部任务保持与完整证明单元：设计、实现和连续验收

## 范围与基线

参考基线为 `4d3b3be645c266ffebb77a92b740d4f36e215dfe`，实际开发起点为 `dee631c7b8fba63ca1d74c362a5e846276c8c1df`；后者保留了参考版本之后的有效回归与报告。本轮实现代码冻结于 `1d20b3edf71c4ea83034c27fb7ab009e78f999d9`。CRPN 的 AND/OR 图、Selector 焦点调度、3:1:1、单一候选提交、Admission、Verifier 判定、scope/bridge、recurrence/helper/alias、COMPOSE、撤销及 DurableRounds 均未修改。数学运行保持闭卷。

## 最近动态切口实验的逐项审计

旧实验的归档 workspace 中有 **10 次 Verifier 调用：8 次接受、1 次判错、1 次超时**；另有一次未交付前提的提交被准入前检查拒绝，未耗 Verifier。完整 submission ID、证明哈希、前提和分类见忽略提交的 Linux 证据 `experiments/crpn_task_proof_units/evidence/prior_ten_verifications.json`。

visit 33 的错误候选把含 N=1、2 的截断 Gram 矩阵称为恰好 rank two；独立 Verifier 指出这两个边界至多 rank one。该判错是必要审查，不能作为可省成本。修正后的 N≤836 证明是一项完整有限接口。随后 N≤1469 的 Gram 表述是由旧证据得到的直接推论，缺少已观察到的独立消费者，具有内联可能，但不能仅凭长度判定无价值。

visit 34 的 N≤1470 结果回应了当次明确任务；同会话的 N≤1653 继续同一构造并以 N≤1470 为前提。若目标事先就是更完整的端点论证，前一段可能直接写入后一份证明；现有证据不能倒推认定 N≤1470 的独立提交是错误。visit 35 的一个 N≤1781 候选超时，保持未确认。修订的 N≤1781、改造后的 N≤1808 与“不存在所列形式 SOS 证书”的结果并非三个等价成果：前两项共享构造链，后者是不同用途的有限方法限制。N≤1808 的证明是否应内联 N≤1781，取决于可审查长度和真实复用。visit 37 的另一个 h 赋值所给 N≤836 结果是独立局部任务的完整结论。

因此旧实验的 8 条接受证据不等于 8 个独立定理前沿；也不能把所有有限端点视为无用。旧 root Claim 仍为 OPEN。尤其在 visit 35，最后的 `next_work` 机械地建议 N=1809，却没有建立这些有限结果通向 root 的图接口；这是本轮修复的任务漂移触发点。

## 最小改造与权威边界

`work.derive` 继续从选定的一个 Study、相关 Claim/Support 和原 LocalMemory 派生临时切口。切口现在明示精确未决焦点的图身份、已选路线的开放 AND requirement、最近三项会话接受结果的证据 ID/状态/来源任务，以及“剩余缺口尚未知”的边界。图接收者能机械识别时才标为接口；检索、收据与数学相似性都不创造蕴含。已撤销的最近结果只标为撤销，不作为可请求前提。过宽条件继续分页；输出消费者与输入缺口分开，避免把当前 Claim 作为另一条路线的前提误写成自己的缺口。

主研究行动现在始终锚定该未决焦点或其开放 requirement。旧 `next_work` 仍保存在切口，但作为未验证路线建议另列；可选择继续、核查或改变方向。四个行动的窗口中保留主行动，其余线索依原游标轮转，仍有公平曝光。局部 Selector 只能在这个焦点下选择，不恢复全图排名，也不增加持久任务权威或数值评分。

Worker 指令要求将一份证明内部的例行代入、同一构造检查和直接推论保存在原 LocalMemory 草稿，形成完整且可审查的数学结论时再通过 `candidate_submit` 交独立 Verifier。实际消费者需要的接口、继续推导前必要的独立审查、已完成的当前任务，或合并后过长的证明，仍可及时单独提交。没有提交次数门槛；另一个独立有效的 OR 证明也不受阻。草稿不给前提权限，最终候选必须自行包含未验证步骤。接受回执后，Worker 需区分原任务完成、只完成一个 requirement、尚无已证明联系，并据此记录准确剩余工作；这些是研究指导，**不是新的准入条件**。

## 确定性回归

变更后 `tests/crpn` **101 passed**。其中新增测试验证：有限端点 `next_work` 不覆盖未决 Claim；开放 Support requirement 和最近图证据仍在有界切口中；撤销后旧结果不再进入行动前提；纯笔记不改变图真值。原有测试继续覆盖 1,001/10,001 OPEN Study 下同一局部包有界、48 路线轮转、240 条条件分页、不同 OR 路线、准入与动态前提、拒绝反馈、超时及中断恢复、游标只推进一次。DANUS DurableRounds 与隔离相关测试 **26 passed，1 skipped**。测试使用假 Worker/Verifier 的部分只证明程序边界，不计作数学研究能力。

## 连续自治配对

两臂从上一轮动态切口归档的同一个只读数学状态，经正式 `python -m crpn migrate` 建立全新 workspace。源 `crpn.json` SHA-256 为 `85395f04c7c3ec577c534dd8c0c004aed13dabd1764a88474564a1c844a85f68`，共 517 个源文件。迁移后数学图与 Local/Global Memory 的字节核对相同：24 Claim、4 Support、5 Study，起点 visit 38、目标 OPEN。A 为实际开发起点 `dee631c7`；B 为本轮实现 `1d20b3e`。只改变任务切口组织与 Worker/Selector 的证明单元指导；Verifier 文本及 schema、Worker schema、Docker 镜像、模型 `gpt-5.6-sol`、`xhigh` 和默认 600 秒角色时限相同。两臂预注册各五次普通 Study 服务、第二次服务后正式 pause/resume；不指定数学路线、不重采。完整预注册和运行证据保存在 Linux 工作树忽略提交的 `experiments/crpn_task_proof_units/evidence/`。

两臂正式 run ID 分别为 `1e79bc177a5440bca16079f1dd167e91` 与 `1d80de74b8814c81af2f03b2b7a969c1`。两者均在 visit 38–42 完成 **ADVANCE、EXPLORE、REVISIT、ADVANCE、ADVANCE** 五项真实服务；第二项之后正式暂停于 visit 40、`pending=false`，再以原 run ID 恢复到 visit 43。两次暂停前后图 SHA-256 与完整 round 数完全相同。源 517 文件始终未变，旧证明正文/状态/依赖逐项未变，14 个原 Local/Global Memory 文件在两臂中均保持字节前缀。每臂的新 accepted submission ID 与图中新增证据 ID 集合完全相等，无重复 round key、service key、提交或遗漏结果。两臂的 `Network.validate()`、新证明前提有效闭包检查均通过；无撤销、Support、Study、bridge、recurrence 或 COMPOSE 自然触发。

| 读数 | A：动态切口原版 | B：局部任务/证明单元升级 |
| --- | ---: | ---: |
| Selector / Worker / Verifier 调用 | 5 / 5 / 6 | 5 / 5 / 4 |
| 已知 input tokens（其中 cached） | 2,268,617（1,852,032） | 1,340,556（1,040,256） |
| 已知 output tokens | 74,447 | 36,702 |
| usage UNKNOWN；超时 | 0；0 | 0；0 |
| 首次请求到最终暂停的观察墙钟 | 1,754 秒 | 951 秒 |
| 外层模型调用墙钟（含工具等待） | 1,733 秒 | 933 秒 |
| Worker 工具等待（已含于外层） | 376 秒 | 160 秒 |
| 嵌套 Verifier 墙钟（已含于等待，不再加到外层） | 370 秒 | 157 秒 |
| Worker 初始包范围 | 44,375–69,969 字节 | 46,081–72,076 字节 |
| Selector 包最大值；每包 Study / 行动 | 39,255 字节；1 / 4 | 40,506 字节；1 / 4 |
| 工作台读取实际交付 | 155,316 字节 | 48,914 字节 |
| 新接受证明 / 新 Support / 新 Study | 6 / 0 / 0 | 4 / 0 / 0 |
| 目标真值 | OPEN | OPEN |

所有 30 次模型调用均使用相同 `gpt-5.6-sol`、`xhigh`、600 秒请求时限；两臂 Docker 镜像、Verifier 指令/schema、Worker schema 与三种角色的实际 capability manifest 哈希相同。两臂的 Worker/Selector 指令差异正是预注册变量。初始包没有因本轮升级变小，仍各含一项 Study 的局部切口。每个 Worker 初始包仅带至多 3 条本地研究命中与 10 条共享检索命中，源全局记忆起初有 31 条记录；完整证明继续按需读取。工具交付量单列，不混同 provider 累计 token。上述墙钟不把嵌套 Verifier 再加一次。

### 实际任务接续和数学内容

A 的 visit 38 重证了旧图中已有的同一 h 构造 N≤1470 弱表述，属于低信息重复。visit 39 从 N≤1808 推进到 N≤1809。visit 40 公平回访另一 Study，先把该证人写成 prime-torus 直接推论，再修改构造得到 **N≤2190** 的完整有限证人。visit 41 跨 Study 使用 N≤2190 证据，验证了所列 SOS 证书形式在该范围内不可能；另给出 Möbius 恒等式与算子范数构成的通用条件性下界接口，但没有证明其中的数值条件 `A/K>4`。visit 42 接到“本局部任务没有剩余义务”的任务文字，未调用材料或提交候选，尽管更大的目标仍 OPEN。A 有一次真正扩展了有限方法边界的多 Study 复用；N≤1470 的重证和 N≤1809 的直接推论也显示了重复与可内联空间。

B 的 visit 38 检查旧图中一条 `P ⇒ Q` 接口，明确写入 LocalMemory：该方向不能反推当前 `P`，仍缺全量词的 prime-torus 证明；未提交候选。visit 39 在 root Study 形成并验证另一份 **N≤1809** 的完整 Gram 证人。正式恢复后的 visit 40 回到 visit 38 的同一 Study/lane，`local_record` 读回其精确记录 ID `b816d6acb34e65dbcc3c4fd334df1b6eea15943156cefef94de2231f98fd5fb8`，再次定位蕴含方向缺口；无新验证。visit 41 在另一个 Study 经 `premise_request` 合法取得 visit 39 的证据，分别提交 N≤1809 的证书形式限制和 prime-torus 直接推论，二者均获独立 Verifier 接受。visit 42 没有机械沿用“无剩余工作”，而是从旧证据 `505035b33d5f9efa` 的 N≤837 有限证人推得相应 kernel 接口并验收。这是合法的局部接口，但没有把定理前沿推进到 N>1809。

B 的 N≤1809 证人本身在一份证明内完成了新素数检查和逐段前缀计算；A 的 N≤1809 证人同样是一份完整证明。因此本次配对**没有观察到**原本会单独验收的同一构造中间检查被新版内联。相反，B 仍把 N≤1809 证人的两个直接后果分别送 Verifier，说明“按完整数学单元提交”的指导尚未可靠改变实际证明分界。B 的前两次未提交服务保存了准确的未验证缺口，避免把逆向蕴含冒充已证明前提，但未形成独立的 verified method limitation。B 的最后一个 kernel 结果是旧 N≤837 证人的直接改写，不能与 A 的新 N≤2190 构造等量比较。

若只看调用与成本，B 少 2 次验证、已知 input tokens 约少 41%、观察墙钟约少 46%。这些节省伴随着真实数学信息下降：A 有 N≤2190 的新有限证人、相应更强方法限制和一个通用证明接口；B 止于 N≤1809，并继续单独验收两个直接后果。两个臂都未解决原无穷目标或形成新的全局 Support。一次配对不能推断普遍胜率；本次数据也不能把“做了较少有价值工作”误报成证明封装效率提升。

### 故障、可靠性与判定

模型运行前的第一次 Docker 预检失败，因为 Windows Docker Desktop 未运行；启动既有 Docker Desktop 后，两臂在任何模型调用前重新完成指纹预检与迁移。没有为此修改源码、数学状态或预算。测试 broker 在受限 Linux 沙箱内曾收到 socket `Operation not permitted`，以允许本地 socket 的测试环境重跑后通过；这与两次真实隔离运行无关。正式配对期间没有基础设施故障、timeout、UNKNOWN usage、真值完整性故障或源码补丁。

**判定：局部任务锚定的控制边界通过，证明封装/研究效率收益未通过本次验收。** `next_work` 不再自动成为唯一主任务，Worker 能在原 lane 读回具体缺口，图与即时验证权限保持完整；但真实 Worker 仍产生可内联的直接后果，且较少的验证调用伴随更弱的已验证有限边界。保留这次负面结果，不将 4 对 6 的 Fact 数或较低 tokens 宣称为数学改进。所有接受仍是自然语言 LLM Verifier 判定，不是 Lean/kernel 正确性；本轮逐项检查未发现需要立即冻结的明显自相矛盾证据，也没有重新研究 Truth Gate。后续若单独评估证明分界，应固定真实消费者和同一证明义务，再看步骤是否在完整候选中被审查，同时守住局部注意力与不丢失结构性工作；本轮到此停止。
