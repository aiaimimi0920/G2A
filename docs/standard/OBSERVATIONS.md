> Non-normative historical working notes. The English G2A_SPECIFICATION.md is the primary review draft and supersedes conflicting wording here.

# G2A 游戏观察 profile 线格式候选

状态：`observations-draft-1`，2026-11-13。这是[标准工作草案](SPECIFICATION.md)第 6 节的具体绑定提案，**不是已注册扩展，不是可发送给当前 SDK 的功能**。不修改 `g2a-design-1` 的已生成契约或 `0.1.0-dev`。

## 1. 选择与兼容性结论

选择复用下一版草案已有的：
- `Descriptor.extensions` / `Requested.extensions` / `Scope.extensions`；
- `Scope.context_categories` 和 `game.context`；
- `context.publish`、`session.events`、`session.snapshot`。

第一版不新增动态 subscribe/unsubscribe 操作。获批类别在会话中静态订阅；变更需求/扩大范围走新 offer 和必要的新批准。游戏可随时收窄实际视野。需要消耗资源或改变世界的“观察”必须走 actions。

`contracts.py` 现状：Extensions 的条目为 `{version, required, value}`，value 可以是 Json；Context 为 `{category, content: Json, provenance}`；Requested/Scope 均允许 Extensions。因此本提案的封装**可以被现有设计结构容纳**。但是：

1. 旧 SDK 根本不实现这个设计线，不能据此称其兼容。
2. 现有 `validate_active_request` 要求请求启用的扩展配置与 Scope 精确相同；本提案遵守这个约束，不把动态观察塞进扩展 value。
3. 现有扩展结构校验不验证本 profile 的业务语义，未注册处理器必须拒绝 required 扩展。
4. 现有 RecoverySnapshot 是 Context 数组，不自动提供下述“每流完整当前快照”；需要 profile 规范约束与独立测试，不能声称现有 harness 已经做到。

临时扩展键使用 `org.example.g2a-observations`，明确为例示命名空间，不声称项目持有域名或已登记正式标识。发布前需确认正式命名空间；实现不得跨标识自动兼容。

## 2. 三个配置阶段

同一扩展的三个配置位置具有不同结构，处理器必须按位置校验：

### 2.1 Descriptor：游戏支持声明

```json
{
  "version": "observations-draft-1",
  "required": false,
  "value": {
    "phase": "catalogue",
    "definitions": [{
      "category": "visible-room",
      "schema_version": "1",
      "schema_digest": "<64-lowercase-hex>",
      "schema": {"type": "object", "additionalProperties": false},
      "modes": ["snapshot", "delta", "retract"],
      "minimum_interval_ms": 250,
      "maximum_age_ms": 2000,
      "maximum_records": 128
    }]
  }
}
```

这是结构示意，示例摘要占位和简化 schema 不可发送。真实 schema 必须声明以下记录 data 的结构；使用现有严格 JSON 数字模型。schema_digest 对规范编码后的 schema 计算 SHA256，必须加已登记的 profile-schema 摘要域；该新域需纳入统一摘要目录后才冻结。

只列调用者允许看到的类别，不公开隐藏对象、隐藏类别或是否存在特殊剧情。支持声明不批准使用。`maximum_age_ms` 是游戏承诺的观察有效窗口，不是无限刷新保证。

### 2.2 Requested：伙伴的需求

value 为 `{phase:"needs", needs:[...]}`；每项为 `category`、可接受的 `schema_versions`、`required`、`maximum_age_ms`、`minimum_interval_ms`、`maximum_records`。

- required 表示缺少该类别则不能满足本次接入，不是强迫游戏披露。
- maximum_age_ms 是伙伴可接受的最大年龄；minimum_interval_ms 是伙伴能够接受的最短推送间隔。
- 游戏与伙伴共同支持结构、限额与新鲜度不存在交集时，必需项拒绝 offer；可选项在结果中明确 rejected。
- Requested 的 context_categories 必须与需求类别一致；不允许在扩展内额外请求未声明类别。

### 2.3 Scope：冻结的最终选择

