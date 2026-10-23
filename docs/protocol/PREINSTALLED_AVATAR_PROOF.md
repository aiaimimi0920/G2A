# 预装形象的精确绑定与设备准入

## 协议合同

既有 Avatar.preinstalled 的 asset_id、revision、format 整体冻结进 Scope，并沿用
forced_avatar → game_avatar → default_avatar 的选择顺序及 accepted_formats 校验。
不新增公开操作。预装形象不要求协商 assets，不生成下载 ResourcePolicy，不调用
asset.resolve，也不能借 manifest 路径给预装对象替换内容。

## 独立 Renderer 登记

ResourcePorts.register_installed 是可信 Renderer 夹具入口：校验完整 Avatar、设备 ID
和 content_digest 后，登记精确版本身份的内容摘要及设备可用性。相同完整 Avatar
在不同设备必须映射到相同摘要；更换摘要必须使用新 revision/身份并重新协商，不能
静默改变旧 Scope 选中的内容。目录最多 128 个身份、16 个设备，重复精确登记幂等。
设备库存可以变得不可用，但目录的旧内容绑定不自动删除，避免同版本重新绑定。

这里的摘要来自可信 Renderer 见证，不是客户端声明即可信；模型不读取或加载真实
文件，也不声称已验证任意模型格式、安全沙箱或版权许可。

## ready、呈现及控制恢复

预装对象无需网络准备，但每次使用目标设备时必须重新验证完整版本库存：

- 无呈现配置的准入在 finish_admission 检查当前设备；没有设备使用固定模型的
  fixture-headless 设备。缺失、错误 revision 或格式不能回退，准入失败关闭。
- presentation.acquire 在产生设备效果前检查目标设备库存；其他设备上存在不算通过。
- 不带呈现的 resume 在代次变更之前检查库存，拒绝时保持原控制代次。
- handoff 在独立目标设备准备阶段重新检查。失败不恢复旧 writer；成功仍需旧设备
  release、目标 acquire 和独立 ready 提交，预装形象不绕过呈现协议。
- 假账本重启保留独立资源端口，ready 仍须重查当前库存，不能只信旧账本状态。

manifest 路径仍沿用原闭包准备、缓存、策略和 Renderer 能力验证。本次只把共同
ready/设备门禁分派到选中形象类型；不会把预装对象伪装成已下载 manifest。

## 证据及未完成项

八个新测试方法覆盖无 assets 准入、无下载/解析/缓存写入、缺失和错版本不回退、
跨设备内容绑定冲突、呈现目标检查、重启后库存丢失、目录容量与 bool revision
拒绝，以及 resume/handoff 的成功与失败边界。原 30 个 manifest 资源测试另行通过。

这是固定可信目录的可执行模型，不是生产安装器。目录的长期回收、防回滚持久化、
原生格式/骨骼兼容、实际 Renderer 验证、设备并发更新尚未证明。固定配置跨语言
增量见下一节，不等于任意设备/格式组合互通。
新安装或更新仍不能自动改写正在使用的 Scope；生产目录必须实现同版本内容不变。

## JS/Python 固定配置互通增量

JS 实际新增 11 次正式字节请求：描述、冻结预装 Scope、批准、邀请与 join、目标库存
缺失拒绝、只有其他设备库存时拒绝、正确库存下呈现 acquire 提交后丢响应、假重启
后的 acquire 重试、join 原事实读取以及未协商 assets 时的 asset.resolve 拒绝。
跨设备同版本不同摘要登记也在可信夹具中拒绝，不接受客户端自报替代安装证据。

本配置同时协商 resume，因此沿用其所需的 durable 模型配置。重启后的 join 重试按既有合同返回
completed_without_secret，不重新交付控制凭据；游戏会话已独立 ready。设备只渲染
一次，fetch_hops/parse_calls/cache_count 均为零。没有修改协议去迎合客户端误以为
重启后仍能取回秘密的假设。

互通门禁新增 preinstalled 子报告：ready=true、render_calls=1、下载/解析为零、
wire_calls>=11，全部数值严格检查。正式操作仍为 38 项，总 wire 请求增至 421 次。
preinstalled_start/register 都是可信管道夹具，不是新的公开安装接口。
