import asyncio
import os
import traceback
from app import process_chat

async def main():
    messages = [
        {"role": "system", "content": "You are a highly skilled SRE assistant."},
        {"role": "user", "content": "hi"}
    ]
    try:
        result = await process_chat(messages)
        print("Success:", result)
    except Exception as e:
        print("FAILED WITH EXCEPTION:")
        traceback.print_exc()
        if hasattr(e, 'exceptions'):
            for i, sub_e in enumerate(e.exceptions):
                print(f"Sub-exception {i}:")
                traceback.print_exception(type(sub_e), sub_e, sub_e.__traceback__)

if __name__ == "__main__":
    asyncio.run(main())
