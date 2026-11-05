"""Register the activity command and connect plugin lifecycle hooks."""

from gsuid_core.logger import logger
from gsuid_core.server import on_core_shutdown, on_core_start, on_core_start_before
from gsuid_core.sv import SL, SV, Plugins

from .runner import activity_handler, stop_activity_tasks, wishlist_handler

Plugins(name="WavesActivity", allow_empty_prefix=False)
sv = SV("鸣潮活动", priority=3)
_registered = False


@on_core_start
@on_core_start_before
async def register_commands() -> None:
    global _registered
    # Normal startup registers before accepting messages; reload only invokes on_core_start.
    if _registered:
        return
    # Core reload removes hooks without running them; task names survive module replacement.
    await stop_activity_tasks()
    xwuid = SL.plugins["XutheringWavesUID"]
    prefixes = [prefix for prefix in xwuid.prefix if prefix]
    if not xwuid.disable_force_prefix:
        prefixes.extend(xwuid.force_prefix)
    if xwuid.allow_empty_prefix:
        prefixes.append("")
    prefixes = list(dict.fromkeys(prefixes))
    if not prefixes:
        raise RuntimeError("XWUID 未配置可用指令前缀，无法注册活动指令。")
    sv.TL.clear()
    commands = tuple(prefix + "活动" for prefix in prefixes)
    wishlist_commands = tuple(prefix + "预约" for prefix in prefixes)
    sv.on_fullmatch(commands, block=True, prefix=False)(activity_handler)
    sv.on_fullmatch(wishlist_commands, block=True, prefix=False)(wishlist_handler)
    _registered = True
    logger.info(f"[鸣潮活动] 已注册指令：{', '.join(commands + wishlist_commands)}")


@on_core_shutdown
async def shutdown() -> None:
    await stop_activity_tasks()
