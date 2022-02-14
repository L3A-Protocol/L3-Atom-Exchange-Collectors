import websockets
import asyncio
import datetime

from .kafka_consumers import async_kafka

# {topic_id: KafkaConsumer}
broadcaster_lock = asyncio.Lock()
topic_broadcasters = {}

# {topic_id: [ClientHandler, ClientHandler ...]}
subscriptions_lock = asyncio.Lock()
client_subscriptions = {}

tasks_lock = asyncio.Lock()
tasks = {}

published_lock = asyncio.Lock()
n_published = 0

async def subscribe(topic_id: str, client):
    async with broadcaster_lock:
        async with subscriptions_lock:
            if topic_id not in topic_broadcasters.keys():
                await create_topic(topic_id)
                client_subscriptions[topic_id] = [client]
            elif client in client_subscriptions[topic_id]:
                print(f"client is already subscribed to {topic_id}")
            else: 
                client_subscriptions[topic_id].append(client)

async def unsubscribe(topic_id: str, client):
    async with broadcaster_lock:
        async with subscriptions_lock:
            if client not in client_subscriptions[topic_id]:
                print(f"client is not subscribed to {topic_id}")
            else:
                client_subscriptions[topic_id].remove(client)
                if len(client_subscriptions[topic_id]) == 0:
                    await remove_topic(topic_id)

async def run_topic(topic_id):
    global n_published
    while not topic_broadcasters[topic_id].closed:
        msg = await topic_broadcasters[topic_id].get()
        subs = client_subscriptions[topic_id]
        sockets = map(lambda client: client.get_ws(), subs)
        websockets.broadcast(sockets, msg)
        async with published_lock:
            n_published += 1

def get_backlog():
    return sum([x.size() for x in topic_broadcasters.values()])

async def create_topic(topic_id):
    consumer = await async_kafka.get_consumer(topic_id)
    if not consumer:
        # This will be replaced by a message parser in the future.
        subscriptions_lock.release()
        broadcaster_lock.release()
        return
    topic_broadcasters[topic_id] = consumer

    task = asyncio.create_task(run_topic(topic_id))
    async with tasks_lock:
        tasks[topic_id] = task

async def remove_topic(topic_id):
    """Precondition: Topic is empty"""
    await async_kafka.shutdown_topic(topic_id)

    del client_subscriptions[topic_id]
    del topic_broadcasters[topic_id]
    async with tasks_lock:
        tasks[topic_id].cancel()
    del tasks[topic_id]

def debug():
    print(f"---------------ts: {datetime.datetime.now()}---------------")
    print(f"Broadcast Backlog: {get_backlog()}")
    print(f"Messages Broadcasted: {n_published}")
    print(f"Broadcasters: {topic_broadcasters}")
    print(f"Subscribers: {client_subscriptions}")
    print(f"--------------------------------------------\n")