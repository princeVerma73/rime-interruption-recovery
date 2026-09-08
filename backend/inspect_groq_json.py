import sys
sys.path.insert(0, '.')
import asyncio
import httpx
import os
import json
from dotenv import load_dotenv
load_dotenv('backend/.env')
from backend.app.services.tavily_search import TavilySearchService
from backend.app.services.llm import format_search_context, VOICE_SYSTEM_PROMPT

async def test():
    tav = TavilySearchService()
    search_res = await tav.search('What is the latest AI news?')
    ctx = format_search_context('What is the latest AI news?', search_res.results)
    sys_prompt = f"{VOICE_SYSTEM_PROMPT}\n\n{ctx}"
    messages = [{'role': 'system', 'content': sys_prompt}, {'role': 'user', 'content': 'What is the latest AI news?'}]
    headers = {'Authorization': f'Bearer {os.getenv("GROQ_API_KEY")}', 'Content-Type': 'application/json'}
    body = {'model': 'openai/gpt-oss-20b', 'messages': messages, 'max_tokens': 500, 'temperature': 0.7}
    async with httpx.AsyncClient() as client:
        r = await client.post('https://api.groq.com/openai/v1/chat/completions', headers=headers, json=body)
        print('STATUS:', r.status_code)
        try:
            with open('groq_out.json', 'w', encoding='utf-8') as f:
                f.write(json.dumps(r.json(), indent=2))
            print("Saved groq_out.json")
        except Exception as e:
            print("Err saving json:", e)

asyncio.run(test())