value 为 `{phase:"selected", categories:[...], rejected_optional:[...]}`。
每个 categories 项完整包含 `category`、`schema_version`、`schema_digest`、`schema`、`modes`、`interval_ms`、`maximum_age_ms`、`maximum_records`、`perspective`。

- categories 必须与本次 Scope.context_categories 完全对应；每个 perspective 必须由游戏绑定本次已验证玩家/席位，不能由伙伴任意指定。
- 只允许从公开候选中选定，不得把支持集合全部当批准集合。
- 配置是完整不可变 Scope 的一部分，scope_digest 覆盖全部字段。
- 活动 Envelope.extensions 携带与 Scope 相同的 `{version,required,value}`；不改 value 的 phase，也不填实时数据。外层 OperationRequest.extensions 必须为空，沿用原数据消息规则。
- profile 被选定后 required 必须为 true，缺少或不支持处理器拒绝相关观察，不能降为任意 context。

## 3. 动态消息映射

`game.context.payload.category` 为选定类别；`payload.provenance` 保留既有权威来源语义；动态内容放 `payload.content`：

```text
ObservationContent = {
  profile: "observations-draft-1",
  stream_id: opaque string,
  revision: positive exact integer,
  world_epoch: opaque string,
  perspective: authenticated principal/seat binding,
  schema_version: exact selected version,
  schema_digest: exact selected digest,
  observed_at_ms: nonnegative exact integer,
  expires_at_ms: nonnegative exact integer,
  mode: "snapshot" | "delta" | "retract",
  base_revision?: positive exact integer,
  records?: [{id: opaque view-local string, data: object}],
  remove_ids?: [opaque view-local string]
}
```

所有标准键严格校验，缺失与 null 不等价；禁止未知键、重复 record ID、records 与 remove_ids 重叠、非有限值和超预算。

- snapshot 必须有 records；不得有 base_revision/remove_ids；完整替换这个流的授权视角，不是全世界。
- delta 必须有 base_revision、records（upsert）和 remove_ids；至少一个非空；不采用任意 JSON Patch，避免路径含义和数组下标歧义。基线必须为接收者当前同 stream/epoch/perspective revision。
- retract 不含 records/base_revision/remove_ids；表示整个流当前不可用，清除其可行动状态。它不证明世界对象已删除。
- revision 必须严格递增；stream_id 在一个会话内唯一，绑定 category、perspective、world_epoch；绑定变化使用新 stream_id，并使旧流失效。
- expires_at_ms 必须大于等于 observed_at_ms，差值不得超过冻结 maximum_age_ms；也不得超出授权/会话有效期限。发送过期观察拒绝；接收已经过期的历史记录只作为过期记录，不恢复当前可行动状态。
- record ID 是当前公开视角内 ID，不允许把全局自增实体计数或隐藏对象哈希作为暗示渠道。
- `data` 必须通过所选 schema，且游戏在验证前已完成字段投影。通过 schema 不代表数据已获授权。

这不是新加一个独立 message ID；去重仍使用 Envelope.id。stream revision 解决观察状态的顺序，不授予权限。

## 4. 流状态与恢复

| 当前状态 | 输入 | 结果 |
| --- | --- | --- |
| absent | 有效 snapshot | active，建立视角基线 |
| absent | delta | 不应用，进入 gap 并请求获准 snapshot |
| active | 精确基线的 delta | 原子 upsert/remove，提升 revision |
| active | snapshot 的更高 revision | 原子替换，提升 revision |
| active | 已知同 revision 同内容 | 忽略重复，不重复作用 |
| active | 同 revision 异内容 | conflict，停止当前流并请求权威恢复 |
| active | retract / 到期 | unavailable，移除可行动数据 |
| 任意 | 新 epoch 或新 perspective | 旧流失效；新流仅由 snapshot 建立 |

`remove_ids` 仅说明记录不再属于本授权视角；不能解释为死亡、删除或任务完成。不在已有基线中的 remove ID 应拒绝整条 delta，避免应用端形成不一致状态；游戏应发新 snapshot 收敛。

