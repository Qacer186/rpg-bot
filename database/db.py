import aiosqlite
import aiohttp
import random
import time

DB_NAME = "rpg.db"
API_MONSTERS_URL = "https://www.dnd5eapi.co/api/monsters"
DUNGEON_COOLDOWN_SECONDS = 30 * 60
STAMINA_REGEN_SECONDS = 60
HP_REGEN_SECONDS = 120
EXP_PER_LEVEL = 250


def level_from_exp(exp: int) -> int:
    exp = max(0, int(exp or 0))
    return 1 + exp // EXP_PER_LEVEL


def exp_needed_for_next_level(level: int) -> int:
    level = max(1, int(level or 1))
    return level * EXP_PER_LEVEL


def exp_progress_for_level(exp: int, level: int | None = None):
    exp = max(0, int(exp or 0))
    level = level_from_exp(exp) if level is None else max(1, int(level or 1))
    current_level_start = (level - 1) * EXP_PER_LEVEL
    next_level_exp = exp_needed_for_next_level(level)
    current_progress = max(0, min(EXP_PER_LEVEL, exp - current_level_start))
    missing = max(0, next_level_exp - exp)
    return current_progress, EXP_PER_LEVEL, missing, next_level_exp


def exp_info_line(user) -> str:
    level = max(1, int(user["level"] or 1))
    progress, needed, missing, _ = exp_progress_for_level(user["exp"], level)
    return f"Do lvl `{level + 1}`: `{missing} EXP` (`{progress}/{needed}`)"


def _tier_name(level: int) -> str:
    if level <= 5:
        return "Rekruta"
    if level <= 10:
        return "Strażnika"
    if level <= 15:
        return "Najemnika"
    if level <= 20:
        return "Rycerza"
    if level <= 25:
        return "Runiczny"
    if level <= 30:
        return "Smoczy"
    if level <= 35:
        return "Cienia"
    if level <= 40:
        return "Królewski"
    if level <= 45:
        return "Pradawny"
    return "Legendarny"


