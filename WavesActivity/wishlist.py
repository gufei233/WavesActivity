"""Claim the Second Coming of Solaris wishlist reward for the selected XWUID role."""

from dataclasses import dataclass
from typing import Literal, TypeVar

import aiohttp
from pydantic import AliasChoices, BaseModel, Field, StrictBool, TypeAdapter

from .bridge import Account, Network
from .community import community_request
from .models import ActivityError, Envelope, Token

T = TypeVar("T")
BASE = "https://diersuola-api.kurogames-global.com"
ORIGIN = "https://diersuola.kurogames-global.com"
ERROR_MESSAGES = {
    10002: "活动登录已失效，请重新发送预约指令。",
    10006: "当前账号没有参与权限。",
    10014: "操作频繁，请稍后再试。",
    10022: "当前角色的区服不在活动支持范围内。",
    10024: "活动登录失败，请更新 XWUID 登录。",
    10036: "库街区授权已失效，请更新 XWUID 登录。",
    20003: "未找到对应游戏角色，请核对 XWUID 当前账号。",
    20012: "预约活动已结束。",
    20020: "愿望单查询失败，请稍后再试。",
    20021: "加入愿望单失败，请稍后再试。",
}


class CommunityRole(BaseModel):
    roleId: str | int
    serverId: str = Field(min_length=1)


class WishlistLogin(BaseModel):
    # The captured frontend accepts all three server spellings.
    token: str = Field(
        validation_alias=AliasChoices("platfrom_token", "platform_token", "token"), min_length=1, repr=False
    )


class WishlistProfile(BaseModel):
    game_role_id: str | int
    server_id: str | int
    has_wishlisted: StrictBool


class WishlistConfig(BaseModel):
    activity_start_time: int
    activity_end_time: int
    now_time: int


@dataclass(frozen=True)
class WishlistResult:
    newly_joined: bool

    def render(self, uid: str) -> str:
        account = f"账号：{uid[:3]}***{uid[-3:]}"
        if not self.newly_joined:
            return f"[鸣潮预约] 当前角色已在愿望单中\n{account}\n本次没有新增奖励。"
        return f"[鸣潮预约] 已加入愿望单，领奖成功\n{account}\n活动奖励：星声×20、贝币×10000\n请到游戏邮箱查收。"


ROLES_RESPONSE = TypeAdapter(list[CommunityRole])
TOKEN_RESPONSE = TypeAdapter(Token)
LOGIN_RESPONSE = TypeAdapter(WishlistLogin)
PROFILE_RESPONSE = TypeAdapter(WishlistProfile)
CONFIG_RESPONSE = TypeAdapter(WishlistConfig)
JOIN_RESPONSE = TypeAdapter[bool](StrictBool)


class WishlistActivity:
    def __init__(self, session: aiohttp.ClientSession, network: Network) -> None:
        self.session = session
        self.network = network
        self.token = ""

    async def request(
        self,
        path: str,
        result_type: TypeAdapter[T],
        method: Literal["GET", "POST"] = "GET",
        body: dict[str, str] | None = None,
    ) -> T:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) KuroGameBox/3.4.0",
        }
        if self.token:
            headers["Authorization"] = self.token
        async with self.session.request(
            method, BASE + path, headers=headers, json=body, proxy=self.network.proxy
        ) as response:
            if response.status != 200:
                raise ActivityError(f"预约 {path} 返回 HTTP {response.status}，本次已停止。")
            envelope = Envelope.model_validate(await response.json(content_type=None))
        if envelope.code != 0:
            message = ERROR_MESSAGES[envelope.code] if envelope.code in ERROR_MESSAGES else "预约接口拒绝了请求。"
            raise ActivityError(f"{message}（{path}，{envelope.code}）")
        return result_type.validate_python(envelope.data)

    async def login(self, account: Account) -> CommunityRole:
        roles = await community_request(
            self.session, self.network, account, "/gamer/role/list", {"gameId": "3"}, ROLES_RESPONSE
        )
        role = next((item for item in roles if str(item.roleId) == account.uid), None)
        if role is None:
            raise ActivityError("当前 XWUID 账号不在库街区角色列表中，请更新登录或切换鸣潮账号。")
        credential = await community_request(
            self.session,
            self.network,
            account,
            "/user/auth/gettoken",
            {"appId": "G152", "pkgId": "A1476"},
            TOKEN_RESPONSE,
        )
        login = await self.request(
            "/api/kuro-street-login",
            LOGIN_RESPONSE,
            "POST",
            {"api_token": credential.token, "server": role.serverId, "role_id": account.uid},
        )
        self.token = login.token if login.token.lower().startswith("bearer ") else "Bearer " + login.token
        return role

    async def profile(self, role: CommunityRole) -> WishlistProfile:
        profile = await self.request("/api/user/info", PROFILE_RESPONSE)
        if str(profile.game_role_id) != str(role.roleId) or str(profile.server_id) != role.serverId:
            raise ActivityError("活动登录角色与 XWUID 当前账号不一致，本次已停止。")
        return profile

    async def run(self, account: Account) -> WishlistResult:
        role = await self.login(account)
        profile = await self.profile(role)
        if profile.has_wishlisted:
            return WishlistResult(newly_joined=False)
        config = await self.request("/api/common/config", CONFIG_RESPONSE)
        if config.now_time < config.activity_start_time:
            raise ActivityError("预约活动尚未开始。")
        if config.now_time >= config.activity_end_time:
            raise ActivityError("预约活动已结束。")
        # POST has no body, matching the captured request; do not retry reward writes.
        joined = await self.request("/api/wishlist/join", JOIN_RESPONSE, "POST")
        if not joined:
            raise ActivityError("服务端未确认加入愿望单，请稍后查询。")
        profile = await self.profile(role)
        if not profile.has_wishlisted:
            raise ActivityError("已提交愿望单，但状态尚未确认，请稍后重新发送预约指令查询。")
        return WishlistResult(newly_joined=True)
