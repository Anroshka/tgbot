"""SQLite: устройства пользователей, заявки на доступ."""

import aiosqlite
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "bot.db"


@dataclass(frozen=True)
class UserDeviceRecord:
    telegram_id: int
    device_kind: str
    slot_index: int
    base_email: str
    uuid: str
    sub_token: str
    created_at: str | None
    expires_at: str | None


@dataclass(frozen=True)
class SubscriptionReminderRecord:
    telegram_id: int
    device_kind: str
    slot_index: int
    sub_token: str
    expires_at: str
    days_before: int


@dataclass(frozen=True)
class AccessRequestRecord:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    base_email: str
    device_kind: str
    slot_index: int


def _parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    text = text.replace("T", " ")
    if "." in text:
        text = text.split(".", 1)[0]
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return dt.replace(tzinfo=timezone.utc)


async def _migrate_schema(
    conn: aiosqlite.Connection, default_subscription_days: int
) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            device_kind TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            base_email TEXT NOT NULL,
            uuid TEXT NOT NULL,
            sub_token TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE (telegram_id, device_kind, slot_index)
        )
        """
    )
    cur = await conn.execute("PRAGMA table_info(user_devices)")
    ud_cols = {r[1] for r in await cur.fetchall()}
    if "expires_at" not in ud_cols:
        await conn.execute(
            "ALTER TABLE user_devices ADD COLUMN expires_at TEXT"
        )
    await conn.execute(
        """
        UPDATE user_devices
        SET expires_at = datetime(
            COALESCE(created_at, datetime('now')),
            '+' || ? || ' days'
        )
        WHERE expires_at IS NULL
        """,
        (int(default_subscription_days),),
    )
    cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if await cur.fetchone():
        await conn.execute(
            """
            INSERT OR IGNORE INTO user_devices
            (telegram_id, device_kind, slot_index, base_email, uuid, sub_token)
            SELECT telegram_id, 'other', 1,
                   'legacy_' || CAST(telegram_id AS TEXT), uuid, sub_token
            FROM users
            """
        )

    cur = await conn.execute("PRAGMA table_info(access_requests)")
    cols = {r[1] for r in await cur.fetchall()}
    if "device_kind" not in cols:
        await conn.execute(
            "ALTER TABLE access_requests ADD COLUMN device_kind TEXT NOT NULL DEFAULT 'other'"
        )
    if "slot_index" not in cols:
        await conn.execute(
            "ALTER TABLE access_requests ADD COLUMN slot_index INTEGER NOT NULL DEFAULT 1"
        )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS terms_acceptance (
            telegram_id INTEGER PRIMARY KEY,
            accepted_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_notifications (
            telegram_id INTEGER NOT NULL,
            device_kind TEXT NOT NULL,
            slot_index INTEGER NOT NULL,
            days_before INTEGER NOT NULL,
            sent_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (telegram_id, device_kind, slot_index, days_before)
        )
        """
    )
    cur = await conn.execute("PRAGMA table_info(terms_acceptance)")
    ta_cols = {r[1] for r in await cur.fetchall()}
    if ta_cols and "agreement_accepted_at" not in ta_cols:
        await conn.execute(
            "ALTER TABLE terms_acceptance ADD COLUMN agreement_accepted_at TEXT"
        )
        await conn.execute(
            """
            UPDATE terms_acceptance
            SET agreement_accepted_at = accepted_at
            WHERE agreement_accepted_at IS NULL AND accepted_at IS NOT NULL
            """
        )
    await conn.execute(
        """
        INSERT OR IGNORE INTO terms_acceptance (telegram_id, accepted_at)
        SELECT DISTINCT telegram_id, datetime('now') FROM user_devices
        """
    )
    await conn.execute(
        """
        UPDATE terms_acceptance
        SET agreement_accepted_at = accepted_at
        WHERE agreement_accepted_at IS NULL AND accepted_at IS NOT NULL
        """
    )


async def init_db(default_subscription_days: int = 30) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                uuid TEXT NOT NULL,
                sub_token TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS access_requests (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                base_email TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await _migrate_schema(db, default_subscription_days)
        await db.commit()
    logger.info("База данных готова: %s", DB_PATH)


async def count_device_slots(telegram_id: int, device_kind: str) -> int:
    """Сколько уже выданных конфигов этого типа устройства (для слота и суффикса email)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM user_devices WHERE telegram_id = ? AND device_kind = ?",
            (telegram_id, device_kind),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def create_user_device(
    telegram_id: int,
    device_kind: str,
    slot_index: int,
    base_email: str,
    uuid_val: str,
    sub_token: str,
    expires_at: str,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_devices
            (telegram_id, device_kind, slot_index, base_email, uuid, sub_token, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_id,
                device_kind,
                slot_index,
                base_email,
                uuid_val,
                sub_token,
                expires_at,
            ),
        )
        await db.commit()


async def list_user_devices(telegram_id: int) -> list[UserDeviceRecord]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT telegram_id, device_kind, slot_index, base_email, uuid, sub_token,
                   created_at, expires_at
            FROM user_devices WHERE telegram_id = ?
            ORDER BY id ASC
            """,
            (telegram_id,),
        )
        rows = await cur.fetchall()
    return [
        UserDeviceRecord(
            telegram_id=r["telegram_id"],
            device_kind=r["device_kind"],
            slot_index=r["slot_index"],
            base_email=r["base_email"],
            uuid=r["uuid"],
            sub_token=r["sub_token"],
            created_at=r["created_at"],
            expires_at=r["expires_at"],
        )
        for r in rows
    ]