历史缺口恢复使用 `session.snapshot`。实现本 profile 的宿主必须在同一切点把每个有效 stream 压成一个完整 snapshot context，而非返回其最新 delta。权限已撤销的流不得在恢复中复活。snapshot 中没有出现的已知旧流视为当前不可用，不代表世界实体不存在。无法提供同切点结果时返回恢复失败/不可用，不伪造完整快照。

慢消费者恢复不能要求回放其失去权限的数据。事件的原受众和当前授权仍须同时成立。

## 5. 主动推送、按需读取与动作边界

本候选只定义静态选定的类别推送和全会话 snapshot 恢复。interval_ms 是最短发送间隔限制，不是必须持续发送相同内容的心跳。没有新观察时不制造世界变化；消费者通过过期规则知道数据已不新鲜。

一键“看当前房间”可由宿主在已授权范围主动发布 snapshot。需要主动扫描、寻路探测、消耗游戏资源或开启门的感知必须先定义动作；其结果如需成为观察，也由 GameAuthority 发布后才取得游戏来源，不让 Agent 自己提升结果可信度。

动态频率调整、任意对象查询、按字段订阅、跨会话共享 stream 不在第一版；不是未定义时允许实现者自由实现，而是未协商不得调用。后续需新 profile 版本。

## 6. 错误及失败行为

- 不支持 profile/精确 schema：feature_unsupported，不能降成普通文本。
- 配置与冻结 Scope 不一致：approval_stale。
- 类别、受众、视角或记录不在授权范围：permission_denied；不暴露隐藏对象是否存在。
- 结构/schema/引用/时间约束不符：invalid_message；不部分应用。
- 基线缺失或事件缺口：history_gap，要求获准 snapshot。
- 同 revision 异内容：使用既有冲突类别，具体机器码在错误目录冻结前不得自造线上常量。
- 超限：resource_limit；不得通过截断一半 snapshot 冒充完整状态。

严格的错误字段仍按主规范；网络无响应仍为 unknown，不推断发布或行动未发生。

## 7. profile 安全预算

schema 只来自冻结可信配置，所有引用必须为本地受控且无循环的定义；第一版可以直接禁用引用以降低实现负担，但正式 schema 方言必须统一，不允许各 SDK 自选。正则、深度、记录数量、schema 大小和每次验证时间必须有可声明的硬预算。

format 注解不是强制断言；未知关键词不得被宣称提供安全限制。profile schema 定义需要采用明确断言子集并产生符合性负例，不能把任意 JSON Schema 当作权限语言。

## 8. 最小非执行性测试向量

| 向量 | 前态/输入 | 预期 |
| --- | --- | --- |
| OBS-01 | 大厅 snapshot 仅含 key、lamp | 成功；隐藏 trap 不出现 |
| OBS-02 | Requested 要求 vault，但游戏未公开 | 拒绝 required 需求；不得告诉 vault 是否存在 |
| OBS-03 | key 离开视角，delta remove key | 从当前视角移除；不宣告 key 被毁 |
| OBS-04 | delta 的 base_revision 跳号 | 整条不应用，snapshot 恢复 |
| OBS-05 | 重复 revision 相同内容 | 无额外状态变化 |
| OBS-06 | 同 revision 内容不同 | conflict，不拼接两份状态 |
| OBS-07 | 离队后回放原 team snapshot | 权限拒绝；不因原 ID 获得旧内容 |
| OBS-08 | world_epoch 改变后旧 delta | 不应用；新 snapshot 才建立基线 |
| OBS-09 | scope 扩展同 ID 换 schema | approval_stale，不能继续按新格式读取 |
| OBS-10 | snapshot 超容量 | resource_limit，不返回看似完整的截断快照 |
| OBS-11 | 恢复宿主只保存最后 delta | 不符合本 profile 的 snapshot 恢复要求 |
| OBS-12 | 游戏发布 retract 后旧结果到达 | 不恢复旧有效状态；依据序号/revision 隔离 |

这些是规范向量定义，不是已运行的测试。后续应转为语言无关输入/输出文件，并与机器 schema 一起冻结。未完成上述契约同步前，不给 SDK 分配“支持 observations”的声明。

