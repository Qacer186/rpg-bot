import pika
import json
import logging
import os

# Konfiguracja logera dla Workera (Punkt 7 planu)
if not os.path.exists('logs'): os.makedirs('logs')
logging.basicConfig(
    filename='logs/game_events.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

def process_fight_log(ch, method, properties, body):
    data = json.loads(body)
    
    # Logowanie natychmiastowe do pliku (bezpieczeństwo danych)
    log_entry = f"PLAYER_ID: {data['user_id']} | ACTION: {data['action']} | TARGET: {data['monster_name']}"
    logging.info(log_entry)
    print(f" [log] Zapisano zdarzenie dla gracza {data['user_id']}")

    # Możliwość dodania logiki: "update w DB po uzbieraniu większej liczby logów"
    
    ch.basic_ack(delivery_tag=method.delivery_tag)

connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel = connection.channel()
channel.queue_declare(queue='fight_logs')
channel.basic_consume(queue='fight_logs', on_message_callback=process_fight_log)

print(' [*] Worker RPG działa i nasłuchuje kolejki...')
channel.start_consuming()