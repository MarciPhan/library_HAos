import asyncio
import aiohttp

async def main():
    isbn = "9788090024069"
    async with aiohttp.ClientSession() as session:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        async with session.get(url, timeout=10) as resp:
            data = await resp.json()
            print(data)

asyncio.run(main())
