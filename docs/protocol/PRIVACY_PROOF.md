# 隐私主体请求、cutoff 与可信存储回执

[PrivacyHarness](privacy_harness.py) 为 `privacy.request` / `privacy.receipt` 提供字节入口，
组合入口由 29/37 增至 **31/37**。复用既有 codec、字段契约、来源导入、事件过滤和
authority 事务，不修改旧 SDK，也不增加请求方能够填写的“删除完成”字段。

[MemoryStore](memory_store.py) 仅保存固定内存清单、假副本状态、效果和可信回执表。
没有访问或删除文件、真实数据库、备份、游戏存档或任何用户数据。

## 1. 谁向谁提出请求

- 独立 `data_subject` 身份走 `privacy` lane；游戏管理员、玩家控制令牌、伙伴写令牌、
  `results_reader` 不能自动转成隐私权限。固定 endpoint 的实际控制者是已登记伙伴，
  身份的 controller 受众必须与 endpoint 及存储控制者一致。
- 隐私 endpoint 的版本、能力和消息限额来自可信固定协商上下文，`privacy-request`
  必须在已选与双方支持集合中。它不读取游戏会话是否 active，也不借 Grant 签发删除权。
  因此可以在游戏尚未加入、已关闭或 Grant 已撤销后处理，但仍须 fresh、未过期的主体身份。
- wire 只有来源引用和动作。每个引用都必须属于固定 instance/session 的可信导入表，
  controller、完整来源声明和当前会话中的来源绑定一致，且请求者是该来源的已验证主体。
  来源不存在、其他主体、其他控制者、其他命名空间都统一拒绝，混合请求整批不接受。
- `SourceAuthorization` 的 state/expiry 是披露授权，不是让控制者在授权到期后拒绝
  数据主体隐私请求的依据。来源声明来自既有 [SourceImporter](source_import.py) 可信
  证据表，不从请求 provenance 推导主体权。真实身份、来源证明和法律权限认证仍未实现。

`PrivacyHarness` 继承启动层仅为了复用同一个测试分派入口、锁与故障驱动。隐私身份、
请求账本、存储端口与游戏会话权限是分开的；这不要求生产部署把游戏与记忆服务合并。

## 2. 受控范围与保守删除规则

`controlled_scope` 在此 profile 中列出请求涉及的**本控制者来源 handle**，不是全局
数据 ID，也不是“所有副本均已删除”的证明。内存清单在构造时固定；内部 binding 另冻结
每条来源、完整副本清单、主体、动作、cutoff revision、接受时间与原存储 operation ID。

- `stop_disclosure` 停止本方后续披露，不擦除副本，不承诺收回已交付明文。
- `delete_owned_copies` 只处理本控制者持有且可信副本主体集合恰好为请求者的副本。
  多主体混合副本保留并报 `shared_copy`；不因为主体出现在来源标签中就删除其他人的资料。
- 其他控制者副本报 `outside_control`。GameAuthority 已接受的 chat/context outbox
  不属于伙伴存储；与事件接受同事务保存这个已知外部副本事实，事件裁剪、丢回复或重启
  都不能使回执遗忘此例外。源 cutoff 可以收紧合作方的未来投递，但不伪造它已擦除数据。
- 法律/安全保留为可信假端口预置的 `legal_hold` / `security_hold`，可带 `retain_until`。
  不通过该名称声称法律审核已完成。期限届满可提出新请求重新处理；旧回执保持当时事实。
- `done` 表示冻结清单中的所请求处理完成且没有已知例外；有成功处理和例外为 `partial`，
  没有成功处理且存在例外为 `denied`。可信完整空清单可以完成，失联或未知不能冒充空清单。
  已知删除结果只保留必要元数据/墓碑；本模型并不证明真实介质清除或不可恢复。

清单、来源或副本身份在 pending 期间改变时不使用旧作业删除新对象，回执报
`inventory_changed`。本包没有开放持续写入/新备份登记；生产适配器必须将 cutoff 接入
所有写入、恢复、导入与披露路径，才能对动态清单作更强承诺。无法确定来源的派生数据
不能由本模型“自动判定已清除”。

## 3. cutoff、去重与效果的提交切点

1. **接受事务**：先逐条核权和检查有界容量；按主体/请求 ID 拒重并冻结规范摘要。
   同事务写入原存储引用、pending 回执、cutoff 与来源 revoked revision。若有会话，
   同时收紧事件服务的来源表；此时尚无存储删除效果。
2. **派发标记**：提交不可倒退的 dispatched 标记后，至多调用一次固定存储作业。
   `MemoryStore` 的效果和回执表独立于 authority snapshot，不随结果事务回滚。
