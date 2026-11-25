"""Configuração central do agente.

Todas as chaves e endereços vêm de variáveis de ambiente (arquivo .env),
nunca do código-fonte. O .env fica fora do Git (ver .gitignore).
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Endereço da API de estoque do professor
API_ESTOQUE_URL = os.getenv("API_ESTOQUE_URL", "http://127.0.0.1:8000").rstrip("/")

# Tempo máximo (segundos) de espera por uma resposta HTTP
API_TIMEOUT = float(os.getenv("API_TIMEOUT", "5"))

# Modelo no formato "provedor:modelo", lido pelo init_chat_model do LangChain.
# Padrão: Claude Haiku 5.5 (rápido e barato para desenvolver).
# Para a gravação final, pode usar "anthropic:claude-sonnet-5-5".
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic:claude-haiku-5-5")

# Limite de ciclos agente -> ferramenta. Evita loop infinito.
MAX_PASSOS = int(os.getenv("MAX_PASSOS", "6"))

# Tamanho máximo da pergunta aceita (proteção básica de entrada)
MAX_CARACTERES_PERGUNTA = 500
