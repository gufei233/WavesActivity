"""Shared API response types and archived fishing models, plans and reward summaries."""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field, JsonValue

RESOURCE_NAMES = {3: "星声", 2: "贝币", 43010003: "高级共鸣促剂", 43020003: "高级能源核心", 36000003: "高级共鸣回响"}


class ActivityError(RuntimeError):
    pass


class Envelope(BaseModel):
    code: int
    message: str | None = None
    msg: str | None = None
    data: JsonValue = None


class Token(BaseModel):
    token: str = Field(repr=False)


class Player(BaseModel):
    playerId: str | int


class Match(BaseModel):
    matchId: str


class Config(BaseModel):
    status: int


class Profile(BaseModel):
    isParticiple: bool


class Reward(BaseModel):
    gameResourceId: int
    count: int


class Task(BaseModel):
    id: int
    taskType: str
    status: int
    rewardResources: list[Reward]


class Level(BaseModel):
    id: int
    status: int
    isPassed: bool
    isChallenge: bool
    treasureClaimed: bool | None


class Fish(BaseModel):
    fishId: str
    status: str


class Settlement(BaseModel):
    isFirstPass: bool
    passedRewardResources: list[Reward] | None
    isFirstClaimTreasure: bool | None
    treasureRewardResources: list[Reward] | None


@dataclass(frozen=True)
class Plan:
    level_id: int
    fish: str
    elapsed: int
    treasure: bool = True


PLANS = (
    Plan(1, "AAAACA", 62),
    Plan(2, "BCCCD", 28),
    Plan(3, "EDDDC", 30),
    Plan(4, "EFFDD", 30),
    Plan(5, "GGFFFF", 45),
    Plan(6, "HHFFGGG", 45),
    Plan(7, "HFFFFGG", 45, False),
)


@dataclass
class Result:
    rewards: dict[int, int] = field(default_factory=dict)
    new_levels: list[int] = field(default_factory=list)
    new_treasures: list[int] = field(default_factory=list)
    new_tasks: list[int] = field(default_factory=list)
    levels: list[Level] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    fish: list[Fish] = field(default_factory=list)

    def add_rewards(self, rewards: list[Reward] | None) -> None:
        for reward in rewards or []:
            ident = reward.gameResourceId
            if ident not in self.rewards:
                self.rewards[ident] = 0
            self.rewards[ident] += reward.count

    def render(self, uid: str) -> str:
        ordinary = [level for level in self.levels if not level.isChallenge]
        passed = sum(level.isPassed for level in self.levels)
        treasure = sum(bool(level.treasureClaimed) for level in ordinary)
        claimed = sum(task.status == 2 for task in self.tasks)
        unlocked = sum(fish.status != "NOT_UNLOCKED" for fish in self.fish)
        complete = (
            bool(self.levels and self.tasks and self.fish)
            and passed == len(self.levels)
            and treasure == len(ordinary)
            and claimed == len(self.tasks)
            and unlocked == len(self.fish)
        )
        title = "活动已全部完成" if complete else "本次执行结束"
        lines = [
            f"[鸣潮活动] {title}",
            f"账号：{uid[:3]}***{uid[-3:]}",
            f"关卡：{passed}/{len(self.levels)}　宝箱：{treasure}/{len(ordinary)}",
            f"图鉴：{unlocked}/{len(self.fish)}　任务：{claimed}/{len(self.tasks)}",
        ]
        if self.rewards:
            lines.append(
                "本次获得："
                + "、".join(
                    f"{RESOURCE_NAMES[ident] if ident in RESOURCE_NAMES else f'资源 {ident}'}×{count}"
                    for ident, count in self.rewards.items()
                )
            )
        else:
            lines.append("本次没有新增奖励，已领取的奖励会自动跳过。")
        pending = [str(level.id) for level in self.levels if not level.isPassed]
        if pending:
            lines.append("未完成关卡：" + "、".join(pending) + "，请在解锁后再次发送活动指令。")
        pending_treasures = [str(level.id) for level in ordinary if not level.treasureClaimed]
        if pending_treasures:
            lines.append("未领取宝箱：" + "、".join(pending_treasures))
        pending_tasks = [str(task.id) for task in self.tasks if task.status != 2]
        if pending_tasks:
            lines.append("未领奖任务：" + "、".join(pending_tasks))
        return "\n".join(lines)
