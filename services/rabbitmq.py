import pika
import json

def send_to_queue(queue_name, data):
    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name)
    
    channel.basic_publish(exchange='',
                          routing_key=queue_name,
                          body=json.dumps(data))
    connection.close()