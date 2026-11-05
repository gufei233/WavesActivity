# WavesActivity

GsCore 鸣潮网页活动插件，依赖 [XutheringWavesUID](https://github.com/Loping151/XutheringWavesUID)（XWUID）。

## 使用

先在 XWUID 登录并选中鸣潮账号，再向机器人发送 **`ww预约`**。

插件从 GsCore 的 XWUID 数据库读取发送者当前账号的 token，完成活动授权，加入《第二索拉：未名之梦》愿望单。页面奖励为 **星声×20、贝币×10000**，成功后请到游戏邮箱查收。

- 已加入愿望单的账号自动跳过；提交后会再次查询状态确认。
- 同一账号同时只执行一次，不自动重试领奖请求；失败后可重新发送指令查询。
- 前缀跟随 XWUID 配置，无需额外填写 token；不会修改 XWUID 的账号记录。
- 请通过机器人私聊或群聊使用，HTTP 调用不支持后台结果回复。

## 安装与更新

需要 Python 3.11+、GsCore 和已安装的 XWUID。

1. 将仓库放到 `gsuid_core/plugins/WavesActivity/`，由宿主安装声明的依赖。
2. 发送管理员指令 `core重载插件WavesActivity`，或重启 GsCore。
3. 使用 `ww预约`。更新后或修改 XWUID 前缀后需重新加载插件。

库街区查询和授权沿用 XWUID 的 `KuroUrlProxyUrl`、`LocalProxyUrl`；`NeedProxyFunc` 包含 `all` 或 `run_activity` 时启用代理。预约站点直接连接，避免库街区专用代理拒绝该域名。

## 已结束的钓鱼活动

钓鱼活动已于 **北京时间 2026-11-01 10:00** 结束，功能已停用。`ww活动` 仅回复过期提示，不读取账号、不请求钓鱼接口。

历史实现保留在 [activity.py](WavesActivity/activity.py)，相关关卡参数和模型保留在 [models.py](WavesActivity/models.py)，供后续参考。

## 验证情况

已用抓包账号运行预约业务代码，验证授权交换、角色查询和已领取跳过流程；未重复提交领奖或核对邮箱到账。机器人数据库读取与消息链路尚未做整体验证。按要求未编写或运行回归测试。
