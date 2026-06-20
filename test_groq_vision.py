import os
import base64
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

load_dotenv()

def test_groq_vision():
    # create a dummy tiny 1x1 png image
    img_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    
    print("Testing Groq Vision...")
    try:
        llm = ChatGroq(model="llama-3.2-11b-vision-preview", groq_api_key=os.getenv("GROQ_API_KEY"), temperature=0)
        msg = HumanMessage(
            content=[
                {"type": "text", "text": "Describe this image in one word."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]
        )
        res = llm.invoke([msg])
        print("Success:", res.content)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_groq_vision()
