# 资源准备、闭包缓存与准入验证

[AssetHarness](asset_harness.py) 组合既有呈现/控制/准入/会话模型，新增 asset.resolve，
统一入口 **28/37**。底层 [ResourcePorts](resource_ports.py) 是可信传输见证、固定声明式
parser 和 Renderer 能力登记；没有网络请求、文件解压或动态资源代码执行。

## 1. 批准范围与资源选择

沿用 forced_avatar → game_avatar → default_avatar 的选择顺序；选中不兼容对象不自动
回退。当前只支持 manifest avatar，preinstalled 明确拒绝，不能把字段契约齐全当作所有
形象配置都可用。Scope 同时冻结选择的完整 Manifest 和本地 ResourcePolicy，经玩家精确
批准后才能领取邀请。配置变更不静默扩大原 Scope。

asset.resolve 仅接受固定 resource_owner 凭据，session/Scope 摘要/完整 root Manifest
必须匹配批准记录。普通玩家、伙伴、游戏或呈现凭据均不自动拥有资源角色。不接受任意
额外资产路径；原有关系检查继续约束依赖深度、数量、重复身份/内容及总声明字节数。
冻结 Manifest/ResourcePolicy、重复 asset_id 的声明和解析后的 compatibility 都使用
`g2a-cjson-1` 规范字节比较；`true`/`1`、`false`/`0` 不等价，对象键排列不影响等价性。

## 2. 受控传输和实际 fixture 字节

每个资源的可信传输响应包含完整重定向链、TLS 验证见证、DNS 候选集和实际连接地址。
每一跳都必须同时属于 Scope 与该 Manifest 的批准 origin，HTTPS 无用户信息或 fragment，
相邻跳关联一致，实际连接位于 DNS 候选集。默认拒绝非公网、组播和未指定地址；只有
Scope 显式允许 private network 时才允许相应候选，仍不扩大 origin。IPv4-mapped IPv6
按实际 IPv4 类别检查。跳数、候选数和分块数都有上限，畸形端口见证不能漏成裸异常。

这些是真实执行的**假见证检查**，不是说已经验证 DNS 服务器、TLS 实现或网络重绑定。
读取的是内存中预置的 bytes 分块：逐块限制尺寸，精确比较实际长度与 SHA-256；短流、
超长流及摘要不同均失败。请求端口只接收批准 URL 和 Accept，不附加会话 token/cookie。

唯一格式为 `application/vnd.g2a.fixture-avatar+json` / `fixture-1`，profile 为
`fixture-avatar` revision `1`。parser 实际解码 bytes，要求闭合字段、匹配兼容性和直接
依赖摘要；model 只有 label。文件清单仅允许声明式 `.txt`/`.json` 数据，不允许链接、
可执行类型、绝对/盘符/反斜杠/父目录路径。没有把任意 GLTF、ZIP 或嵌入脚本交给真实引擎。
解包量按 UTF-8 内容实际长度计算，并在整个唯一依赖闭包上累计，不只检查每个文件。

## 3. 缓存、收据和失败提交点

资源先在暂存区按依赖顺序完整验证，全部成功后才将整棵闭包、root 绑定和 AssetReceipt
放入同一 authority 事务。后面的根资源失败时，前面已解析的依赖不会成为可见半成品。
这比逐资源发布更保守；已有完整缓存不因别的失败被删除。

缓存身份包含内容所处的完整 Manifest、parser revision、策略内容/revision 及可接受的
issuer/license 声明集合，避免同 bytes 换许可或依赖元数据后复用旧批准。许可接受是固定
本地策略，不是对第三方版权真实性的法律保证。命中缓存仍重新验证闭包和当前许可规则。
原请求在 parser/policy 改变后不能直接重放旧成功收据，新请求需要重新验证。

