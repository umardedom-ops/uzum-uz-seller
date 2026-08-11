"""Hodimlar va guruh/kanal — kirish nazorati bilan.

Eng muhimi: hodim boshqa do'konni ko'rmasligi va begona odam hodim
qo'sha olmasligi. Bu yerdagi xato — mijozning ma'lumoti begonaga
ko'rinishi demak.
"""
from __future__ import annotations

from app.db.base import session_scope
from app.db.models import Shop, StaffRole, User
from app.services import team
from app.services.exports import find_user_shop, list_user_shops, set_active_shop

OWNER, OTHER, STAFF = 5001, 5002, 5003


async def _seed() -> tuple[int, int]:
    """Ikki egaga bitta-bittadan do'kon. `(egasi_shop, boshqa_shop)`."""
    async with session_scope() as s:
        owner = User(telegram_id=OWNER)
        other = User(telegram_id=OTHER)
        s.add_all([owner, other])
        await s.flush()

        a = Shop(user_id=owner.id, uzum_shop_id="100", title="MENIKI", is_active=True)
        b = Shop(user_id=other.id, uzum_shop_id="200", title="BEGONA", is_active=True)
        s.add_all([a, b])
        await s.flush()
        return a.id, b.id


class TestStaffAccess:
    async def test_staff_sees_assigned_shop(self) -> None:
        mine, _ = await _seed()
        await team.add_staff(OWNER, mine, STAFF)

        shops = await list_user_shops(STAFF)
        assert [s.id for s in shops] == [mine]
        assert (await find_user_shop(STAFF)).id == mine

    async def test_staff_does_not_see_other_shops(self) -> None:
        mine, foreign = await _seed()
        await team.add_staff(OWNER, mine, STAFF)

        shops = await list_user_shops(STAFF)
        assert foreign not in [s.id for s in shops]

    async def test_staff_cannot_switch_to_foreign_shop(self) -> None:
        mine, foreign = await _seed()
        await team.add_staff(OWNER, mine, STAFF)

        assert await set_active_shop(STAFF, foreign) is None

    async def test_without_staff_sees_nothing(self) -> None:
        await _seed()
        assert await list_user_shops(STAFF) == []
        assert await find_user_shop(STAFF) is None


class TestOwnership:
    async def test_stranger_cannot_add_staff(self) -> None:
        mine, _ = await _seed()
        # OTHER — boshqa odam, MENIKI do'koniga hodim qo'sha olmasligi kerak
        assert await team.add_staff(OTHER, mine, STAFF) is None
        assert await team.list_staff(mine) == []

    async def test_owner_cannot_add_self(self) -> None:
        mine, _ = await _seed()
        assert await team.add_staff(OWNER, mine, OWNER) is None

    async def test_stranger_cannot_remove(self) -> None:
        mine, _ = await _seed()
        await team.add_staff(OWNER, mine, STAFF)
        assert await team.remove_staff(OTHER, mine, STAFF) is False
        assert len(await team.list_staff(mine)) == 1


class TestStaffLifecycle:
    async def test_add_list_remove(self) -> None:
        mine, _ = await _seed()
        await team.add_staff(OWNER, mine, STAFF, title="Ali")

        members = await team.list_staff(mine)
        assert len(members) == 1 and members[0].telegram_id == STAFF
        assert members[0].role is StaffRole.VIEWER

        assert await team.remove_staff(OWNER, mine, STAFF) is True
        assert await team.list_staff(mine) == []

    async def test_re_add_updates_role(self) -> None:
        """Qayta qo'shish dublikat yaratmaydi — huquqni yangilaydi."""
        mine, _ = await _seed()
        await team.add_staff(OWNER, mine, STAFF, role=StaffRole.VIEWER)
        await team.add_staff(OWNER, mine, STAFF, role=StaffRole.MANAGER)

        members = await team.list_staff(mine)
        assert len(members) == 1
        assert members[0].role is StaffRole.MANAGER


class TestChannels:
    async def test_link_and_list(self) -> None:
        mine, _ = await _seed()
        ch = await team.link_channel(OWNER, mine, -1001234, title="Ombor")
        assert ch is not None

        channels = await team.list_channels(mine)
        assert [c.chat_id for c in channels] == [-1001234]

    async def test_stranger_cannot_link(self) -> None:
        mine, _ = await _seed()
        assert await team.link_channel(OTHER, mine, -1009999) is None

    async def test_unlink(self) -> None:
        mine, _ = await _seed()
        await team.link_channel(OWNER, mine, -1001234)
        assert await team.unlink_channel(OWNER, mine, -1001234) is True
        assert await team.list_channels(mine) == []

    async def test_channels_for_daily_report(self) -> None:
        mine, _ = await _seed()
        await team.link_channel(OWNER, mine, -1001)
        await team.link_channel(OWNER, mine, -1002)

        mapping = await team.channels_for_shops([mine])
        assert sorted(mapping[mine]) == [-1002, -1001]

    async def test_duplicate_link_is_idempotent(self) -> None:
        mine, _ = await _seed()
        await team.link_channel(OWNER, mine, -1005)
        await team.link_channel(OWNER, mine, -1005)
        assert len(await team.list_channels(mine)) == 1
