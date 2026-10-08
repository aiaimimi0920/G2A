# 草案编码与摘要契约

状态：`g2a-design-1` 的设计补充，不分配新的可部署 wire 版本，不升级旧 SDK。
本文件将总设计 §15 的“固定版本规范编码”落实为 `g2a-cjson-1`，参考算法见
[codec.py](codec.py)。这是内容比较算法，不是自创的签名或身份协议。

## 1. 输入数据模型与限额

JSON 原始输入必须为无 BOM 的严格 UTF-8。允许 null、布尔、字符串、整数、数组和对象；
禁止浮点词法（包括 `1.0`、`1e0`）、NaN、Infinity、整数 `-0` 和未配对 surrogate。
合法 surrogate pair 解码为同一个 Unicode 标量；字面字符与其合法转义等价。
重复键在转义解码后判定，因此 `"a"` 与 `"\u0061"` 不能同时存在。

整数范围固定为 `[-9007199254740991, 9007199254740991]`；布尔不属于整数。
禁止使用大整数字符串绕过一个本来应为整数的字段。小数业务值需单独定义整数单位，
或在动作 schema 中定义明确的十进制字符串；不得全局隐式转换。

| 限额 | 本地符合性配置默认值 | 定义 |
| --- | --- | --- |
| max_bytes | 1048576 | 原始输入和规范输出各自的 UTF-8 字节数 |
| max_depth | 32 | 根数组/对象深度为 1，嵌套容器逐级加 1；标量不增加容器深度 |
| max_nodes | 65536 | 根、容器、标量和对象键分别计为一个节点 |
| max_container_items | 4096 | 每个数组的元素数或每个对象的键数 |
| max_string_bytes | 65536 | 每个解码字符串（含键）的 UTF-8 字节数 |

这些是验证配置默认值，不是强制部署容量。服务器解码前硬上限、已协商 Scope 限额和
操作限额取最严值；不能因客户端发送更大声明而增加容量。接收端先限原始字节与嵌套深度，
再完整解析并校验节点/字符串/数组。参考工具只接收已取得的 bytes；实际网络适配器必须
在读取过程中限流，不能先无限缓存再调用它。错误码不得包含输入、令牌或内部堆栈。

## 2. 唯一编码

1. 对象键按 Unicode 标量值序列逐字典序排序，不使用 UTF-16 code-unit 排序。
2. 数组顺序保持；规范编码不排序、去重，也不把数组解释为集合。
3. 对象分隔符仅 `,` 和 `:`，不输出任何额外空白或结尾换行。
4. 字符串用双引号；双引号和反斜杠分别转义为 `\"` 和 `\\`。
5. U+0008、0009、000A、000C、000D 使用 `\b`、`\t`、`\n`、`\f`、`\r`；
   其余 U+0000–001F 使用小写十六进制 `\u00xx`。
6. `/` 不转义，其余合法 Unicode 标量直接输出 UTF-8（包括 U+2028、U+2029）。
   不做 NFC/NFD、大小写、路径、URL、时区或其他归一化。
7. 整数为最短十进制，零为 `0`，无前导 `+` 或 `0`；布尔和 null 为小写关键词。

字段缺失与显式 null 不等价；只有字段契约明确允许 null 时才能出现 null。
在摘要前完成字段校验；不能先丢弃未知字段再判定重复请求。可选未知扩展不执行，
但保留在完整请求摘要中，防止同 ID 改内容被误认为原请求。

数据操作 chat.send/action.request/action.cancel/context.publish/player_chat.forward 的
OperationRequest.extensions 固定为空对象；扩展只放对应 Envelope.extensions，因而包含
在 message 摘要中。控制操作扩展仍在外层，包含于 control 摘要。详见
[研究决策](PROTOCOL_RESEARCH.md) §3；这是草案结构收紧，不升级旧 wire 实现。

## 3. 摘要域与确切投影

`digest(domain, value) = lowercase_hex(SHA256(UTF8("g2a-cjson-1") || 0x00 ||
ASCII(domain) || 0x00 || canonical(value)))`。

| domain | value | 不包含 |
| --- | --- | --- |
| scope | 完整已验证不可变 Scope | UI 显示、审批证据、秘密 |
| control | `{version, operation, payload, extensions}`，四键均必需 | request_id（在去重键内）、HTTP 头、凭据 |
| message | 完整 Envelope | 传输 request_id、HTTP 头、凭据 |
| result | `{state, effect, result}`，result 仅在字段契约允许时为 null | 接收时间、服务端 result_revision |
| relay | 完整 OperationRequest | inner_auth_proof、外层凭据与 RelayCall 截止时间 |
| auto-rule | `{scope_without_timestamps, maximum_grant_duration_ms}` | 本次绝对 created_at 和 expires_at |
| join-intent | 完整 JoinIntent | 邀请秘密、HTTP 凭据 |
| action-arguments | 完整已校验动作 arguments 对象 | action ID（由确认元组/执行记录另外绑定） |
| action-definition | 完整 ActionDefinition | 传输 request_id、凭据 |

control/message 的已认证主体、受众与会话仍属于各自去重键或授权检查，不能因为摘要
不含凭据而跳过认证。Relay 重试只能复用首次接受的期限，不能借省略 deadline 延长。
所有期限、数量、revision 等安全字段除表中明确排除者外必须保留，不能仅比较选定业务参数。

语义为集合的数组在创建不可变 Scope 时由权威端按字段类型排序并拒绝重复；一经创建，
保存原快照，不在重试时重新排序。对象元素按其 canonical 字节排序，字符串按 Unicode
标量排序。普通消息数组不适用这条创建规则。

摘要一致仅说明在给定编码/域下内容一致，不证明发送者身份、同意、资源可信或未发生碰撞。
秘密不得作为普通摘要字段公开；生产身份适配器采用何种成熟签名标准属于独立契约。
资源 content_digest 对实际资源字节计算，不对 JSON 包装计算，也不添加上述内容比较域前缀。
其算法标识和许可/来源校验独立；原伪代码中其他 digest 简写须在各操作字段契约中逐一绑定，
不能擅自套用 scope 域或将此目录冒充全部内部记录的摘要登记表。

## 4. 字段通用约束与后续契约边界

- wire 时间使用 UTC Unix epoch 毫秒整数，期限以服务端受信时钟判断；逻辑模型的 tick
  不是 wire 时间。duration 使用非负毫秒整数，计数/序号为非负整数，generation/revision
  从 1 开始，均不得超过上述精确整数范围。时钟不可信时拒绝续权，不猜测宽限期。
- ID 为不透明、大小写敏感的字符串；不得因 URI 解码、trim、Unicode 归一化或大小写
  转换改变身份。身份三元组必须逐字段比较。字符串格式合法不代表身份已认证。
- 未知标准字段拒绝，扩展只在 extensions 内；对象字段是否可缺失、长度及 null 规则
  必须由对应操作的字段契约固定，不靠本 JSON 编码层推断。
- OperationRequest 的 version 与 extensions 是必需字段，空扩展显式为 `{}`；完整形式
  为 `{version, operation, request_id, payload, extensions}`，不能沿用总设计里的简写漏字段。
- OperationReply 恰好包含 result 或 error 之一，必须回显可解析原请求的 request_id；
  完全无法解析出合法关联 ID 的边界错误不得伪造已接受请求的回执。

本文件完成编码层与摘要投影，不等于所有业务 payload 已有机器 schema，更不等于真实
网络绑定已实现。操作级 schema、所有错误码的封闭目录、跨语言实现和真实适配器验收
需分别记录，不能用 codec 测试代替授权与状态机测试。
