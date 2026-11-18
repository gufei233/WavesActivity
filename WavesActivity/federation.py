"""Register the selected XWUID role for the New Federation event."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import aiohttp
from pydantic import BaseModel, Field, JsonValue, TypeAdapter

from .bridge import Account, Network
from .community import community_request
from .models import ActivityError, Envelope, Token

BASE = "https://newfederation-api.kurogames-global.com"
ORIGIN = "https://newfederation.kurogames-global.com"
ACTIVITY_REGION = "1"
RESERVATION_TASK = "activity_apply"
SHARE_TASK = "share_first"
RESERVED_STATUSES = (1, 2)
ERROR_MESSAGES = {
    1: "活动接口繁忙，请稍后再试。",
    1001: "库街区授权失败，请更新 XWUID 登录。",
    5001: "活动登录已失效，请重新发送预约指令。",
    5002: "未找到游戏角色。",
    5003: "当前角色不在活动支持范围内。",
    5005: "活动任务尚未完成。",
    5006: "该奖励已领取。",
    5007: "该奖励已领取。",
    5010: "预约活动已结束。",
    5011: "预约活动尚未开始。",
    5012: "预约活动暂时关闭。",
    5013: "预约活动正在维护。",
}


class CommunityRole(BaseModel):
    roleId: str | int
    serverId: str = Field(min_length=1)


class ActivityInfo(BaseModel):
    start_time: datetime
    end_time: datetime
    current_time: datetime
    status: int


class ActivityLogin(BaseModel):
    token: str = Field(validation_alias="platfrom_token", min_length=1, repr=False)


class ActivityUser(BaseModel):
    role_id: str | int


class ActivityTask(BaseModel):
    task_ident: str
    status: int


ROLES_RESPONSE = TypeAdapter(list[CommunityRole])
TOKEN_RESPONSE = TypeAdapter(Token)
TASKS_RESPONSE = TypeAdapter(list[ActivityTask])


@dataclass(frozen=True)
class ReservationResult:
    newly_reserved: bool
    newly_shared: bool | None

    def render(self, uid: str) -> str:
        title = "预约成功" if self.newly_reserved else "当前角色已预约"
        lines = [f"[鸣潮预约] {title}", f"账号：{uid[:3]}***{uid[-3:]}"]
        if self.newly_shared is not None:
            lines.append("分享任务：本次已完成" if self.newly_shared else "分享任务：已处理")
        lines.append("新版本开服后登录游戏可领取预约奖励：星声×100。")
        return "\n".join(lines)


class FederationActivity:
    def __init__(self, session: aiohttp.ClientSession, network: Network) -> None:
        self.session = session
        self.network = network
        self.token = ""
        self.client_id = ""

    async def request(self, path: str, body: dict[str, str]) -> JsonValue:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": ORIGIN,
            "Referer": ORIGIN + "/",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) KuroGameBox/3.5.0",
            "X-BLM-CID": self.client_id,
            "X-BLM-FRID": uuid4().hex,
        }
        if self.token:
            headers["Authorization"] = self.token
        async with self.session.post(BASE + path, headers=headers, json=body) as response:
            if response.status != 200:
                raise ActivityError(f"预约 {path} 返回 HTTP {response.status}，本次已停止。")
            if not self.client_id:
                self.client_id = response.headers.get("X-Request-Id", "")
            envelope = Envelope.model_validate(await response.json(content_type=None))
        if envelope.code != 0:
            message = ERROR_MESSAGES.get(envelope.code, "预约接口拒绝了请求。")
            raise ActivityError(f"{message}（{path}，{envelope.code}）")
        return envelope.data

    async def check_activity(self) -> None:
        info = ActivityInfo.model_validate(
            await self.request("/api/common/activityInfo", {"server_id": ACTIVITY_REGION})
        )
        if info.status == 2 or info.current_time >= info.end_time:
            raise ActivityError("预约活动已结束。")
        if info.current_time < info.start_time:
            raise ActivityError("预约活动尚未开始。")

    async def login(self, account: Account) -> None:
        roles = await community_request(
            self.session, self.network, account, "/user/role/findRoleList", {"gameId": "3"}, ROLES_RESPONSE
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
        login = ActivityLogin.model_validate(
            await self.request(
                "/api/auth/kuroStreetLogin",
                {"api_token": credential.token, "server": role.serverId, "role_id": account.uid},
            )
        )
        self.token = login.token
        user = ActivityUser.model_validate(await self.request("/api/user/userInfo", {}))
        if str(user.role_id) != account.uid:
            raise ActivityError("活动登录角色与 XWUID 当前账号不一致，本次已停止。")

    async def tasks(self) -> dict[str, int]:
        tasks = TASKS_RESPONSE.validate_python(await self.request("/api/task/taskList", {}))
        return {task.task_ident: task.status for task in tasks}

    async def run(self, account: Account) -> ReservationResult:
        await self.check_activity()
        await self.login(account)
        tasks = await self.tasks()
        reservation_status = tasks.get(RESERVATION_TASK)
        newly_reserved = reservation_status == 0
        if newly_reserved:
            await self.request("/api/task/taskSubmit", {"task_ident": RESERVATION_TASK})
            tasks = await self.tasks()
            if tasks.get(RESERVATION_TASK) not in RESERVED_STATUSES:
                raise ActivityError("预约已提交，活动页面暂未确认状态，请稍后重新发送指令查询。")
        elif reservation_status not in RESERVED_STATUSES:
            raise ActivityError("当前角色的预约任务不可用。")

        share_status = tasks.get(SHARE_TASK)
        if share_status is None:
            return ReservationResult(newly_reserved, newly_shared=None)
        newly_shared = share_status == 0
        if newly_shared:
            await self.request("/api/task/shareActivitySubmit", {})
            if (await self.tasks()).get(SHARE_TASK) != 2:
                raise ActivityError("预约已确认，分享任务状态待确认，请稍后重新发送指令查询。")
        return ReservationResult(newly_reserved, newly_shared)