async def list_due_subscription_reminders(
    days_before: list[int],
    now_utc: datetime,
    limit: int = 100,
) -> list[SubscriptionReminderRecord]:
    normalized_days = sorted(
        {int(x) for x in days_before if int(x) >= 0}, reverse=True
    )
    if not normalized_days or limit <= 0:
        return []
    now = now_utc.astimezone(timezone.utc)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT telegram_id, device_kind, slot_index, sub_token, expires_at
            FROM user_devices
            WHERE expires_at IS NOT NULL
            ORDER BY expires_at ASC, id ASC
            """
        )
        devices = await cur.fetchall()
        cur = await db.execute(
            """
            SELECT telegram_id, device_kind, slot_index, days_before
            FROM subscription_notifications
            """
        )
        sent_rows = await cur.fetchall()
    sent_keys = {
        (
            int(r["telegram_id"]),
            str(r["device_kind"]),
            int(r["slot_index"]),
            int(r["days_before"]),
        )
        for r in sent_rows
    }
    due: list[SubscriptionReminderRecord] = []
    for row in devices:
        expires = _parse_utc_datetime(row["expires_at"])
        if expires is None:
            continue
        key_base = (
            int(row["telegram_id"]),
            str(row["device_kind"]),
            int(row["slot_index"]),
        )
        for d in normalized_days:
            key = (*key_base, d)
            if key in sent_keys:
                continue
            if now >= expires - timedelta(days=d):
                due.append(
                    SubscriptionReminderRecord(
                        telegram_id=key_base[0],
                        device_kind=key_base[1],
                        slot_index=key_base[2],
                        sub_token=str(row["sub_token"]),
                        expires_at=str(row["expires_at"]),
                        days_before=d,
                    )
                )
                if len(due) >= limit:
                    return due
    return due


async def mark_subscription_reminder_sent(
    telegram_id: int,
    device_kind: str,
    slot_index: int,
    days_before: int,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO subscription_notifications
            (telegram_id, device_kind, slot_index, days_before)
            VALUES (?, ?, ?, ?)
            """,
            (telegram_id, device_kind, slot_index, days_before),
        )
        await db.commit()


async def count_distinct_subscribers() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(DISTINCT telegram_id) FROM user_devices"
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_devices() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM user_devices")
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_pending_requests() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM access_requests")
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def get_access_request(telegram_id: int) -> AccessRequestRecord | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT telegram_id, username, first_name, last_name, base_email,
                   device_kind, slot_index
            FROM access_requests WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return AccessRequestRecord(
        telegram_id=row["telegram_id"],
        username=row["username"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        base_email=row["base_email"],
        device_kind=row["device_kind"] or "other",
        slot_index=int(row["slot_index"] or 1),
    )


async def try_insert_access_request(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
    base_email: str,
    device_kind: str,
    slot_index: int,
) -> bool:
    """True — новая заявка. False — уже есть активная заявка от этого пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM access_requests WHERE telegram_id = ?",
            (telegram_id,),
        )
        if await cur.fetchone():
            return False
        await db.execute(
            """
            INSERT INTO access_requests
            (telegram_id, username, first_name, last_name, base_email, device_kind, slot_index)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_id,
                username,
                first_name,
                last_name,
                base_email,
                device_kind,
                slot_index,
            ),
        )
        await db.commit()
    return True


async def delete_access_request(telegram_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM access_requests WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()


async def has_accepted_usage_rules(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT 1 FROM terms_acceptance
            WHERE telegram_id = ? AND accepted_at IS NOT NULL
            """,
            (telegram_id,),
        )
        return await cur.fetchone() is not None


async def has_accepted_user_agreement(telegram_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT 1 FROM terms_acceptance
            WHERE telegram_id = ? AND agreement_accepted_at IS NOT NULL
            """,
            (telegram_id,),
        )
        return await cur.fetchone() is not None


async def set_rules_accepted(telegram_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO terms_acceptance
                (telegram_id, accepted_at, agreement_accepted_at)
            VALUES (?, datetime('now'), NULL)
            ON CONFLICT(telegram_id) DO UPDATE SET
                accepted_at = excluded.accepted_at
            """,
            (telegram_id,),
        )
        await db.commit()


async def set_agreement_accepted(telegram_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE terms_acceptance
            SET agreement_accepted_at = datetime('now')
            WHERE telegram_id = ?
            """,
            (telegram_id,),
        )
        await db.commit()
