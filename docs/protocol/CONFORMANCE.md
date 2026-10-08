# 符合性声明与本地验证包

G2A 按角色、精确版本、能力、信任配置、绑定和证据级别声明符合性，不能用“全部支持”
一个勾选代替。本文不是第三方认证机构，也不授予发布、许可、商标或生产安全认可。

## 1. 证据级别

| assurance | 可以说明什么 | 不能据此说明什么 |
| --- | --- | --- |
| design | 规范、字段契约、伪代码和逐步符号推演完成相应设计检查 | 真实 SDK/网络/身份端口运行成功 |
| mock | 固定身份、逻辑时钟、假世界/设备的状态转换得到实际执行证据 | 真实并发、持久化、密码学、窗口或引擎已验证 |
| adapter | 指定 revision 的具体身份/存储/引擎等适配器通过相应测试 | 未测适配器或实际部署也通过 |
| deployment | 精确部署配置/版本和环境有实际运行证据 | 其他厂商、其他部署、无限故障交错、法律批准 |

schema、unit、model、symbolic、adapter、deployment 是 evidence.kind，不同于声明主体的
assurance。一个设计包可以同时引用结构测试和人工推演，但不能因此自动提升到 deployment。
本工作区当前证据属于 design/mock，不包含生产 adapter/deployment 证据。

## 2. 可移植验证入口

Python 3.11+，使用项目已有依赖 jsonschema（本轮验证版本 4.23.0）；不要求模型账户、
API key、Mot 服务器、Godot、GitHub Actions 或联网。安装依赖属于环境准备，测试本身
不访问网络。建议在隔离环境准备，测试产物写到用户临时目录。

在 G2A 根目录：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk python scripts/verify_design.py
```

也可从任何工作目录通过脚本绝对路径启动。可选完整回执：

```powershell
rtk python scripts/verify_design.py --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/unified-verification.json
```

该命令实际执行：

1. 只读检查生成 schema、操作目录、错误目录和声明模板是否与声明源一致。
2. 重放 42 条固定模型流程，要求 42 passed / 0 failed。
3. 运行全部 test_design_*.py；失败、错误、跳过或零测试都不能通过。
4. 输出逐项测试日志、Python 版本、时间、子命令返回码和相关源文件 SHA256。

返回码非零即失败。`passed=true` 只表示上述本地门禁通过，不是整个协议、真实部署或法律
事项的自动认证。人工推演和最终完整性审计必须单独阅读，不因报告生成成功而自动通过。
脚本默认只读仓库；显式 --output 才写回执，不将日志混入源码。

可选跨语言检查：安装 Node.js 后执行 `rtk proxy python scripts/verify_design.py --interop`。
该选项实际调用独立 JS 编码器/客户端和 Python 内存服务；失败、Node 不可用或非成功回执
均使门禁失败。不带选项时明确记录 `not_run`，不引入 Node 依赖或隐式跳过。
详情、实际操作子集和同一交付方的独立实现限制见 [统一会话验证](UNIFIED_SESSION_PROOF.md)。

## 3. 声明模板与字段

[conformance.template.json](conformance.template.json) 由声明源生成，初始全部
`not_evaluated`，不会预填通过结果。填报副本应与精确来源 revision 一起保存；不要把模板
本身改成某家实现的自评结果。其结构为 contracts.schema.json 的 ConformanceStatement。

- subject：被评估的设计包、假实现或实际实现的名字与精确 revision。
- design_revision：本文设计修订；wire_versions 则单独列实际支持版本，不能混用。
- roles：使用机器目录里的验证后角色名；需要全部设计覆盖时 subject.artifact_kind=design。
- features/trust_profiles/bindings/ledger_durability：本次评估的能力和端口条件。
- evidence：稳定 id、类别、证据文件/地址、具体 case_refs，可附 SHA256。
- coverage：每项操作的 verdict、引用的 evidence_ids 和明确限制。
- exclusions：没有评估的范围，不用隐藏在脚注中；reviewed_by 标明实际复核者。

`validate_statement` 检查字段、引用、能力依赖、重复条目、passed 是否有证据，及声明范围
是否漏操作。design 总体 passed 必须覆盖目录全部操作；实现声明至少覆盖所声明角色与
能力的操作。adapter/deployment 的通过项必须引用相应级别证据；纯 test-enrolled 不能
宣称生产 deployment。模板没有真实证据时，不能只把 status 改成 passed。

但该检查器不验证 reviewer 身份、不替你阅读 artifact，也不证明链接内容真实。正式评估
必须人工或独立工具核对证据对象、hash、运行环境、测试分母与限制，防止“有链接即通过”。

## 4. 操作与不变量追溯

- [STATE_TRACES.md](STATE_TRACES.md)：全部 38 个操作的前态、输入、提交点、后态、反例及证据级别。
- [CONFORMANCE_AUDIT.md](CONFORMANCE_AUDIT.md)：D01–D16、R01–R17、S01–S14、I01–I10 的设计责任。
- [WALKTHROUGH_RESULTS.md](WALKTHROUGH_RESULTS.md)：42 条实际模型轨迹与 M01–M10 人工推演。
- [RELATION_CONTRACT.md](RELATION_CONTRACT.md)：字段合法之后仍须检查的权限和跨对象关系。
- [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md)：当前尚未关闭的工作，不以旧完成声明替代新审计。

## 5. 可选能力与非适用项目

无 actions 的最小伙伴不必实现世界执行器，不能因此称为不符合核心；但不得接受 action.request
并返回伪成功。没有 presentation 的云端伙伴不创建桌面占用，协议仍必须定义对应拒绝/缺省
路径。未声明能力的真实适配器测试可以列非适用，不能把它们算作 passed；设计包则仍需
描述该可选能力的契约，所以不能用不适用删掉本设计范围。

失败、unknown、partial、pending、not_evaluated 均是有意义的结果，不是为了让报表好看就
转换为成功。生产实现、公开发布和权利人决定继续使用独立门禁。
