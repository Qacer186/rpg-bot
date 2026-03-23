import aiosqlite

DB_NAME = "rpg.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Tabela użytkowników (już ją masz, upewnij się, że jest kompletna)
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
            gold INTEGER DEFAULT 50, -- Dajemy 50 na start na pierwszy miecz
            stamina INTEGER DEFAULT 100
        )
        """)

        # Tabela przedmiotów (Sklep)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            atk_bonus INTEGER DEFAULT 0,
            def_bonus INTEGER DEFAULT 0
        )
        """)

        # Tabela ekwipunku
        await db.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            item_id INTEGER,
            is_equipped INTEGER DEFAULT 0,
            FOREIGN KEY(item_id) REFERENCES items(id)
        )
        """)

        # Dodajemy przykładowe przedmioty, jeśli ich nie ma
        await db.execute("INSERT OR IGNORE INTO items (id, name, price, atk_bonus, def_bonus) VALUES (1, 'Drewniany Miecz', 30, 3, 0)")
        await db.execute("INSERT OR IGNORE INTO items (id, name, price, atk_bonus, def_bonus) VALUES (2, 'Skórzana Tunika', 30, 0, 2)")
        await db.execute("INSERT OR IGNORE INTO items (id, name, price, atk_bonus, def_bonus) VALUES (3, 'Żelazny Miecz', 120, 10, 0)")
        await db.execute("INSERT OR IGNORE INTO items (id, name, price, atk_bonus, def_bonus) VALUES (4, 'Mikstura HP', 20, 0, 0)")
        
        await db.commit()

# Funkcje pomocnicze do ekwipunku
async def buy_item(discord_id: str, item_id: int, price: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET gold = gold - ? WHERE discord_id = ?", (price, discord_id))
        await db.execute("INSERT INTO inventory (user_id, item_id) VALUES (?, ?)", (discord_id, item_id))
        await db.commit()

async def get_user_inventory(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT i.name, i.atk_bonus, i.def_bonus, inv.is_equipped, inv.id as inv_id
            FROM inventory inv
            JOIN items i ON inv.item_id = i.id
            WHERE inv.user_id = ?
        """, (discord_id,))
        return await cursor.fetchall()

async def get_leaderboard(limit: int = 10):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Sortujemy po poziomie, potem po exp, na końcu po złocie
        cursor = await db.execute("""
            SELECT discord_id, level, exp, gold FROM users 
            ORDER BY level DESC, exp DESC, gold DESC 
            LIMIT ?
        """, (limit,))
        return await cursor.fetchall()

async def create_user(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        # Wystarczy podać discord_id, reszta uzupełni się sama (DEFAULT)
        await db.execute("""
        INSERT OR IGNORE INTO users (discord_id)
        VALUES (?)
        """, (discord_id,))
        await db.commit()

async def get_user(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        # Row_factory pozwala odwoływać się do kolumn po nazwach, np. user['gold']
        db.row_factory = aiosqlite.Row 
        cursor = await db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,))
        return await cursor.fetchone()

async def get_all_items():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM items")
        return await cursor.fetchall()

async def get_item_by_id(item_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        return await cursor.fetchone()

async def get_equipped_bonuses(user_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT SUM(i.atk_bonus) as total_atk, SUM(i.def_bonus) as total_def 
            FROM inventory inv 
            JOIN items i ON inv.item_id = i.id 
            WHERE inv.user_id = ? AND inv.is_equipped = 1
        """, (user_id,))
        return await cursor.fetchone()

async def toggle_equip_item(user_id: str, item_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT inv.id, inv.is_equipped, i.name 
            FROM inventory inv 
            JOIN items i ON inv.item_id = i.id 
            WHERE inv.user_id = ? AND i.name LIKE ?
        """, (user_id, f"%{item_name}%"))
        item = await cursor.fetchone()
        if item:
            new_status = 0 if item['is_equipped'] else 1
            await db.execute("UPDATE inventory SET is_equipped = ? WHERE id = ?", (new_status, item['id']))
            await db.commit()
            return item['name'], new_status
        return None, None

async def update_user_after_fight(discord_id: str, hp: int, exp: int, gold: int, stamina: int):
    async with aiosqlite.connect(DB_NAME) as db:
        # Aktualizujemy statystyki po walce
        await db.execute("""
            UPDATE users 
            SET hp = ?, exp = ?, gold = gold + ?, stamina = ?
            WHERE discord_id = ?
        """, (hp, exp, gold, stamina, discord_id))
        await db.commit()

# Funkcja do aktualizacji użytkownika (ogólna)
async def update_user(discord_id: str, **kwargs):
    async with aiosqlite.connect(DB_NAME) as db:
        set_clause = ', '.join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [discord_id]
        await db.execute(f"UPDATE users SET {set_clause} WHERE discord_id = ?", values)
        await db.commit()

# Funkcja do użycia przedmiotu konsumpcyjnego (usuwa jeden z inventory)
async def use_item(discord_id: str, item_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Znajdź item_id po nazwie
        cursor = await db.execute("SELECT id FROM items WHERE name = ?", (item_name,))
        item = await cursor.fetchone()
        if not item:
            return False
        item_id = item['id']
        # Sprawdź czy użytkownik ma przedmiot w inventory
        cursor = await db.execute("SELECT id FROM inventory WHERE user_id = ? AND item_id = ? LIMIT 1", (discord_id, item_id))
        inv_item = await cursor.fetchone()
        if not inv_item:
            return False
        # Usuń jeden przedmiot
        await db.execute("DELETE FROM inventory WHERE id = ?", (inv_item['id'],))
        await db.commit()
        return True