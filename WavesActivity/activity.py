"""Archived fishing activity, expired on 2026-11-01; no longer used by command handlers."""

import asyncio
import secrets
import time
from typing import TypeVar

import aiohttp
from pydantic import JsonValue, TypeAdapter

from .bridge import Account, Network
from .models import (
    PLANS,
    ActivityError,
    Config,
    Envelope,
    Fish,
    Level,
    Match,
    Player,
    Profile,
    Result,
    Settlement,
    Task,
    Token,
)

T = TypeVar("T")
BASE = "https://event-api.aki-game.com"


TOKEN_RESPONSE = TypeAdapter(Token)
PLAYERS_RESPONSE = TypeAdapter(list[Player])
JSON_RESPONSE = TypeAdapter[JsonValue](JsonValue)
EMPTY_RESPONSE = TypeAdapter[None](type(None))
CONFIG_RESPONSE = TypeAdapter(Config)
PROFILE_RESPONSE = TypeAdapter(Profile)
TASKS_RESPONSE = TypeAdapter(list[Task])
LEVELS_RESPONSE = TypeAdapter(list[Level])
MATCH_RESPONSE = TypeAdapter(Match)
SETTLEMENT_RESPONSE = TypeAdapter(Settlement)
FISH_RESPONSE = TypeAdapter(list[Fish])


