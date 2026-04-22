import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    delta_api_key: str
    delta_api_secret: str
    finnhub_api_key: str
    runpod_api_key: str
    runpod_endpoint_id: str
    vps_webhook_url: str
    telegram_bot_token: str
    telegram_chat_id: str
    resend_api_key: str
    resend_from_email: str
    resend_to_email: str
    supabase_url: str
    supabase_service_key: str
    ollama_base_url: str
    ollama_fast_model: str
    complexity_threshold: int
    runpod_daily_budget_usd: float
    paper_mode: bool


def load_config() -> Config:
    def req(key: str) -> str:
        val = os.getenv(key)
        if not val:
            raise RuntimeError(f"Missing required env var: {key}")
        return val

    return Config(
        delta_api_key=req("DELTA_EXCHANGE_API_KEY"),
        delta_api_secret=req("DELTA_EXCHANGE_API_SECRET"),
        finnhub_api_key=req("FINNHUB_API_KEY"),
        runpod_api_key=req("RUNPOD_API_KEY"),
        runpod_endpoint_id=req("RUNPOD_ENDPOINT_ID"),
        vps_webhook_url=req("VPS_WEBHOOK_URL"),
        telegram_bot_token=req("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=req("TELEGRAM_CHAT_ID"),
        resend_api_key=req("RESEND_API_KEY"),
        resend_from_email=req("RESEND_FROM_EMAIL"),
        resend_to_email=os.getenv("RESEND_TO_EMAIL", "nikhil2050thakur2001@gmail.com"),
        supabase_url=req("SUPABASE_URL"),
        supabase_service_key=req("SUPABASE_SERVICE_KEY"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_fast_model=os.getenv("OLLAMA_FAST_MODEL", "qwen2.5:1.5b"),
        complexity_threshold=int(os.getenv("COMPLEXITY_THRESHOLD", "6")),
        runpod_daily_budget_usd=float(os.getenv("RUNPOD_DAILY_BUDGET_USD", "2.0")),
        paper_mode=os.getenv("PAPER_MODE", "true").lower() == "true",
    )
