import pytest
from database.db import init_db, create_user, get_user

@pytest.mark.asyncio
async def test_user_creation():
    await init_db()
    await create_user("test_123")
    user = await get_user("test_123")
    assert user['discord_id'] == "test_123"
    assert user['gold'] == 50 # Sprawdzenie czy użytkownik dostał startowego golda