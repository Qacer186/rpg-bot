# Discord RPG Bot

System RPG dla Discord z mechaniką walki w karczme, systemem Quest + RabbitMQ worker.  
Tech: Python 3.11+, discord.py, SQLite, RabbitMQ, aiosqlite.

## Setup

### Wymagania
```bash
pip install -r requirements.txt
```

### Konfiguracja
1. Stwórz `.env`:
   ```
   DISCORD_TOKEN=<twój_token>
   ```

2. Zainicjuj RabbitMQ (localhost:5672):
   ```bash
   # macOS: brew install rabbitmq
   # Linux: apt install rabbitmq-server
   brew services start rabbitmq-server
   ```

### Uruchomienie

**Terminal 1 - Bot Discord:**
```bash
python main.py
```

**Terminal 2 - Background Worker (przetwarzanie quest/walki):**
```bash
python services/worker.py
```

## Architektura

```
Discord Command (/tavern)
    ↓
Quest View (UI w Discord)
    ↓
RabbitMQ (quest_selections queue)
    ↓
Worker (quest timer, SQL updates)
    ↓
Fight View (mechanika walki)
    ↓
Database (exp, gold, HP, stamina)
```

## Struktura projektu

| Plik | Rola |
|------|------|
| `main.py` | Discord bot entry point, loading Cogs, init DB |
| `database/db.py` | SQL queries, user management, items |
| `commands/rpg_commands.py` | Slash commands (/start, /tavern, /profile, etc.) |
| `views/fight_view.py` | Fight UI & damage calculation |
| `services/worker.py` | Background worker - quest timers, RabbitMQ consumer |
| `services/rabbitmq.py` | RabbitMQ queue operations |

## Komendy

- `/start` - Tworzy nową postać
- `/profile` - HP, statystyki, level, gold
- `/tavern` - Otwiera karczmę z 3 losowymi misjami
- `/shop` - Lista przedmiotów (broń, pancerz)
- `/buy <id>` - Zakup przedmiotu
- `/inventory` - Lista posiadanych itemów
- `/equip <nazwa>` - Zakład/zdejmij przedmiot
- `/heal` - Użycie mikstury HP
- `/leaderboard` - Top 10 graczy

## Game Mechanics

**Quest System:**
- W karczme dostępne 3 losowe misje (czas: 1-2 min)
- Po ukończeniu misji walka z potworem z API (D&D 5e)
- Wygrana: gold + EXP
- Przegrana: brak nagród

**Combat:**
- Turn-based: gracz atakuje → potwór kontruje
- Damage: base_stat + equipment_bonus +/- variance
- Stamina: -10 za walkę, regeneracja 1 pt/min
- Equipment bonuses: atk (broń), def (pancerz)

**Economy:**
- Przedmioty kupuje się za gold
- Cena: 50-500 gold
- Bonus: +1 do +5 atk/def

## Notes

- **Isolation:** Każda walka ma lokalną kopię HP (nie zmienia DB przy każdym kliknięciu)
- **Transactions:** Quest selection → background task → fight → DB update
- **Stale State Fix:** Pobieranie aktualnych danych z DB przed zapisem wyników walki
- Pełna dokumentacja: patrz `ARCHITECTURE.md`
