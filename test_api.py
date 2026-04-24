import asyncio
from custom_components.bookcase.api import fetch_book_metadata
class MockHass: pass

async def main():
    result = await fetch_book_metadata(MockHass(), '9788090024069')
    print("COVER URL:", result.get("cover_url"))

asyncio.run(main())
