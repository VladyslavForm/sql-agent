import os
from dotenv import load_dotenv

def load_config():
    """Load configuration from environment variables."""
    load_dotenv()
    
    config = {
        'openrouter_api_key': os.getenv('OPENROUTER_API_KEY'),
        'db_host': os.getenv('DB_HOST', 'localhost'),
        'db_port': int(os.getenv('DB_PORT', 5432)),
        'db_name': os.getenv('DB_NAME', 'sql_agent'),
        'db_user': os.getenv('DB_USER'),
        'db_password': os.getenv('DB_PASSWORD'),
        'debug': os.getenv('DEBUG', 'false').lower() == 'true',
        
        # LLM Configuration
        'llm_model': os.getenv('LLM_MODEL', 'anthropic/claude-3.5-sonnet'),
        'llm_timeout': int(os.getenv('LLM_TIMEOUT', 30)),
        'response_language': os.getenv('RESPONSE_LANGUAGE', 'auto'),
        'max_response_length': int(os.getenv('MAX_RESPONSE_LENGTH', 2000))
    }
    
    return config

def validate_config(config):
    """Validate that required configuration is present."""
    required_fields = ['openrouter_api_key', 'db_user', 'db_password']
    missing = [field for field in required_fields if not config.get(field)]
    
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    
    return True