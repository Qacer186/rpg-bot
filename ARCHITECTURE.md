# Discord RPG Bot - Dokumentacja Techniczna

System RPG dla Discord z mechaniką karczmy (tavern), quest-ów, walk i systemem ekwipunku.

## Ogólny cel

- Slash komendy (`/start`, `/tavern`, `/profile`, `/shop`, etc.)
- SQLite baza (`rpg.db`)
- Karczma z 3 losowymi misjami (quest-ami)
- Turn-based walka z potworami z API (D&D 5e)
- RabbitMQ worker do obsługi quest timerów
- System staminy, ekwipunku i nagród

## 1. Główne moduły

### `main.py`
- `RpgBot(commands.Bot)` - entry point
- `setup_hook()`:
  - `init_db()` - inicjalizacja tabel, seed przedmiotów
  - Dynamiczne ładowanie `commands/*.py` jako Cog
  - Synchronizacja slash komend z Discord server
- `on_ready()` - log zalogowania

### `database/db.py`
- Warstwa danych, 100% SQL queries
- **Tabele:**
  - `users`: discord_id, level, exp, hp, max_hp, attack, defense, gold, stamina, max_stamina, last_regen, on_expedition, expedition_start_time, expedition_duration
  - `items`: name, price, atk_bonus, def_bonus
  - `inventory`: user_id, item_id, is_equipped

- **Kluczowe funkcje:**
  - `get_user()`, `create_user()`, `update_user()`
  - `buy_item()`, `use_item()`
  - `get_user_inventory()`, `toggle_equip_item()`, `get_equipped_bonuses()`
  - `update_user_after_fight()` - atomowa aktualizacja HP, EXP, gold, stamina
  - `regenerate_stamina()` - naliczanie staminy (1pt/min)
  - `get_random_quests()` - losuje 3 potwory z D&D API, skaluje nagrody do poziomu gracza

### `commands/rpg_commands.py`
- `QuestProgressView` - UI pokazujący progress misji (timer, procent)
- `QuestView` - UI karczmy z 3 przyciskami do questów
- `RPGCog` - wszystkie slash komendy:
  - `/start` - tworzenie postaci
  - `/profile` - stats
  - `/tavern` - otwiera karczmę, regeneruje staminę
  - `/shop` - lista przedmiotów
  - `/buy <id>` - zakup
  - `/inventory` - ekwipunek
  - `/equip <nazwa>` - założ/zdejmij item
  - `/heal` - użycie mikstury HP
  - `/leaderboard` - top 10
  - `/expedition_status` - status misji

**Quest Flow w /tavern:**
1. Pobranie 3 losowych questów (`get_random_quests`)
2. Wyświetlenie UI karczmy
3. Gracz wybiera quest → wysłanie do RabbitMQ (`quest_selections` queue)
4. Wyłączenie przycisków, pokazanie progressu
5. `QuestProgressView` aktualizuje UI co 5 sekund
6. Po upłynięciu czasu → `FightView` z walką

### `views/fight_view.py`
- `FightView` - UI walki z przyciskiem "Atakuj"
- **attack() button:**
  - Pobranie bonusów z ekwipunku: `get_equipped_bonuses()`
  - Atak gracza: `base_atk + equipment_bonus +/- variance`
  - HP potwora -= dmg
  - Kontra potwora: `max(0, monster_atk - player_def - equipment_bonus)`
  - HP gracza -= dmg
  - Sprawdzenie warunku wygranej/przegranej

- **end_fight():**
  - **Wygrana:** +20 EXP + monster_gold + callback `on_win()`
  - **Przegrana:** brak EXP, 0 gold, HP reset do 20, callback `on_lose()`
  - Pobranie aktualnych danych z DB (`get_user()`) przed aktualizacją - **fix do stale exp values**
  - Stamina zawsze -10 (niezależnie od wyniku)

### `services/worker.py`
- RabbitMQ consumer dla quest-ów
- **process_quest_selection():**
  - Nasłuchuje `quest_selections` queue
  - Ustawia `on_expedition=1`, zapisuje czas i czas trwania
  - `asyncio.sleep(duration * 60)` - czeka aż quest się skończy
  - Po upłynięciu: `on_expedition=0`, ready dla walki
  - Nagrody (EXP, gold) są przyznawane w `FightView.end_fight()`

