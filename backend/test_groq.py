import os

from dotenv import load_dotenv

from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_AI_API_KEY")

if not api_key:
    raise ValueError("GROQ_AI_API_KEY not found in .env")

client = Groq(api_key=api_key)

response = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {
            "role": "user",
            "content": "Explain what a software requirement is in one sentence."
        }
    ],
    temperature=0,
    max_completion_tokens=100
)

print(response.choices[0].message.content)