def _build_equipment_items():
    items = []

    for level in range(1, 51):
        tier = _tier_name(level)
        base_price = 35 + level * 42
        atk = 2 + level * 3
        defense = 2 + level * 3

        items.extend([
            (f"Krótki Miecz {tier} Lvl {level}", base_price, atk, 0, level),
            (f"Topór {tier} Lvl {level}", base_price + 25, atk + 2, 0, level),
            (f"Włócznia {tier} Lvl {level}", base_price + 45, atk + 3, 1, level),
            (f"Skórzany Pancerz {tier} Lvl {level}", base_price, 0, defense, level),
            (f"Tarcza {tier} Lvl {level}", base_price + 20, 0, defense + 2, level),
            (f"Hełm {tier} Lvl {level}", base_price + 15, 1, max(1, defense - 1), level),
            (f"Pierścień Mocy {tier} Lvl {level}", base_price + 60, max(1, atk // 2), max(1, defense // 2), level),
            (f"Amulet Wypraw {tier} Lvl {level}", base_price + 80, max(1, atk // 2 + 1), max(1, defense // 2 + 1), level),
        ])

    return items


EQUIPMENT_ITEMS = _build_equipment_items()

POTION_ITEMS = [
    ("Mała Mikstura HP", 40, "heal", 50, 1),
    ("Mikstura HP", 90, "full_heal", 0, 1),
    ("Mikstura Staminy", 120, "stamina", 40, 1),
    ("Eliksir Siły", 260, "attack", 1, 2),
    ("Eliksir Obrony", 260, "defense", 1, 2),
    ("Eliksir Żywotności", 320, "max_hp", 10, 3),
]

DUNGEON_MONSTERS = [
    {
        "name": "Szczur z Piwnicy",
        "level": 1,
        "hp": 45,
        "attack": 8,
        "defense": 2,
        "gold": 35,
        "exp": 60,
    },
    {
        "name": "Kościany Strażnik",
        "level": 2,
        "hp": 80,
        "attack": 12,
        "defense": 5,
        "gold": 70,
        "exp": 110,
    },
    {
        "name": "Ork z Bramy Lochu",
        "level": 4,
        "hp": 130,
        "attack": 18,
        "defense": 8,
        "gold": 120,
        "exp": 190,
    },
    {
        "name": "Czarny Rycerz",
        "level": 6,
        "hp": 190,
        "attack": 26,
        "defense": 12,
        "gold": 220,
        "exp": 340,
    },
    {
        "name": "Smok Pod Ruinami",
        "level": 8,
        "hp": 280,
        "attack": 36,
        "defense": 16,
        "gold": 420,
        "exp": 650,
        "final": True,
    },
]


async def _add_column(db, table: str, column: str, definition: str):
    try:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except Exception:
        pass


async def _seed_item(db, name: str, price: int, atk_bonus: int, def_bonus: int, category: str, level_required: int = 1, effect_type: str | None = None, effect_value: int = 0):
    cursor = await db.execute("SELECT id FROM items WHERE name = ?", (name,))
    exists = await cursor.fetchone()
    if exists:
        await db.execute(
            """
            UPDATE items
            SET price = ?, atk_bonus = ?, def_bonus = ?, category = ?, level_required = ?, effect_type = ?, effect_value = ?, is_shop_item = 1
            WHERE name = ?
            """,
            (price, atk_bonus, def_bonus, category, level_required, effect_type, effect_value, name)
        )
        return

    await db.execute(
        """
        INSERT INTO items (name, price, atk_bonus, def_bonus, category, level_required, effect_type, effect_value, is_shop_item)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (name, price, atk_bonus, def_bonus, category, level_required, effect_type, effect_value)
    )


async def seed_default_items(db):
    for name, price, atk, defense, level_required in EQUIPMENT_ITEMS:
        await _seed_item(db, name, price, atk, defense, "equipment", level_required)

    for name, price, effect_type, effect_value, level_required in POTION_ITEMS:
        await _seed_item(db, name, price, 0, 0, "potion", level_required, effect_type, effect_value)


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id TEXT UNIQUE,
            level INTEGER DEFAULT 1,
            exp INTEGER DEFAULT 0,
            hp INTEGER DEFAULT 100,
            max_hp INTEGER DEFAULT 100,
            attack INTEGER DEFAULT 10,
            defense INTEGER DEFAULT 5,
            gold INTEGER DEFAULT 50,
            mushrooms INTEGER DEFAULT 5,
            stamina INTEGER DEFAULT 100,
            max_stamina INTEGER DEFAULT 100,
            on_expedition INTEGER DEFAULT 0,
            expedition_start_time REAL DEFAULT 0,
            expedition_duration INTEGER DEFAULT 0,
            last_regen REAL DEFAULT 0,
            last_hp_regen REAL DEFAULT 0,
            last_dungeon_attack REAL DEFAULT 0,
            dungeon_progress INTEGER DEFAULT 0,
            shop_refresh_seed INTEGER DEFAULT 0,
            quest_refresh_seed INTEGER DEFAULT 0
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            atk_bonus INTEGER DEFAULT 0,
            def_bonus INTEGER DEFAULT 0,
            category TEXT DEFAULT 'equipment',
            level_required INTEGER DEFAULT 1,
            effect_type TEXT,
            effect_value INTEGER DEFAULT 0,
            is_shop_item INTEGER DEFAULT 1
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            item_id INTEGER,
            is_equipped INTEGER DEFAULT 0,
            FOREIGN KEY(item_id) REFERENCES items(id)
        )
        """)

        await _add_column(db, "users", "on_expedition", "INTEGER DEFAULT 0")
        await _add_column(db, "users", "expedition_start_time", "REAL DEFAULT 0")
        await _add_column(db, "users", "expedition_duration", "INTEGER DEFAULT 0")
        await _add_column(db, "users", "max_stamina", "INTEGER DEFAULT 100")
        await _add_column(db, "users", "last_regen", "REAL DEFAULT 0")
        await _add_column(db, "users", "last_hp_regen", "REAL DEFAULT 0")
        await _add_column(db, "users", "mushrooms", "INTEGER DEFAULT 5")
        await _add_column(db, "users", "last_dungeon_attack", "REAL DEFAULT 0")
        await _add_column(db, "users", "dungeon_progress", "INTEGER DEFAULT 0")
        await _add_column(db, "users", "shop_refresh_seed", "INTEGER DEFAULT 0")
        await _add_column(db, "users", "quest_refresh_seed", "INTEGER DEFAULT 0")

        await _add_column(db, "items", "category", "TEXT DEFAULT 'equipment'")
        await _add_column(db, "items", "level_required", "INTEGER DEFAULT 1")
        await _add_column(db, "items", "effect_type", "TEXT")
        await _add_column(db, "items", "effect_value", "INTEGER DEFAULT 0")
        await _add_column(db, "items", "is_shop_item", "INTEGER DEFAULT 1")

        await seed_default_items(db)
        await db.commit()


async def create_user(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (discord_id, last_regen, last_hp_regen, mushrooms, shop_refresh_seed, quest_refresh_seed)
            VALUES (?, ?, ?, 5, ?, ?)
            """,
            (discord_id, time.time(), time.time(), random.randint(1, 999999), random.randint(1, 999999))
        )
        await db.commit()


async def get_user(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        return await cursor.fetchone()


async def update_user(discord_id: str, **kwargs):
    if not kwargs:
        return
    async with aiosqlite.connect(DB_NAME) as db:
        set_clause = ", ".join(f"{key} = ?" for key in kwargs)
        values = list(kwargs.values()) + [discord_id]
        await db.execute(f"UPDATE users SET {set_clause} WHERE discord_id = ?", values)
        await db.commit()


async def regenerate_resources(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        user = await cursor.fetchone()
        if not user:
            return

        now = time.time()
        updates = {}

        last_stamina_regen = user['last_regen']
        if not last_stamina_regen:
            last_stamina_regen = now
            updates['last_regen'] = now

        stamina_points = int((now - last_stamina_regen) // STAMINA_REGEN_SECONDS)
        max_stamina = user['max_stamina'] or 100
        if stamina_points > 0:
            updates['stamina'] = min(user['stamina'] + stamina_points, max_stamina)
            updates['last_regen'] = now

        last_hp_regen = user['last_hp_regen']
        if not last_hp_regen:
            last_hp_regen = now
            updates['last_hp_regen'] = now

        hp_points = int((now - last_hp_regen) // HP_REGEN_SECONDS)
        max_hp = user['max_hp'] or 100
        if hp_points > 0:
            updates['hp'] = min(user['hp'] + hp_points, max_hp)
            updates['last_hp_regen'] = now

        if updates:
            set_clause = ", ".join(f"{key} = ?" for key in updates)
            values = list(updates.values()) + [discord_id]
            await db.execute(f"UPDATE users SET {set_clause} WHERE discord_id = ?", values)
            await db.commit()


async def regenerate_stamina(discord_id: str):
    await regenerate_resources(discord_id)


async def regenerate_hp(discord_id: str):
    await regenerate_resources(discord_id)


async def get_leaderboard(limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT discord_id, level, exp, gold, mushrooms FROM users
            ORDER BY level DESC, exp DESC, gold DESC
            LIMIT ?
            """,
            (limit,)
        )
        return await cursor.fetchall()


async def get_all_items(category: str = "equipment"):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        if category:
            cursor = await db.execute(
                "SELECT * FROM items WHERE category = ? ORDER BY level_required ASC, price ASC, id ASC",
                (category,)
            )
        else:
            cursor = await db.execute("SELECT * FROM items ORDER BY category ASC, level_required ASC, price ASC")
        return await cursor.fetchall()


async def get_potion_items():
    return await get_all_items("potion")


async def get_item_by_id(item_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        return await cursor.fetchone()


async def get_shop_items_for_user(discord_id: str, limit: int = 5):
    user = await get_user(discord_id)
    if not user:
        return []

    user_level = int(user['level'] or 1)
    min_level = max(1, user_level - 2)
    max_level = user_level + 2

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT * FROM items
            WHERE category = 'equipment'
              AND is_shop_item = 1
              AND level_required BETWEEN ? AND ?
            ORDER BY level_required ASC, price ASC, id ASC
            """,
            (min_level, max_level)
        )
        items = await cursor.fetchall()

        if len(items) < limit:
            cursor = await db.execute(
                """
                SELECT * FROM items
                WHERE category = 'equipment'
                  AND is_shop_item = 1
                  AND level_required <= ?
                ORDER BY level_required ASC, price ASC, id ASC
                """,
                (max_level,)
            )
            items = await cursor.fetchall()

    if not items:
        return []

    rng = random.Random(f"{discord_id}-{user['shop_refresh_seed']}-{user_level}")
    items = list(items)
    rng.shuffle(items)
    return items[:limit]


async def buy_item(discord_id: str, item_id: int, price: int):
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("BEGIN")
            await db.execute("UPDATE users SET gold = gold - ? WHERE discord_id = ?", (price, discord_id))
            await db.execute("INSERT INTO inventory (user_id, item_id) VALUES (?, ?)", (discord_id, item_id))
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise e


async def get_user_inventory(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT i.name, i.atk_bonus, i.def_bonus, i.category, i.effect_type, i.effect_value,
                   i.level_required, inv.is_equipped, inv.id as inv_id
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ?
            ORDER BY i.category ASC, i.level_required ASC, i.name ASC
            """,
            (discord_id,)
        )
        return await cursor.fetchall()


async def get_equipped_bonuses(user_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT SUM(i.atk_bonus) as total_atk, SUM(i.def_bonus) as total_def
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND inv.is_equipped = 1 AND i.category = 'equipment'
            """,
            (user_id,)
        )
        return await cursor.fetchone()


async def toggle_equip_item(user_id: str, item_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT inv.id, inv.is_equipped, i.name
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND i.category = 'equipment' AND i.name LIKE ?
            LIMIT 1
            """,
            (user_id, f"%{item_name}%")
        )
        item = await cursor.fetchone()
        if item:
            new_status = 0 if item['is_equipped'] else 1
            await db.execute("UPDATE inventory SET is_equipped = ? WHERE id = ?", (new_status, item['id']))
            await db.commit()
            return item['name'], new_status
        return None, None


async def update_user_after_fight(discord_id: str, hp: int, exp: int, gold: int, stamina: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT level FROM users WHERE discord_id = ?", (discord_id,))
        user = await cursor.fetchone()
        current_level = user['level'] if user else 1
        new_level = max(current_level, level_from_exp(exp))

        await db.execute(
            """
            UPDATE users
            SET hp = ?, exp = ?, gold = gold + ?, stamina = ?, level = ?, last_hp_regen = ?
            WHERE discord_id = ?
            """,
            (hp, exp, gold, stamina, new_level, time.time(), discord_id)
        )
        await db.commit()


async def use_item(discord_id: str, item_name: str):
    result = await use_potion(discord_id, item_name)
    return result[0]


async def use_potion(discord_id: str, item_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT inv.id as inv_id, i.*
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ? AND i.category = 'potion' AND i.name LIKE ?
            LIMIT 1
            """,
            (discord_id, f"%{item_name}%")
        )
        potion = await cursor.fetchone()
        if not potion:
            return False, "Nie masz takiej mikstury."

        cursor = await db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        user = await cursor.fetchone()
        if not user:
            return False, "Najpierw użyj /start."

        effect_type = potion['effect_type']
        effect_value = potion['effect_value'] or 0
        updates = {}
        message = ""

        if effect_type == "heal":
            if user['hp'] >= user['max_hp']:
                return False, "Masz już pełne HP. Mikstura nie została zużyta."
            updates['hp'] = min(user['max_hp'], user['hp'] + effect_value)
            message = f"❤️ Uleczono postać o `{updates['hp'] - user['hp']}` HP."
        elif effect_type == "full_heal":
            if user['hp'] >= user['max_hp']:
                return False, "Masz już pełne HP. Mikstura nie została zużyta."
            updates['hp'] = user['max_hp']
            message = "❤️ HP zostało odnowione do pełna."
        elif effect_type == "stamina":
            max_stamina = user['max_stamina'] or 100
            if user['stamina'] >= max_stamina:
                return False, "Masz już pełną staminę. Mikstura nie została zużyta."
            updates['stamina'] = min(max_stamina, user['stamina'] + effect_value)
            message = f"⚡ Odnowiono `{updates['stamina'] - user['stamina']}` staminy."
        elif effect_type == "attack":
            updates['attack'] = user['attack'] + effect_value
            message = f"⚔️ Atak zwiększony o `{effect_value}`."
        elif effect_type == "defense":
            updates['defense'] = user['defense'] + effect_value
            message = f"🛡️ Obrona zwiększona o `{effect_value}`."
        elif effect_type == "max_hp":
            updates['max_hp'] = user['max_hp'] + effect_value
            updates['hp'] = user['hp'] + effect_value
            message = f"❤️ Maksymalne HP zwiększone o `{effect_value}`."
        else:
            return False, "Ta mikstura nie ma ustawionego działania."

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [discord_id]
        await db.execute(f"UPDATE users SET {set_clause} WHERE discord_id = ?", values)
        await db.execute("DELETE FROM inventory WHERE id = ?", (potion['inv_id'],))
        await db.commit()
        return True, f"Użyto: **{potion['name']}**.\n{message}"


async def spend_mushrooms(discord_id: str, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "UPDATE users SET mushrooms = mushrooms - ? WHERE discord_id = ? AND mushrooms >= ?",
            (amount, discord_id, amount)
        )
        await db.commit()
        return cursor.rowcount > 0


async def add_mushrooms(discord_id: str, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET mushrooms = mushrooms + ? WHERE discord_id = ?", (amount, discord_id))
        await db.commit()


async def increase_max_stamina(discord_id: str, cost: int = 3, amount: int = 10):
    paid = await spend_mushrooms(discord_id, cost)
    if not paid:
        return False, f"Potrzebujesz `{cost}` grzybków."

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET max_stamina = max_stamina + ?, stamina = stamina + ? WHERE discord_id = ?",
            (amount, amount, discord_id)
        )
        await db.commit()
    return True, f"⚡ Maksymalna stamina zwiększona o `{amount}`."


async def refresh_user_shop(discord_id: str, cost: int = 1):
    paid = await spend_mushrooms(discord_id, cost)
    if not paid:
        return False, f"Potrzebujesz `{cost}` grzybka."

    await update_user(discord_id, shop_refresh_seed=random.randint(1, 999999))
    return True, "🛒 Sklep został odświeżony."


async def refresh_user_quests(discord_id: str, cost: int = 1):
    paid = await spend_mushrooms(discord_id, cost)
    if not paid:
        return False, f"Potrzebujesz `{cost}` grzybka."

    await update_user(discord_id, quest_refresh_seed=random.randint(1, 999999))
    return True, "🍻 Misje zostały odświeżone."


def get_dungeon_monsters():
    return DUNGEON_MONSTERS


def get_current_dungeon_monster_from_user(user):
    progress = int(user['dungeon_progress'] or 0)
    index = max(0, min(progress, len(DUNGEON_MONSTERS) - 1))
    return DUNGEON_MONSTERS[index]


def get_dungeon_cooldown_seconds(user):
    last_attack = user['last_dungeon_attack'] or 0
    remaining = int(DUNGEON_COOLDOWN_SECONDS - (time.time() - last_attack))
    return max(0, remaining)


async def start_dungeon_attack(discord_id: str, use_mushroom: bool = False):
    user = await get_user(discord_id)
    if not user:
        return False, "Najpierw użyj /start.", None

    remaining = get_dungeon_cooldown_seconds(user)
    if remaining > 0:
        if not use_mushroom:
            minutes = remaining // 60
            seconds = remaining % 60
            return False, f"Loch odpoczywa. Spróbuj za `{minutes} min {seconds} sek` albo użyj grzybka.", None

        paid = await spend_mushrooms(discord_id, 1)
        if not paid:
            return False, "Nie masz grzybków na pominięcie czekania.", None

    await update_user(discord_id, last_dungeon_attack=time.time())
    fresh_user = await get_user(discord_id)
    monster = dict(get_current_dungeon_monster_from_user(fresh_user))
    return True, "Loch rozpoczęty.", monster


async def complete_dungeon_monster(discord_id: str):
    user = await get_user(discord_id)
    if not user:
        return "Nie znaleziono postaci."

    progress = int(user['dungeon_progress'] or 0)
    monster = DUNGEON_MONSTERS[min(progress, len(DUNGEON_MONSTERS) - 1)]

    if monster.get('final'):
        item_name, atk_bonus, def_bonus, item_id = await grant_dungeon_reward_item(discord_id)
        await add_mushrooms(discord_id, 1)
        await update_user(discord_id, dungeon_progress=0)
        return (
            "### 🏰 Loch ukończony!\n"
            f"Pokonałeś ostatniego przeciwnika: **{monster['name']}**.\n\n"
            f"🎁 Otrzymujesz specjalny przedmiot: **{item_name}**\n"
            f"⚔️ Atak: `+{atk_bonus}` | 🛡️ Obrona: `+{def_bonus}`\n"
            "🍄 Bonus: `+1 grzybek`\n"
            f"{exp_info_line(user)}\n\n"
            "Loch został zresetowany i możesz przechodzić go od początku."
        )

    await update_user(discord_id, dungeon_progress=progress + 1)
    next_monster = DUNGEON_MONSTERS[progress + 1]
    return (
        "### ✅ Potwór z lochu pokonany\n"
        f"Pokonałeś: **{monster['name']}**.\n\n"
        f"Następny przeciwnik: **{next_monster['name']}** `lvl {next_monster['level']}`.\n"
        f"{exp_info_line(user)}\n"
        "Następny atak będzie możliwy po 30 minutach albo po użyciu grzybka."
    )


async def grant_dungeon_reward_item(discord_id: str):
    user = await get_user(discord_id)
    level = user['level'] if user else 1

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT MAX(atk_bonus) as max_atk, MAX(def_bonus) as max_def
            FROM items
            WHERE category = 'equipment' AND is_shop_item = 1 AND level_required <= ?
            """,
            (level + 2,)
        )
        row = await cursor.fetchone()
        max_atk = row['max_atk'] or 5
        max_def = row['max_def'] or 5

        if random.choice([True, False]):
            name = f"Relikt Lochu Lvl {level}"
            atk_bonus = max_atk + 4
            def_bonus = max(1, max_def // 4)
        else:
            name = f"Pancerz z Głębin Lvl {level}"
            atk_bonus = max(1, max_atk // 4)
            def_bonus = max_def + 4

        price = 0
        await db.execute(
            """
            INSERT INTO items (name, price, atk_bonus, def_bonus, category, level_required, is_shop_item)
            VALUES (?, ?, ?, ?, 'equipment', ?, 0)
            """,
            (name, price, atk_bonus, def_bonus, level)
        )
        cursor = await db.execute("SELECT last_insert_rowid()")
        item_row = await cursor.fetchone()
        new_item_id = item_row[0]
        await db.execute("INSERT INTO inventory (user_id, item_id) VALUES (?, ?)", (discord_id, new_item_id))
        await db.commit()

    return name, atk_bonus, def_bonus, new_item_id


def _make_monster(details, level: int, difficulty: str):
    name = details.get("name", "Nieznany Potwór")
    base_hp = int(details.get("hit_points", 50) or 50)
    base_attack = int(details.get("strength", 10) or 10)
    base_defense = int(details.get("dexterity", 10) or 10)

    if difficulty == "hard":
        hp = max(70 + level * 12, int(base_hp * 1.15))
        attack = max(12 + level * 3, int(base_attack * 1.10))
        defense = max(6 + level, int(base_defense * 0.60))
    else:
        hp = max(40 + level * 8, int(base_hp * 0.70))
        attack = max(8 + level * 2, int(base_attack * 0.75))
        defense = max(4 + level, int(base_defense * 0.45))

    return {
        "name": name,
        "hp": hp,
        "attack": attack,
        "defense": defense,
        "gold": random.randint(10, 30) * level
    }


def _fallback_monster(level: int, difficulty: str, rng=None):
    rng = rng or random
    if difficulty == "hard":
        names = ["Ogr z Ciemnego Lasu", "Wilczy Herszt", "Kamienny Troll"]
        return {
            "name": rng.choice(names),
            "hp": 90 + level * 15,
            "attack": 14 + level * 3,
            "defense": 7 + level,
            "gold": 25 * level
        }
    names = ["Goblin Zwiadowca", "Zbój z Traktu", "Bagienny Szkielet"]
    return {
        "name": rng.choice(names),
        "hp": 45 + level * 8,
        "attack": 8 + level * 2,
        "defense": 4 + level,
        "gold": 12 * level
    }


def _build_easy_quest(level: int, rng):
    easy_names = [
        "Dostarczenie listu do strażnika",
        "Pomoc karczmarzowi przy beczkach",
        "Zaniesienie paczki do kupca",
        "Pilnowanie wozu przed karczmą"
    ]

    return {
        "name": rng.choice(easy_names),
        "difficulty": "easy",
        "difficulty_label": "🟢 ŁATWA",
        "requires_combat": False,
        "duration": 1,
        "gold": rng.randint(5, 12) * level,
        "exp": rng.randint(10, 25) * level,
        "cr": 0,
        "monster": None
    }


async def get_random_quests(user_id: str):
    user = await get_user(user_id)
    level = user['level'] if user else 1
    quest_seed = user['quest_refresh_seed'] if user else random.randint(1, 999999)
    rng = random.Random(f"{user_id}-{level}-{quest_seed}")

    quest_defs = [
        {
            "difficulty": "hard",
            "difficulty_label": "🔴 TRUDNA",
            "requires_combat": True,
            "duration": rng.choice([2, 3]),
            "gold_range": (70, 120),
            "exp_range": (140, 220),
            "name_prefix": "Polowanie na"
        },
        {
            "difficulty": "medium",
            "difficulty_label": "🟡 ŚREDNIA",
            "requires_combat": True,
            "duration": rng.choice([1, 2]),
            "gold_range": (30, 60),
            "exp_range": (60, 120),
            "name_prefix": "Starcie z"
        }
    ]

    monster_details = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_MONSTERS_URL) as response:
                if response.status == 200:
                    all_data = await response.json()
                    results = all_data.get('results', [])
                    if len(results) >= 2:
                        random_refs = rng.sample(results, 2)
                        for monster_ref in random_refs:
                            async with session.get(f"https://www.dnd5eapi.co{monster_ref['url']}") as res:
                                if res.status == 200:
                                    monster_details.append(await res.json())
    except Exception:
        monster_details = []

    quests = []
    for idx, quest_def in enumerate(quest_defs):
        difficulty = quest_def["difficulty"]
        details = monster_details[idx] if idx < len(monster_details) else {}
        monster = _make_monster(details, level, difficulty) if details else _fallback_monster(level, difficulty, rng)
        gold_min, gold_max = quest_def["gold_range"]
        exp_min, exp_max = quest_def["exp_range"]

        quests.append({
            "name": f"{quest_def['name_prefix']} {monster['name']}",
            "difficulty": difficulty,
            "difficulty_label": quest_def["difficulty_label"],
            "requires_combat": True,
            "duration": quest_def["duration"],
            "gold": rng.randint(gold_min, gold_max) * level,
            "exp": rng.randint(exp_min, exp_max) * level,
            "cr": details.get("challenge_rating", 1) if details else 1,
            "monster": monster
        })

    quests.append(_build_easy_quest(level, rng))
    return quests
