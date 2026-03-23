import aiohttp
import random

API_URL = "https://www.dnd5eapi.co/api/monsters"

async def get_random_monster():
    async with aiohttp.ClientSession() as session:
        # 1. Pobieramy listę wszystkich potworów
        async with session.get(API_URL) as response:
            if response.status != 200:
                return None
            data = await response.json()
            all_monsters = data['results']
            
        # 2. Losujemy jednego potwora z listy
        random_monster = random.choice(all_monsters)
        
        # 3. Pobieramy szczegóły wybranego potwora
        async with session.get(f"https://www.dnd5eapi.co{random_monster['url']}") as response:
            if response.status != 200:
                return None
            details = await response.json()
            
            # Mapujemy dane z API na nasz system walki
            return {
                "name": details.get("name", "Nieznany Potwór"),
                "hp": details.get("hit_points", 50),
                "attack": details.get("strength", 10),
                "gold": random.randint(10, 30), # API nie ma złota, więc losujemy
                "image": f"https://www.dnd5eapi.co{details.get('image', '')}" if details.get('image') else None
            }