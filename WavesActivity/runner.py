"""Own background jobs and report their outcome to the original conversation."""

import asyncio
import traceback
from copy import copy
from functools import partial
from json import JSONDecodeError

import aiohttp
from pydantic import ValidationError

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.sv import get_plugin_available_prefix

from .bridge import Account, get_account, get_network
from .models import ActivityError
from .wishlist import WishlistActivity

TASK_PREFIX = "WavesActivity:"
_tasks: dict[str, asyncio.Task[str]] = {}
_deliveries: set[asyncio.Task[None]] = set()


async def execute_activity(account: Account, start: asyncio.Event) -> str:
    await start.wait()
    network = get_network()
    logger.info(f"[鸣潮预约] 开始执行，网络代理={'开启' if network.proxy else '关闭'}")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        result = await WishlistActivity(session, network).run(account)
    logger.info(f"[鸣潮预约] 执行完成，新增愿望单={result.newly_joined}")
    return result.render(account.uid)


def failure_message(error: BaseException) -> str:
    if isinstance(error, ActivityError):
        logger.warning(f"[鸣潮活动] {error}")
        message = str(error)
    elif isinstance(error, (aiohttp.ClientError, TimeoutError)):
        logger.warning(f"[鸣潮活动] 网络请求失败：{type(error).__name__}")
        message = "网络请求失败，请检查 XWUID 代理配置后重试。"
    elif isinstance(error, ValidationError):
        fields = "、".join(
            f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
            for item in error.errors(include_input=False, include_context=False, include_url=False)
        )
        logger.error(f"[鸣潮活动] 接口响应结构变化：{fields}")
        message = "接口响应结构发生变化，请联系管理员更新插件。"
    elif isinstance(error, JSONDecodeError):
        logger.error("[鸣潮活动] 接口返回了非 JSON 内容")
        message = "接口返回了非 JSON 内容，请稍后重试。"
    else:
        # Format the traceback without frame locals, which can contain account credentials.
        detail = "".join(traceback.format_tb(error.__traceback__))
        logger.error(f"[鸣潮活动] 后台执行异常：{type(error).__name__}\n{detail}")
        message = "后台执行异常，请联系管理员查看日志。"
    return f"[鸣潮预约] {message}\n可稍后重新发送预约指令查询；已在愿望单中的角色会跳过领取。"


async def deliver_result(bot: Bot, message: str) -> None:
    await bot.send(message)


def delivery_done(task: asyncio.Task[None]) -> None:
    _deliveries.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        detail = "".join(traceback.format_tb(error.__traceback__))
        logger.error(f"[鸣潮活动] 最终结果发送失败：{type(error).__name__}\n{detail}")


def activity_done(uid: str, bot: Bot, task: asyncio.Task[str]) -> None:
    _tasks.pop(uid)
    if task.cancelled():
        logger.info("[鸣潮活动] 后台任务已取消，服务端已完成的进度保留")
        return
    error = task.exception()
    message = failure_message(error) if error is not None else task.result()
    delivery = asyncio.create_task(deliver_result(bot, message), name=TASK_PREFIX + "result")
    _deliveries.add(delivery)
    delivery.add_done_callback(delivery_done)


async def activity_handler(bot: Bot, ev: Event) -> None:
    prefix = get_plugin_available_prefix("XutheringWavesUID")
    await bot.send(
        "[鸣潮活动] 钓鱼活动已于北京时间 2026-11-01 10:00 结束，功能已停用。\n"
        f"领取本期愿望单奖励请发送【{prefix}预约】。"
    )


async def wishlist_handler(bot: Bot, ev: Event) -> None:
    if ev.task_event is not None:
        await bot.send("[鸣潮预约] 请通过机器人聊天发送指令，HTTP 调用无法接收后台完成结果。")
        return
    account = await get_account(ev.user_id, ev.bot_id)
    if account is None:
        prefix = get_plugin_available_prefix("XutheringWavesUID")
        await bot.send(f"[鸣潮预约] 当前账号未绑定有效 token，请先发送【{prefix}登录】完成 XWUID 登录和绑定。")
        return
    if account.uid in _tasks:
        await bot.send("[鸣潮预约] 该账号正在执行活动，请等待完成结果。")
        return
    start = asyncio.Event()
    task = asyncio.create_task(execute_activity(account, start), name=TASK_PREFIX + account.uid)
    _tasks[account.uid] = task
    task.add_done_callback(partial(activity_done, account.uid, Bot(bot.bot, copy(ev))))
    try:
        await bot.send("[鸣潮预约] 正在为当前绑定账号查询并领取愿望单奖励，完成后会发送结果。")
        start.set()
    finally:
        if not start.is_set():
            task.cancel()


async def stop_activity_tasks() -> None:
    tasks = [task for task in asyncio.all_tasks() if task.get_name().startswith(TASK_PREFIX)]
    for task in tasks:
        task.cancel()
    if tasks:
        _, pending = await asyncio.wait(tasks, timeout=5)
        if pending:
            raise TimeoutError(f"鸣潮活动仍有 {len(pending)} 个后台任务未停止。")