3. **结果事务**：只读取并核验原 provider operation 的可信回执，验证规范字节精确绑定、
   请求归属、受控范围、状态和例外，然后发布当前 PrivacyReceipt。

同 ID 更换动作、引用顺序或扩展值都属于摘要冲突； optional 未激活扩展仍参与摘要。
不同主体的同 ID 不串账。终态回执不因再次查询、保留期限到期或外部查询异常而改变。

cutoff 一旦提交，存储拒绝、延迟或未知都不能恢复披露。新的 chat/context 接受被拒绝，
旧 event page（包括重复 poll）和 recovery snapshot 重新做来源过滤。首次 join 及可信
导入刷新也继承 cutoff，更高 revision 的重新授权不能复活同一 source handle。
这些隐私操作不追加游戏事件、不续游戏租约；已收到的明文不能靠过滤追回。

## 4. 故障与原结果查询

| 故障点 | 留存事实及恢复规则 |
| --- | --- |
| before_commit | 接受/去重/cutoff 全部回滚；没有派发或假副本删除 |
| after_accept | pending 与 cutoff 已提交，尚未派发；receipt 只读，原 request 可继续一次派发 |
| after_dispatch | 可能完全没有存储记录；保持 pending，不再调用 apply |
| after_effect | 独立存储效果/回执可能存在，authority 仍 pending；查同 provider 引用收敛 |
| before_result_commit | 结果导入回滚，但已删除的假副本不恢复；再查原回执 |
| after_commit | 仅丢回复；重试得到已提交状态，不重删、不重复 cutoff |

privacy 的 wire 状态沿用 `pending`，不另外增加 `unknown` 枚举。端口失联、缺失回执、
错误主体/绑定、畸形回执或未获证的完成都保持 pending。已受理后的响应编码失败用
`internal_failure/outcome=unknown`，不交给外层误报 not_accepted。

`privacy.receipt` 只验证 fresh 原主体并查询同一作业，不执行 apply，也不为尚未派发的
请求偷偷补派。任何与未决请求来源重叠的新 ID 都被阻止，尤其不能绕过“已标派发但
端口无记录”的窗口。无证据时可以持续 pending；不凭超时强制转 done 或重新删除。
此模型没有实现调度队列、超时清理或长期回执回收，128 条容量用尽时明确拒绝新受理。

假账本重启保留隐私账本、cutoff、已知外部副本以及独立存储效果；旧 authority 退休，
损坏账本拒绝读取和新操作，不清空状态来冒充恢复。没有真实磁盘/进程恢复证据。

## 5. 本地验证与发现的接缝问题

[test_design_privacy.py](../../tests/test_design_privacy.py) 有 **38 个测试方法**，覆盖上述
权限、混合来源原子拒绝、两类动作、共享/外部/保留例外、六个故障切点、双线程重复请求、
可信回执校验、chat/context/poll/snapshot 过滤，以及 prejoin/postjoin 重启。

实际聊天链还复现了启动层缺陷：默认控制凭据已有 `device_id=None`，`setdefault` 不会
填入启动设备，导致 ready 后合法写入被拒绝。现只在首次 join 精确绑定设备，既检查
已有呈现设备是否匹配，也不在旧邀请重放时覆写后续控制代次。启动专项和 JS 启动后
真实请求链均验证了修复，而不是只检查 ready 字段。

完整设计验证为 **350 个方法，0 failures/errors/skipped**；原 **42 条模型轨迹**另计。
JS/Python 独立代码夹具为 **23 组编码正反例、158 次 wire 调用、29 个操作**：新增隐私
权限拒绝、接受与结果故障、保留例外、效果后重启、派发缺口及 outbox cutoff 链。
它仍是同一作者的两份实现，不是第三方厂商互通或全协议认证。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
rtk proxy python scripts/verify_design.py --interop --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/privacy-final-verification.json
```

同目录 `privacy-cross-language-final-verification.json` 保存独立互通回执，
`privacy-final-hygiene.json` 核对最终源 hash、UTF-8 无 BOM、AST、链接和增量范围。
启动历史回执保留，不拿其旧 hash 冒充此次设备绑定修复后的验证。

## 6. 剩余范围

该检查点曾剩 6 个入口；玩家转发现由 [后续工作包](PLAYER_FORWARD_PROOF.md) 补齐，当前还剩五项 Relay 操作，详见 [范围表](SESSION_OPERATION_COVERAGE.md)。
本包不证明真实身份/签名、跨服务 cutoff 原子性、动态副本/备份发现、混合数据拆分、
来源不明的正文识别、真实存储删除、永久无残留、法律合规、第三方互通或生产发布。
没有提交、推送、部署或运行 GitHub Actions。
