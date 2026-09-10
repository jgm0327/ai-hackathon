"""공용 환경변수 로더. 모든 트랙은 이 모듈을 통해서만 설정값에 접근한다."""
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    notion_token: str = os.getenv("NOTION_TOKEN", "")
    notion_mcp_server_url: str = os.getenv("NOTION_MCP_SERVER_URL", "")
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "./.chroma")
    mock_jd_dir: str = os.getenv("MOCK_JD_DIR", "data/mock_jds")


settings = Settings()
