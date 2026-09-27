"""Shared, frozen-safe HTTP server configuration."""

import uvicorn
from fastapi import FastAPI


def uvicorn_config(app: FastAPI, port: int) -> uvicorn.Config:
    return uvicorn.Config(
        app, host="127.0.0.1", port=port, loop="asyncio", http="h11", ws="none", lifespan="on"
    )
