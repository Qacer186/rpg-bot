# Dokumentacja techniczna projektu Discord RPG Bot

Ten dokument przedstawia szczegółową architekturę i przepływ działania projektu.

## Ogólny cel

System to prosty RPG działający na Discordzie, z:
- poleceniami slash (`/start`, `/fight`, `/shop`, etc.)
- bazą SQLite (`rpg.db`)
- przeglądem przedmiotów i ekwipunku
- logiką walki w widoku Discord
- integracją RabbitMQ dla logów walki

## 1. Główne moduły

### `main.py`
- definiuje klasę `RpgBot(commands.Bot)`.
- `setup_hook()`:
  - `init_db()` (database/db.py)
  - dynamiczne ładowanie `commands/*.py` jako Cog (każdy plik w katalogu `commands`)
  - synchronizacja slash komend z serwerem (guild)
- `on_ready()` loguje, że bot jest zalogowany.

### `database/db.py`
- pełna warstwa danych.
- tabele:
  - `users`: informacje o graczu
  - `items`: baza przedmiotów
  - `inventory`: ekwipunek gracza
- seed przedmiotów, w tym `Mikstura HP` (ID=4).

Funkcje:
- `init_db()`
- `create_user(discord_id)`
- `get_user(discord_id)`
- `update_user(discord_id, **kwargs)`
- `update_user_after_fight(discord_id, hp, exp, gold, stamina)`
- `buy_item(discord_id, item_id, price)`
- `get_user_inventory(discord_id)`
- `get_leaderboard(limit)`
- `get_all_items()`
- `get_item_by_id(item_id)`
- `get_equipped_bonuses(user_id)`
- `toggle_equip_item(user_id, item_name)`
- `use_item(user_id, item_name)`

Te funkcje eliminują SQL z `commands` i `views`.

### `commands/rpg_commands.py`
- `RPGCog(commands.Cog)` z komendami:
  - `/start`, `/profile`, `/fight`, `/shop`, `/buy`, `/inventory`, `/equip`, `/heal`
- korzysta z funkcji bazy z `database/db.py`.

Przykłady:
- `/shop`: `get_all_items()`
- `/buy`: `get_item_by_id()` + `buy_item()`
- `/equip`: `toggle_equip_item()`
- `/heal`: `use_item('Mikstura HP')` + `update_user(...hp...)`
- `/fight`: `get_user()` + `get_random_monster()` + `send_to_queue('fight_logs', ...)`

### `views/fight_view.py`
- `FightView(discord.ui.View)` i przycisk `attack`.
- w `attack()`:
  - `get_equipped_bonuses(discord_id)`
  - obliczenia skali obrażeń i obrony
  - runda potwór/gracz
  - `end_fight()` -> `update_user_after_fight()`

Nie ma już `aiosqlite` w tej funkcji.

### `services/rabbitmq.py`
- `send_to_queue(queue_name, data)` - centralny transport do RabbitMQ.
- `commands/rpg_commands.py` korzysta z tej funkcji.

### `services/monster_service.py`
- funkcja `get_random_monster()` pobierająca potwora z API.

## 2. Przepływ funkcjonalny

### Uruchomienie bota
1. start `python main.py`
2. `setup_hook()`
3. `init_db()` i tabelki, seed itemów
4. ładujemy Cog `RPGCog`
5. synchronizujemy slash komendy

### `/start`
- sprawdza, czy użytkownik już istnieje (w `users`)
- jeśli nie, tworzy w `create_user` i zwraca potwierdzenie

### `/profile`
- pobiera `get_user`
- generuje embed statystyk

### `/shop` i `/buy`
- `/shop` pobiera wszystkie itemy `get_all_items`
- `/buy` weryfikuje złoto i `get_item_by_id`, następnie `buy_item`

### `/inventory` i `/equip`
- `/inventory`: `get_user_inventory`
- `/equip`: `toggle_equip_item`

### `/heal`
- próbuje `use_item('Mikstura HP')`
- jeśli OK -> `update_user(hp=max_hp)`

### `/fight`
- ładujemy potwora z API
- wysyłamy log do RabbitMQ `send_to_queue` z `fight_logs`
- tworzymy i wysyłamy `FightView`

### walka w `FightView`:
- `attack()`: bonusy z `get_equipped_bonuses`
- obliczenia stanu HP potwora i użytkownika
- koniec -> `update_user_after_fight`

## 3. Adnotacja techniczna

- centralizacja SQL: `database/db.py`.
- jedno źródło prawdy dla przedmiotów + ekwipu.
- RabbitMQ jako serwis w `services/rabbitmq.py`.
- `fight_view.py` przechodzi do DB tylko przez interfejs funkcji.

## 4. Dalsze kroki

- testy `pytest` dla `database` i `commands`
- refaktoring fight logic do serwisu `services/combat.py`
- migracja SQL (PostgreSQL) w jednym pliku: `database/db.py`
