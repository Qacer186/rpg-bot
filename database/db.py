import aiosqlite
import aiohttp
import random
import time

DB_NAME = "rpg.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Tabela użytkowników
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
            stamina INTEGER DEFAULT 100,
            on_expedition INTEGER DEFAULT 0,
            expedition_start_time REAL DEFAULT 0,
            expedition_duration INTEGER DEFAULT 0
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

        # Dodawanie nowych kolumn, jeśli nie istnieją
        try:
            await db.execute("ALTER TABLE users ADD COLUMN on_expedition INTEGER DEFAULT 0")
        except:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN expedition_start_time REAL DEFAULT 0")
        except:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN expedition_duration INTEGER DEFAULT 0")
        except:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN max_stamina INTEGER DEFAULT 100")
        except:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN last_regen REAL DEFAULT 0")
        except:
            pass
        
        await db.commit()

# Funkcje pomocnicze do ekwipunku
async def buy_item(discord_id: str, item_id: int, price: int):
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("BEGIN")
            await db.execute("UPDATE users SET gold = gold - ? WHERE discord_id = ?", (price, discord_id))
            await db.execute("INSERT INTO inventory (user_id, item_id) VALUES (?, ?)", (discord_id, item_id))
            await db.commit() # Zatwierdzanie obu zmian naraz
        except Exception as e:
            await db.rollback() # Cofnięcie zmian w przypadku błędu
            raise e

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
        await db.execute("""
        INSERT OR IGNORE INTO users (discord_id, last_regen)
        VALUES (?, ?)
        """, (discord_id, time.time()))
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
        # Aktualizacja statystyk po walce
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

async def regenerate_stamina(discord_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        user = await get_user(discord_id)
        if not user:
            return
        now = time.time()
        regen_rate = 60  # 1 punkt staminy na minutę
        time_passed = now - user['last_regen']
        points_to_add = int(time_passed // regen_rate)
        if points_to_add > 0:
            new_stamina = min(user['stamina'] + points_to_add, user['max_stamina'])
            await db.execute("UPDATE users SET stamina = ?, last_regen = ? WHERE discord_id = ?", (new_stamina, now, discord_id))
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

API_MONSTERS_URL = "https://www.dnd5eapi.co/api/monsters"

async def get_random_quests(user_id: str):
    """Losuje 3 potwory z API i przypisuje im nagrody skalowane poziomem gracza"""
    user = await get_user(user_id)
    level = user['level'] if user else 1
    
    async with aiohttp.ClientSession() as session:
        async with session.get(API_MONSTERS_URL) as response:
            if response.status != 200: return []
            all_data = await response.json()
            # Losujemy 3 różne indeksy z listy potworów
            random_indices = random.sample(range(len(all_data['results'])), 3)
            
            quests = []
            for idx in random_indices:
                monster_ref = all_data['results'][idx]
                async with session.get(f"https://www.dnd5eapi.co{monster_ref['url']}") as res:
                    details = await res.json()
                    
                    # Logika nagród w stylu S&F: złoto vs doświadczenie
                    # Misje o różnej trudności i czasie trwania
                    duration = random.choice([1, 2]) # minuty
                    base_gold = random.randint(10, 50) * level
                    base_exp = random.randint(50, 150) * level
                    
                    quests.append({
                        "name": details.get("name", "Tajemniczy Przeciwnik"),
                        "duration": duration,
                        "gold": base_gold if random.random() > 0.5 else int(base_gold * 0.5),
                        "exp": base_exp if random.random() < 0.5 else int(base_exp * 2),
                        "cr": details.get("challenge_rating", 1),
                        "monster": {
                            "name": details.get("name", "Nieznany Potwór"),
                            "hp": details.get("hit_points", 50),
                            "attack": details.get("strength", 10),
                            "gold": random.randint(10, 30)
                        }
                    })
            return quests