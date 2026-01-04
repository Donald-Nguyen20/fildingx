# llm_client.py
import requests

class LLMClient:
    def __init__(self, model: str = "llama3.2:3b", host: str = "http://localhost:11434"):
        self.model = model
        self.url_generate = f"{host}/api/generate"

    def generate(self, prompt: str) -> str:
        """
        Gọi Ollama để sinh câu trả lời.
        - stream=False để nhận 1 lần (dễ tích hợp UI).
        """
        r = requests.post(
            self.url_generate,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                # Tuỳ chọn:
                "options": {
                    "temperature": 0.2,
                    "num_predict": 512
                }
            },
            timeout=280
        )
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip()
