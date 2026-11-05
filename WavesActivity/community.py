"""Read community roles and exchange activity credentials with the user's token."""

from typing import TypeVar

import aiohttp
from pydantic import TypeAdapter

from .bridge import Account, Network
from .models import ActivityError, Envelope

T = TypeVar("T")


async def community_request(
    session: aiohttp.ClientSession,
    network: Network,
    account: Account,
    path: str,
    body: dict[str, str],
    result_type: TypeAdapter[T],
) -> T:
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
    if account.did:
        headers["devCode"] = account.did
    async with session.post(network.community_base + path, headers=headers, data=body, proxy=network.proxy) as response:
        if response.status != 200:
            raise ActivityError(f"库街区 {path} 返回 HTTP {response.status}，本次已停止。")
        envelope = Envelope.model_validate(await response.json(content_type=None))
    if envelope.code != 200:
        raise ActivityError(f"库街区 {path} 请求失败（{envelope.code}），请检查 XWUID 登录状态。")
    return result_type.validate_python(envelope.data)
