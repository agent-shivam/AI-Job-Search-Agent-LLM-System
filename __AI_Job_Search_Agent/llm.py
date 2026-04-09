# import os
# import google.generativeai as genai
# from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# class GeminiLLM:
#     def __init__(self, model="gemini-pro"):
#         self.model = genai.GenerativeModel(model)

#     def invoke(self, messages):
#         formatted_prompt = ""

#         for m in messages:
#             if isinstance(m, HumanMessage):
#                 formatted_prompt += f"User: {m.content}\n"
#             elif isinstance(m, AIMessage):
#                 formatted_prompt += f"Assistant: {m.content}\n"
#             elif isinstance(m, SystemMessage):
#                 formatted_prompt += f"System: {m.content}\n"
#             else:
#                 formatted_prompt += str(m)

#         try:
#             response = self.model.generate_content(formatted_prompt)
#             return AIMessage(content=response.text)

#         except Exception as e:
#             print(f"❌ Gemini error: {e}")
#             return AIMessage(content="")


# import requests
# from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# class OllamaLLM:
#     def __init__(self, model="llama3"):
#         self.model = model
#         self.url = "http://localhost:11434/api/generate"

#     def invoke(self, messages):
#         prompt = ""

#         for m in messages:
#             if isinstance(m, HumanMessage):
#                 prompt += f"User: {m.content}\n"
#             elif isinstance(m, AIMessage):
#                 prompt += f"Assistant: {m.content}\n"
#             elif isinstance(m, SystemMessage):
#                 prompt += f"System: {m.content}\n"
#             else:
#                 prompt += str(m)

#         try:
#             response = requests.post(
#                 self.url,
#                 json={
#                     "model": self.model,
#                     "prompt": prompt,
#                     "stream": False
#                 }
#             )

#             result = response.json()

#             return AIMessage(
#                 content=result.get("response", "")
#             )

#         except Exception as e:
#             print(f"❌ Ollama error: {e}")
#             return AIMessage(content="")
        





import os
from groq import Groq
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

class GroqLLM:
    def __init__(self, model="meta-llama/llama-prompt-guard-2-86m"):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = model

    

    def invoke(self, messages):
        formatted_messages = []

        for m in messages:
            if isinstance(m, HumanMessage):
                formatted_messages.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                formatted_messages.append({"role": "assistant", "content": m.content})
            elif isinstance(m, SystemMessage):
                formatted_messages.append({"role": "system", "content": m.content})
            else:
                formatted_messages.append({"role": "user", "content": str(m)})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=formatted_messages
            )

            return AIMessage(content=response.choices[0].message.content)

        except Exception as e:
            print(f"❌ Groq error: {e}")
            return AIMessage(content="")
        











import os
import requests
from dotenv import load_dotenv

load_dotenv()

class OpenRouterLLM:
    def __init__(self, model=None):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def invoke(self, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
        }

        try:
            res = requests.post(self.url, headers=headers, json=payload, timeout=30)
            res.raise_for_status()
            data = res.json()

            content = data["choices"][0]["message"]["content"]

            # mimic LangChain style
            return type("AIMessage", (), {"content": content})()

        except Exception as e:
            print(f"❌ OpenRouter error: {e}")
            return type("AIMessage", (), {"content": ""})()