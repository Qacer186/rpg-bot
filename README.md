# Discord RPG Bot

Prosty system RPG dla Discord (slash-komendy), stworzony w Pythonie (discord.py) + SQLite + RabbitMQ.

## Instalacja

1. `pip install discord.py aiosqlite pika python-dotenv`
2. stwórz plik `.env` z kluczem:
   - `DISCORD_TOKEN=<token>`
3. uruchom:
   - `python main.py`

## Struktura projektu

- `main.py`: bot, ładowanie Cogów, inicjalizacja DB
- `database/db.py`: 100% logiki bazy i zapytań SQL
- `commands/rpg_commands.py`: komendy slash jako Cog
- `views/fight_view.py`: mechanika walki i przycisk discord
- `services/rabbitmq.py`: wysyłka logów walki do RabbitMQ

## Komendy

- `/start` - tworzy postać
- `/profile` - pokazuje profil i statystyki
- `/shop` - lista przedmiotów
- `/buy <id>` - zakup przedmiotu
- `/inventory` - lista itemów w ekwipunku
- `/equip <nazwa>` - zakłada lub zdejmuje item
- `/heal` - używa Mikstury HP i odnowienie HP
- `/fight` - rozpoczyna walkę z potworem

## Rekomendowane pliki

- `ARCHITECTURE.md` - pełna dokumentacja architektury i przepływu (w tym informacje o izolacji SQL, RabbitMQ, logice walki).

## Dodatkowe kroki

- dodać testy `pytest`
- migracja na PG (opis już w `ARCHITECTURE.md`)
- rozdzielenie logiki walki do `services/combat.py`
