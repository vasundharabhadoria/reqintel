import os
import json

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

token = os.getenv("HF_TOKEN")

if not token:
    raise RuntimeError("HF_TOKEN not found in .env")

client = InferenceClient(token=token)

messages = [
    {
        "role": "system",
        "content": """
You are a software requirements extraction system.

Read the provided document and identify actual software requirements.

Rules:
- Decide whether the document is a software requirements document.
- Extract only requirements supported by the document.
- Do not invent requirements.
- Do not treat resume/project experience statements as software requirements.
- Include functional, non-functional, business-rule, and constraint requirements.
- If the document is not a requirements document, return an empty requirements list.
"""
    },
    {
        "role": "user",
        "content": """
Software Requirements Specification

The system shall allow users to create an account using their email
and password.

The system shall send an email verification link after registration.

The system must lock an account for 10 minutes after five failed
login attempts.

The application should respond to normal user requests within
2 seconds.
"""
    }
]

response = client.chat_completion(
    model="Qwen/Qwen3-32B",
    messages=messages,
    max_tokens=1000,
)

content = response.choices[0].message.content

print(content)
