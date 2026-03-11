import os
from dotenv import load_dotenv
load_dotenv()
from google import genai

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
print("=== Models hỗ trợ generateContent ===")
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(m.name)