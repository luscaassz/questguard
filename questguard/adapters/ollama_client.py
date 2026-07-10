from __future__ import annotations

from typing import Any

import requests

from questguard.ports.llm import LLMClient


class OllamaClient(LLMClient):
    def __init__(
        self,
        url: str,
        timeout_seconds: int = 360,
        max_output_tokens: int = 4096,
        seed: int | None = None,
    ) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens

        # Seed-base da execução.
        self.seed = seed

        # Contador usado para produzir uma seed diferente em cada chamada.
        self._request_index = 0

    def set_seed(self, seed: int | None) -> None:
        """
        Define a seed-base da execução e reinicia o contador de chamadas.
        """
        self.seed = seed
        self._request_index = 0

    def _next_request_seed(self) -> int | None:
        """
        Produz uma seed determinística diferente para cada requisição.

        Exemplo, com seed-base 100:
        chamada 1 -> 100
        chamada 2 -> 101
        chamada 3 -> 102
        """
        if self.seed is None:
            return None

        request_seed = self.seed + self._request_index
        self._request_index += 1

        # Mantém a seed dentro do intervalo de inteiro positivo de 32 bits.
        return request_seed % 2_147_483_647

    def generate_text(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        top_p: float,
        json_mode: bool = True,
    ) -> str:
        request_seed = self._next_request_seed()

        options: dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": self.max_output_tokens,
        }

        if request_seed is not None:
            options["seed"] = request_seed

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }

        if json_mode:
            payload["format"] = "json"

        try:
            response = requests.post(
                self.url,
                json=payload,
                timeout=(10, self.timeout_seconds),
            )
        except requests.Timeout as error:
            raise TimeoutError(
                "O Ollama excedeu o limite de "
                f"{self.timeout_seconds} segundos."
            ) from error
        except requests.ConnectionError as error:
            raise ConnectionError(
                f"Não foi possível conectar ao Ollama em {self.url}."
            ) from error

        if response.status_code != 200:
            raise RuntimeError(
                f"Falha no Ollama ({response.status_code}): "
                f"{response.text[:1000]}"
            )

        try:
            data = response.json()
        except requests.JSONDecodeError as error:
            raise ValueError(
                "O servidor Ollama não retornou uma resposta HTTP JSON válida."
            ) from error

        raw = data.get("response", "")
        done = data.get("done", False)
        done_reason = data.get("done_reason", "")
        eval_count = data.get("eval_count", 0)

        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                "O Ollama retornou uma resposta vazia."
            )

        if not done:
            raise RuntimeError(
                "O Ollama encerrou a requisição sem indicar conclusão."
            )

        # Quando o limite de saída é atingido, devolve o conteúdo parcial.
        # O QuestGenerationService tentará recuperar as quests completas
        # presentes na resposta e solicitar apenas as que ainda faltam.
        if done_reason == "length":
            print(
                "[Ollama] Aviso: resposta truncada após "
                f"{eval_count} tokens. O serviço tentará recuperar "
                "os objetos completos e complementar o batch."
            )
            return raw.strip()

        return raw.strip()