class FishingActivity:
    def __init__(self, session: aiohttp.ClientSession, network: Network) -> None:
        self.session = session
        self.network = network
        self.token = ""
        self.result = Result()
        self.headers = {
            "x-event-type": "fishing",
            "x-language": "zh-Hans",
            "x-client-platform": "iOS",
            "x-s-from": "kurobbs",
            "x-s-source": "",
            "x-fe-trace-id": secrets.token_hex(16),
            "Origin": "https://mc-act.kurogames-global.com",
            "Referer": "https://mc-act.kurogames-global.com/",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) KuroGameBox/3.4.0",
        }

    async def request(
        self,
        path: str,
        result_type: TypeAdapter[T],
        body: dict[str, object] | None = None,
    ) -> T:
        headers = dict(self.headers)
        if self.token:
            headers["x-token"] = self.token
        method = "POST" if body is not None else "GET"
        params = {"_t": str(time.time_ns() // 1_000_000)} if body is None else None
        async with self.session.request(
            method, BASE + path, headers=headers, params=params, json=body, proxy=self.network.proxy
        ) as response:
            if response.status != 200:
                raise ActivityError(f"{path} 返回 HTTP {response.status}，本次已停止。")
            envelope = Envelope.model_validate(await response.json(content_type=None))
        if envelope.code != 200:
            raise ActivityError(f"{path}：{envelope.message or envelope.msg or '请求失败'}（{envelope.code}）")
        return result_type.validate_python(envelope.data)

    async def login(self, account: Account) -> None:
        headers = {
            "token": account.token,
            "channelId": "1",
            "version": "3.4.0",
            "channel": "appstore",
            "source": "ios",
            "lang": "zh-Hans",
            "model": "iPhone18,1",
            "osVersion": "27.0.1",
            "User-Agent": "KuroGameBox/20260922172728 CFNetwork/3896.100.1.2.1 Darwin/27.0.0",
        }
        async with self.session.post(
            self.network.community_base + "/user/auth/gettoken",
            headers=headers,
            data={"appId": "G152", "pkgId": "A1496"},
            proxy=self.network.proxy,
        ) as response:
            if response.status != 200:
                raise ActivityError(f"授权交换返回 HTTP {response.status}，请稍后重试。")
            envelope = Envelope.model_validate(await response.json(content_type=None))
        if envelope.code != 200:
            raise ActivityError(
                f"授权交换失败：{envelope.message or envelope.msg}（{envelope.code}），请更新 XWUID 登录。"
            )
        bbs = Token.model_validate(envelope.data)
        token = await self.request("/user/login/bbs", TOKEN_RESPONSE, {"BBSToken": bbs.token})
        self.token = token.token
        players = await self.request("/user/bbs-player/list", PLAYERS_RESPONSE)
        player = next((item for item in players if str(item.playerId) == account.uid), None)
        if player is None:
            raise ActivityError("当前 XWUID 账号不在此 token 的活动角色列表中，请重新登录或切换鸣潮账号。")
        await self.request("/user/bbs-player/choose", JSON_RESPONSE, {"playerId": player.playerId})

    async def claim_ready(self, tasks: list[Task]) -> list[Task]:
        while ready := next((task for task in tasks if task.status == 1), None):
            await self.request("/fishing/task/claim", EMPTY_RESPONSE, {"id": ready.id})
            tasks = await self.request("/fishing/task/list", TASKS_RESPONSE)
            updated = next((task for task in tasks if task.id == ready.id), None)
            if updated is None or updated.status != 2:
                raise ActivityError(f"任务 {ready.id} 领取后状态未更新，请稍后查询。")
            self.result.new_tasks.append(ready.id)
            self.result.add_rewards(ready.rewardResources)
        return tasks

    async def run(self, account: Account) -> Result:
        await self.login(account)
        config = await self.request("/fishing/config", CONFIG_RESPONSE)
        if config.status != 1:
            raise ActivityError("本期钓鱼活动尚未开始或已经结束。")
        profile = await self.request("/fishing/profile", PROFILE_RESPONSE)
        if not profile.isParticiple:
            raise ActivityError("当前角色尚未参与活动，请先在活动网页完成首次参与。")
        tasks = await self.request("/fishing/task/list", TASKS_RESPONSE)
        pending_tasks = [task for task in tasks if task.status == 0 and task.taskType in ("share", "jump_out_link")]
        for task in pending_tasks:
            await self.request("/fishing/task/submit", EMPTY_RESPONSE, {"id": task.id})
        if pending_tasks:
            tasks = await self.request("/fishing/task/list", TASKS_RESPONSE)
        tasks = await self.claim_ready(tasks)
        levels = await self.request("/fishing/level/list", LEVELS_RESPONSE)
        for plan in PLANS:
            level = next((item for item in levels if item.id == plan.level_id), None)
            if level is None:
                raise ActivityError(f"活动未返回第 {plan.level_id} 关，请联系管理员核对本期活动配置。")
            treasure = plan.treasure and not level.treasureClaimed
            if level.isPassed and not treasure:
                continue
            if level.status != 2:
                continue
            match = await self.request("/fishing/game/start", MATCH_RESPONSE, {"levelId": plan.level_id})
            await asyncio.sleep(plan.elapsed + 4)
            settlement = await self.request(
                "/fishing/game/pass",
                SETTLEMENT_RESPONSE,
                {
                    "matchId": match.matchId,
                    "levelId": plan.level_id,
                    "isClaimTreasure": bool(treasure),
                    "caughtFishTypes": list(plan.fish),
                    "elapsedSec": plan.elapsed,
                },
            )
            levels = await self.request("/fishing/level/list", LEVELS_RESPONSE)
            updated = next((item for item in levels if item.id == plan.level_id), None)
            if updated is None or not updated.isPassed or (treasure and not updated.treasureClaimed):
                raise ActivityError(f"第 {plan.level_id} 关结算后状态未更新，本次已停止。")
            if settlement.isFirstPass:
                self.result.new_levels.append(plan.level_id)
                self.result.add_rewards(settlement.passedRewardResources)
            if settlement.isFirstClaimTreasure:
                self.result.new_treasures.append(plan.level_id)
                self.result.add_rewards(settlement.treasureRewardResources)
            tasks = await self.claim_ready(await self.request("/fishing/task/list", TASKS_RESPONSE))
        self.result.levels = levels
        self.result.tasks = tasks
        self.result.fish = await self.request("/fishing/fish-list", FISH_RESPONSE)
        return self.result
