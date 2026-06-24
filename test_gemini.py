from google import genai
from dotenv import load_dotenv
import os

load_dotenv()

print("KEY FOUND:", bool(os.getenv("GEMINI_API_KEY")))

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say hello"
    )

    print("SUCCESS:")
    print(response.text)

except Exception as e:
    print("ERROR:")
    print(type(e))
    print(e)