- **process_fight_log():**
  - Nasłuchuje `fight_logs` queue
  - Loguje akcje do `logs/game_events.log`

### `services/rabbitmq.py`
- `send_to_queue(queue_name, data)` - wysyła JSON do RabbitMQ

### `services/monster_service.py`
- `get_random_monster()` - pobiera potwora z D&D 5e API

## 2. Przepływ funkcjonalny

### Sekwencja: Quest → Walka → Nagrody

```
/tavern (gracz)
  ↓
[QuestView] wyświetla 3 misje
  ↓
gracz klika quest
  ↓
send_to_queue('quest_selections', {...})
  ↓
[Worker.process_quest_selection]
  ├─ update_user(on_expedition=1, start_time, duration)
  ├─ asyncio.sleep(duration * 60)
  └─ update_user(on_expedition=0)
  ↓
[QuestProgressView] pokazuje timer i progress
  ↓
po upłynięciu czasu
  ↓
[FightView] walka z potworem
  ├─ attack button: damage calc + HP update
  ├─ if monster_hp <= 0: end_fight(win=True) 
  │  └─ +20 EXP, +gold, callback return_to_tavern
  └─ if player_hp <= 0: end_fight(win=False)
     └─ brak EXP, 0 gold, HP=20, callback return_to_tavern
  ↓
[return_to_tavern]
  ├─ regenerate_stamina()
  ├─ get_random_quests() - nowe misje
  └─ [QuestView] znowu karczma
```

### Poszczególne komendy

**`/start`** - `create_user(discord_id)`

**`/profile`** - `get_user()` + render embeda ze stats

**`/tavern`**
- `regenerate_stamina()` - nalicz staminę
- Sprawdź `stamina >= 10`
- `get_random_quests()` - pobierz misje
- Wyświetl `QuestView`

**`/shop`** - `get_all_items()` + render lista

**`/buy <id>`** - `get_item_by_id()` + `buy_item()` + check gold

**`/inventory`** - `get_user_inventory()` + pokazuj equipped status

**`/equip <nazwa>`** - `toggle_equip_item()` + update view

**`/heal`** - `use_item('Mikstura HP')` + `update_user(hp=max_hp)`

**`/leaderboard`** - `get_leaderboard()` + render top 10

### Walka - detale

**Damage calc:**
```python
player_dmg = randint(base_atk + atk_bonus - 2, base_atk + atk_bonus + 5)
monster_dmg = max(0, base_monster_atk - (player_def + def_bonus))
```

**Stamina:**
- Regeneracja: 1 punkt na minutę (od `last_regen`)
- Koszt walki: -10
- Max: `max_stamina` (zwykle 100)

**Equipment bonuses:**
- Pobranie: `get_equipped_bonuses(user_id)` → aggregate SUM w SQL
- Brak itemów = NULL → obsługa w Python (domyślnie 0)
- Dynamiczny wpływ na damage i reduction

## 3. Kluczowe decyzje techniczne

### DB Isolation
- Każda walka ma **lokalną kopię HP** (`self.user_hp`, `self.monster_hp`)
- DB aktualizowany tylko raz przy `end_fight()`
- Brak zagnieżdżonych transakcji, bezpieczne wielordzeniowo

### Stale EXP Fix
- Po przegranej: pobierz `current_user['exp']` z DB i ustaw bez zmian
- Eliminuje błędy gdzie gracz dostawał EXP mimo przegranej

### RabbitMQ Workflow
- Quest selection → queue
- Worker nasłuchuje, obsługuje timer
- Fight UI pojawia się po upłynięciu timeru
- Dekouplowanie: Discord UI ≠ Backend timery

### SQL Organization
- Wszystkie queries w `database/db.py`
- Commands/Views nie mają `aiosqlite` importów
- Łatwa migracja (np. na PostgreSQL)

## 4. Future improvements

- [ ] Testy `pytest` dla `database/` i `commands/`
- [ ] Refactor fight logic do `services/combat.py`
- [ ] Migracja na PostgreSQL
- [ ] Caching questów (zmniejszenie API calls)
- [ ] Admin komendy (resetowanie gracza, itp.)
- [ ] XP scaling curve (nowe poziomy cięższe)
