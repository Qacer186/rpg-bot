import aio_pika
import json
import logging
import os
import asyncio
import sys
import time

# Dodaj główny katalog projektu do sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database.db import update_user_after_fight, get_user, update_user

# Konfiguracja logera dla Workera (Punkt 7 planu)
if not os.path.exists('logs'): os.makedirs('logs')
logging.basicConfig(
    filename='logs/game_events.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Konfiguracja logera dla Workera (Punkt 7 planu)
if not os.path.exists('logs'): os.makedirs('logs')
logging.basicConfig(
    filename='logs/game_events.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

async def process_fight_log(message: aio_pika.IncomingMessage):
    async with message.process():
        data = json.loads(message.body.decode())
        
        # Logowanie natychmiastowe do pliku (bezpieczeństwo danych)
        log_entry = f"PLAYER_ID: {data['user_id']} | ACTION: {data['action']} | TARGET: {data['monster_name']}"
        logging.info(log_entry)
        print(f" [log] Zapisano zdarzenie dla gracza {data['user_id']}")

async def process_quest_selection(message: aio_pika.IncomingMessage):
    async with message.process():
        data = json.loads(message.body.decode())
        
        user_id = data['user_id']
        duration_minutes = data['duration_minutes']
        gold_reward = data['gold_reward']
        exp_reward = data['exp_reward']
        
        # Ustaw on_expedition = 1 i czas rozpoczęcia
        await update_user(user_id, on_expedition=1, expedition_start_time=time.time(), expedition_duration=duration_minutes)
        
        # Czekaj czas misji
        await asyncio.sleep(duration_minutes * 60)  # minuty na sekundy
        
        # Po zakończeniu, odblokuj misję (nagrody przyznawane przez walkę)
        user = await get_user(user_id)
        if user:
            await update_user(user_id, on_expedition=0, expedition_start_time=0, expedition_duration=0)
        
        log_entry = f"QUEST_COMPLETED: {user_id} | Quest finished, rewards handled by fight"
        logging.info(log_entry)
        print(f" [quest] Misja zakończona dla gracza {user_id}")

async def main():
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    
    async with connection:
        channel = await connection.channel()
        
        # Kolejka dla fight_logs
        await channel.declare_queue('fight_logs')
        await channel.set_qos(prefetch_count=1)
        fight_queue = await channel.get_queue('fight_logs')
        await fight_queue.consume(process_fight_log)
        
        # Kolejka dla quest_selections
        await channel.declare_queue('quest_selections')
        quest_queue = await channel.get_queue('quest_selections')
        await quest_queue.consume(process_quest_selection)
        
        print(' [*] Worker RPG działa i nasłuchuje kolejek...')
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())