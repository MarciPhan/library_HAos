import asyncio
import aiohttp

async def main():
    isbn = "9788090024069"
    async with aiohttp.ClientSession() as session:
        url = f"https://www.knihovny.cz/api/v1/search?lookfor={isbn}&type=ISN"
        async with session.get(url, timeout=10) as resp:
            data = await resp.json()
            print(data)

asyncio.run(main())
