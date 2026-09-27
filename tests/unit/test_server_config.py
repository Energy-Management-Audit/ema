from fastapi import FastAPI

from ema.cli.server import uvicorn_config


def test_frozen_server_uses_one_explicit_configuration() -> None:
    app = FastAPI()
    config = uvicorn_config(app, 8799)
    assert config.app is app
    assert config.host == "127.0.0.1"
    assert config.port == 8799
    assert config.loop == "asyncio"
    assert config.http == "h11"
    assert config.ws == "none"
    assert config.lifespan == "on"
