import asyncio
import aiohttp
import re

async def main():
    isbn = "9788090024069"
    async with aiohttp.ClientSession() as session:
        url = f"https://www.obalkyknih.cz/view?isbn={isbn}"
        async with session.get(url, timeout=10) as resp:
            text = await resp.text()
            print("Response:", resp.status)
            match = re.search(r'<link\s+rel=["\']previewimage["\']\s+href=["\']([^"\']+)["\']', text, re.IGNORECASE)
            print("Match:", match.group(1) if match else "None")
            
            # Also test the regex with single quotes if any
            match2 = re.search(r'<link\s+rel=previewimage\s+href=([^>\s]+)', text, re.IGNORECASE)
            print("Match2:", match2.group(1) if match2 else "None")

asyncio.run(main())
