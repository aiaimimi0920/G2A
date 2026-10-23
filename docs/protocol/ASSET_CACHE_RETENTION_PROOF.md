# 关闭会话资源缓存的有界回收

## 回收条件

AssetHarness.compact_closed_asset_cache 是可信维护入口，不是公开协议操作，不删除
磁盘文件。一次最多清理 128 个缓存条目，默认 64；bool、零和越界预算明确拒绝。

回收前必须同时证明：authority 账本健康、会话已关闭、所有 presentation_jobs
都有当前设备 epoch 下有效的独立释放完成证据。仅关闭会话、设备离线或本地观察
occupations 为空均不能替代 release ACK/已验证到期证据。

例如设备 release 已成功，但 authority 在记录 ACK 前故障，此时仍拒绝 GC。重试
取得并提交原释放回执后才允许回收。GC 不自动联系设备、不猜测其是否还在读取内容，
也不偷偷替代停止补偿调度。没有呈现任务的 headless 会话不需要虚构设备 ACK。

## 内容、回执和身份分离

事务仅删除选定的 asset_cache 内容并清除关闭会话的 asset_binding；不删除
asset_receipts、关闭/撤权事实或呈现回执。部分清理与重复清理均有明确 removed/
remaining 结果；旧 asset.resolve 不能凭历史成功回执绕过当前 Grant/会话检查。

预装 installed_catalog/installed_devices 是独立 Renderer 库存和不可重绑定身份目录，
不属于下载缓存。关闭预装会话执行本维护操作返回零删除，不能借缓存 GC 解除同版本
内容绑定或卸载其他设备正在使用的预装形象。

## 故障和证据

可信时间维护仍先独立提交。GC before_commit 故障不删除缓存；after_commit 丢响应
保留已删除部分，假账本重启后可以继续有界清理。损坏恢复的 ledger 不允许 GC。

六个新测试方法覆盖活动会话拒绝、关闭但设备不可达拒绝、独立 release/ACK 间隙、
部分/重复 GC、回执保留且旧请求不可恢复权限、两种提交故障与重启、严格预算和
不健康账本、headless 清理及预装目录保持不变。

本轮只关闭固定单会话下载缓存的生命周期缺口。活跃会话缓存替换、跨会话共享引用、
缓存回执已由后续 [回执期限与回收](ASSET_RECEIPT_RETENTION_PROOF.md) 补充；
预装目录长期回收及真实文件/Renderer 并发持有仍需独立合同；
不把本模型作为生产文件删除授权。