- before_commit：可以已经读取/解析，但不发布任何缓存、绑定或操作收据；重试可再次读取。
- after_commit：收据已提交，原 ID 重试不再读取/解析；新 ID 的精确缓存命中也不重复读取。
- 已验证资源失败：当前窄模型保守关闭准备会话，并同事务保存 terminal failed 收据。
  返回合法 `operation_failed/outcome=accepted`，可由原请求重试或所属玩家 operation.get
  查询，不被外层错误映射误写为 not_accepted。公开 details 仅使用已定义的 resource 和
  operation_ref；内部原因保存在模型账本，不临时扩张 ErrorDetails schema。
- 准备后、发布前发生撤权或配置变化：重新检查阻止发布，保留已独立提交的撤权，不能随
  当前资源事务回滚。相关测试使用可信调度注入点，不宣称真实并行下载已验证。

## 4. 与设备及控制权的连接

未取得完整资源绑定时，finish_admission 保持 pending，presentation.acquire 不允许产生
设备效果。解析成功后还必须验证独立 Renderer 能力登记；不支持当前设备则闭会，不发
ready。handoff 复用已验证缓存，但目标 Renderer 独立检查；缓存成功不意味着所有设备都
可渲染。无 presentation 的配置仍要准备资源；同设备 resume 也不得跳过已失效的 parser
收据。假 authority 重启保留缓存和可信端口状态，但不恢复旧写凭据。

## 5. 反例与实际验证

[test_design_assets.py](../../tests/test_design_assets.py) 共新增 **30 个方法**（首轮 27 个、
恢复收尾再补 3 个），覆盖批准/角色、
来源/重定向/连接绑定、分块大小和摘要、路径/链接/活动字段、闭包总量、缓存版本/许可、
故障前后提交、准备中撤权、设备能力、handoff、无呈现 resume 及假账本重启。

新负例实际发现并修复：

1. 可信传输见证缺少 url 时出现 `KeyError: 'url'`；补齐结构与类型检查后，进入有回执的
   资源失败路径，不留下半成品缓存。
2. 无 presentation 时更换 parser revision 后，resume 仍返回 ready，负例报告
   `ContractError not raised`；现在在代次事务内检查资源绑定，失败不交凭据也不偷偷升代。
3. Python 的布尔/整数相等性使 Manifest 类型变化仍获成功收据、解析后不匹配的兼容性
   被接受、重复依赖元数据变化被忽略。恢复收尾时三处均实际复现；现改为规范字节比较，
   同时拒绝本地 ResourcePolicy 的同类类型漂移。新回归覆盖两个方向的 `true`/`1`、
   `false`/`0`，以及合法对象键重排。修复前证据保存在同目录 assets-canonical-before.json。

完整门禁累计 **283 个设计方法**，原 **42 条模型轨迹**保持独立分母。JS/Python 夹具累计
**23 组编码正反例、99 次 wire 调用、26 个操作**。JS 独立构造 fixture bytes、SHA-256 和
Manifest；成功链验证 pre/post-commit、缓存命中、资源→呈现→ready，失败链验证根摘要
损坏时 0 个可见缓存、accepted failure、失败查询和禁止秘密交付。原有业务/控制/呈现
场景继续运行；另从 JS 发送 Manifest 类型变化，验证 not_accepted 且 0 次读取/解析。
不是第三方厂商或全 schema 客户端认证。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk proxy python scripts/verify_design.py --interop --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/assets-final-verification.json
```

独立互通回执为同目录 assets-cross-language-final-verification.json，交付 hash/UTF-8 无
BOM/AST/本地链接检查为 assets-final-hygiene.json，以实际结果为准。

## 6. 仍未完成

资源阶段当时未装配的 launch.request 已由后续 [启动增量](LAUNCH_PROOF.md) 补充；当前
未装配入口还有 player_chat.forward、privacy.request/receipt 和五个 Relay 操作，完整列表
见 [范围表](SESSION_OPERATION_COVERAGE.md)。资源本身仍无 preinstalled、
真实格式 parser/沙箱、真实流式网络、缓存长期回收和跨进程存储。当前单锁/单会话/有界
闭包验证不等于所有交错、网络攻防、版权或部署验收。设备租约更新与后台补偿等上一轮
限制仍保留。没有修改旧 SDK、提交推送、部署或运行 GitHub Actions。
