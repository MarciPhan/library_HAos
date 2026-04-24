import asyncio
import aiohttp
import re

async def main():
    isbn = "9788090024069"
    async with aiohttp.ClientSession() as session:
        url = f"https://www.obalkyknih.cz/view?isbn={isbn}"
        async with session.get(url, timeout=10) as resp:
            print("Status:", resp.status)
            text = await resp.text()
            match = re.search(r'<link\s+rel=["\']previewimage["\']\s+href=["\']([^"\']+)["\']', text, re.IGNORECASE)
            print("Cover:", match.group(1) if match else "None")

asyncio.run(main())
