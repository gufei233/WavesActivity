"""Read the current XWUID binding and reuse its network configuration."""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from gsuid_core.utils.database.base_models import with_read_session
from plugins.XutheringWavesUID.XutheringWavesUID.utils.database.models import WavesBind, WavesUser
from plugins.XutheringWavesUID.XutheringWavesUID.wutheringwaves_config import WutheringWavesConfig


@dataclass(frozen=True)
class Account:
    uid: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class Network:
    community_base: str
    proxy: str | None = field(repr=False)


class AccountReader:
    @classmethod
    @with_read_session
    async def read(cls, session: AsyncSession, user_id: str, bot_id: str) -> Account | None:
        binding = (
            await session.scalars(
                select(WavesBind).where(col(WavesBind.user_id) == user_id, col(WavesBind.bot_id) == bot_id).limit(1)
            )
        ).first()
        if binding is None or not binding.uid:
            return None
        # XWUID stores selected UID first, followed by other bindings separated by underscores.
        uid = binding.uid.split("_", 1)[0]
        row = (
            await session.scalars(
                select(WavesUser)
                .where(
                    col(WavesUser.uid) == uid,
                    col(WavesUser.user_id) == user_id,
                    col(WavesUser.bot_id) == bot_id,
                    col(WavesUser.game_id) == 3,
                )
                .limit(1)
            )
        ).first()
        if row is None or not row.cookie:
            return None
        return Account(uid=uid, token=row.cookie)


async def get_account(user_id: str, bot_id: str) -> Account | None:
    return await AccountReader.read(user_id, bot_id)


def get_network() -> Network:
    base: str = WutheringWavesConfig.get_config("KuroUrlProxyUrl").data
    proxy: str = WutheringWavesConfig.get_config("LocalProxyUrl").data
    functions: list[str] = WutheringWavesConfig.get_config("NeedProxyFunc").data
    enabled = "all" in functions or "run_activity" in functions
    return Network(
        community_base=(base or "https://api.kurobbs.com").rstrip("/"), proxy=proxy if enabled and proxy else None
    )
