from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    fhir_base_url: str
    fhir_auth_token: str = ""

    # Azure AI Foundry — project endpoint + API key from the Foundry portal home page
    azure_project_endpoint: str
    azure_api_key: str
    # Agent ID created in the Foundry portal (Agents tab) with Foundry IQ attached
    azure_agent_id: str

    allowed_origins: str = "http://localhost:5173"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
