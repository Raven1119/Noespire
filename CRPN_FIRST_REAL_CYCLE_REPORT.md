**SOURCE SHA**  
`35a898bb5c3c5e59922f0cfdc9e53cc0472fe941` + 最小权限补丁。Implementation：`adce52605da500133f0d6538261ea5ad024098fb`。补丁 SHA-256：`7a71ecceed03c55d01aa721c89a06d54b75d6dfd51e086cd5195a45f25c97b27`。冻结输入 `C:\n\e67` 的 435 个文件哈希一致，经正式 migrate 生成全新 workspace。

**RUN ID**  
`00ffd9f56e99474aa7f914c8123fb288`，workspace：`C:\n\dsr2`。Windows 编排 / Linux Docker Codex，Sol / xhigh / 600 秒，全程闭卷。

**STUDY SERVICES**  
5 次：4 COMPLETED、1 TIMEOUT；涉及 3 个 Study lane。visit `23 → 28`，状态转换和 Study revision 均核对通过。

**CHANNEL TRACE**  
`ADVANCE → EXPLORE → REVISIT → ADVANCE → ADVANCE`，完整 3:1:1。

**PAUSE BOUNDARY**  
第 2 次完成后正式 pause；已启动的第 3 次排空后退出。退出码 0、状态冻结、残留 DANUS 容器 0。

**RESUME RESULT**  
正式 resume 同一 run；恢复前 workspace 哈希完全一致，从 visit 26 继续。运行指纹一致；旧 run 的源码漂移检查实测 fail closed。

**DUPLICATE CALLS**  
0。重复 service、pending 提交、Fact admission 均为 0；暂停前 75 份不可变证据全部未变。

**LOCAL ATTENTION AUDIT**  
固定随机种子抽查 3 个真实 packets：

| visit | packet 字节 | Facts | 本地记录 | GM 命中 / 去重记录 |
|---|---:|---:|---:|---:|
| 23 | 51,170 | 2 | 2 | 9 / 4 |
| 24 | 68,596 | 1 | 3 | 12 / 7 |
| 25 | 47,397 | 2 | 3 | 16 / 9 |

查询均满足既定边界；额外 4 次内部 `gm_search` 各返回 1 条记录。Fact IDs、查询及结果完整保存在审计文件。恢复后的 packets 亦检查通过。确认 **DANUS stores globally，CRPN projects locally**，无整库注入或外部检索。

**MEMORY CONTINUITY**  
同一 Study 回到原 lane；visit 26 实际收到 visit 23 的 continuation，visit 27 延续 visit 26。超时及暂停前已持久化记忆全部保留。LocalMemory = unfinished work；GlobalMemory = awareness；FactGraph = verified truth，无平行 authority。

**NEW FACTS**  
4：`2f72e0aca879ea00`、`a2f650b9be55f4ca`、`b21e5f8eb8e56ca1`、`28555270ab4db864`。

**NEW SUPPORTS**  
0。4 个既有 Support 的要求仍未满足，未被误判可 COMPOSE；多前提 AND 未自然触发。

**NEW STUDIES**  
0。

**BRIDGE / RECURRENCE / COMPOSE**  
均未自然触发，未人工插入。

**TRUTH STORE CHECK**  
FactGraph `9 → 13`；4/4 新 Fact 均经独立 verifier / SubmissionGate。原 Claim、Support 接口未变，没有第二套 Fact admission。目标仍 OPEN。

**REVOCATION CHECK**  
真实 run 无 revoked Fact，未自然触发撤销；非法 predecessor、级联撤销及恢复拒绝的 6 项隔离检查全部通过。

**CALLS**  
有效 run：14（5 selector + 5 Worker + 4 verifier），均由 DurableRounds 管理。前置失败 run 另有 2 次，独立留存、不计入有效 services。

**TOKENS / UNKNOWN**  
有效 run 已知 790,044：input 747,456（含 cached 418,944），output 42,588；另 1 次 UNKNOWN，总 token 不能确报。前置失败 run 另有已知 39,656 + 1 次 UNKNOWN，均未填 0。

**WALL**  
有效 run 两阶段合计 41 分 8.8 秒；含暂停间隔 42 分 36.5 秒。

**VERDICT**  
**A+ — SUBSTRATE ACCEPTED（修复后）**。Docker 未启动和内部 MCP 审批阻塞已解决；69 项 CRPN/隔离回归检查通过。真实周期、pause/resume、局部注意力及 truth/memory 边界均通过，无剩余基础设施 blocker。

**NEXT STEP**  
保留此次最小权限补丁，接受新 substrate。本轮已停止；源码未提交、未 push。[完整 runtime evidence 与校验清单](/home/wmywb/Noespire/experiments/crpn_first_real_cycle/evidence/INDEX.md)。
