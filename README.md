# WavesActivity

GsCore 鸣潮网页活动插件，依赖 [XutheringWavesUID](https://github.com/Loping151/XutheringWavesUID)（XWUID）。

## 使用

在 XWUID 登录并选中鸣潮角色，再通过机器人私聊或群聊发送 **`ww预约`**，参与《鸣潮：永明的烬焰》年度篇章预约。 [活动页面](https://newfederation.kurogames-global.com/)

插件读取当前角色绑定的库街区 token，提交预约和预约页分享任务，并查询服务端状态确认结果。已完成的任务会自动跳过，指令前缀跟随 XWUID 设置。

预约成功后，等 **2026 年 12 月 22 日新版本开服**再登录游戏，领取 **100 星声**。

## 安装与更新

需要 Python 3.11+、GsCore 和已安装的 XWUID。

1. 将仓库放到 `gsuid_core/plugins/WavesActivity/`，由宿主安装声明的依赖。
2. 安装、更新或修改 XWUID 前缀后，发送管理员指令 `core重载插件WavesActivity`，或重启 GsCore。

库街区查询和授权沿用 XWUID 的 `KuroUrlProxyUrl` 和 `LocalProxyUrl`。当 `NeedProxyFunc` 包含 `all` 或 `run_activity` 时启用库街区代理。预约接口直连。

## 历史活动

- **钓鱼活动**已于 2026 年 11 月 1 日 10:00（北京时间）结束。`ww活动` 仅回复过期提示，源码保留在 [activity.py](WavesActivity/activity.py)。
- **《第二索拉：未名之梦》愿望单**已过期，原预约源码保留在 [wishlist.py](WavesActivity/wishlist.py)。
