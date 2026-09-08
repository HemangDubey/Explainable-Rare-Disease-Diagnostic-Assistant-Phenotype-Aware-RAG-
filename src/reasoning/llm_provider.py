import abc
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BaseLLMProvider(abc.ABC):
    """Abstract base class for LLM providers."""
    @abc.abstractmethod
    def generate_json(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    def check_health(self) -> Dict[str, Any]:
        pass

class OllamaProvider(BaseLLMProvider):
    """
    Ollama LLM Provider.
    Interfaces with local Ollama daemon at base_url (default: http://127.0.0.1:11434).
    """
    def __init__(
        self,
        model: str = "mistral:latest",
        base_url: str = "http://127.0.0.1:11434",
        temperature: float = 0.1,
        max_tokens: int = 2000,
        timeout: int = 60
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def check_health(self) -> Dict[str, Any]:
        """Checks if Ollama is running and whether the configured model is installed."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    installed_models = [m.get("name") for m in data.get("models", [])]
                    model_found = self.model in installed_models or any(m.startswith(self.model.split(":")[0]) for m in installed_models)
                    return {
                        "status": "healthy" if model_found else "model_missing",
                        "ollama_running": True,
                        "model_found": model_found,
                        "configured_model": self.model,
                        "installed_models": installed_models,
                        "pull_command": f"ollama pull {self.model}" if not model_found else None
                    }
        except Exception as e:
            return {
                "status": "offline",
                "ollama_running": False,
                "model_found": False,
                "configured_model": self.model,
                "error": str(e),
                "instructions": "Ensure Ollama is running (`ollama serve`)."
            }

    def generate_json(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """Sends request to Ollama with format='json'."""
        endpoint = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_bytes,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                raw_response = res_json.get("response", "{}")
                
                # Parse the internal json response
                try:
                    parsed = json.loads(raw_response)
                    return parsed
                except json.JSONDecodeError:
                    # Attempt simple fallback extraction of JSON substring
                    start = raw_response.find("{")
                    end = raw_response.rfind("}")
                    if start != -1 and end != -1:
                        return json.loads(raw_response[start:end+1])
                    raise ValueError(f"Ollama response could not be parsed as JSON: {raw_response[:200]}")
        except urllib.error.URLError as e:
            logger.error(f"Ollama connection error: {e}")
            raise ConnectionError(f"Could not connect to Ollama at {self.base_url}: {e}")
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise RuntimeError(f"Ollama generation failed: {e}")

def get_llm_provider(config: Dict[str, Any]) -> BaseLLMProvider:
    """Factory function for LLM provider."""
    llm_cfg = config.get("llm", {})
    provider_name = llm_cfg.get("provider", "ollama").lower()

    if provider_name == "ollama":
        return OllamaProvider(
            model=llm_cfg.get("model", "mistral:latest"),
            base_url=llm_cfg.get("base_url", "http://localhost:11434"),
            temperature=float(llm_cfg.get("temperature", 0.1)),
            max_tokens=int(llm_cfg.get("max_tokens", 2000)),
            timeout=int(llm_cfg.get("timeout", 60))
        )
    else:
        raise ValueError(f"Unsupported LLM provider '{provider_name}'. Phase 4 supports local Ollama.")
