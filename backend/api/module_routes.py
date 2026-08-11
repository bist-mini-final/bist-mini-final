from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from ..module_registry import ModuleRegistry
from ..modules.base import ModuleExecutionError


def create_module_router(module_registry: ModuleRegistry) -> APIRouter:
    router = APIRouter()

    @router.get("/modules")
    def get_modules():
        return {"modules": module_registry.definitions()}

    @router.get("/modules/{module_type}")
    def get_module(module_type: str):
        try:
            return module_registry.definition(module_type)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/modules/{module_type}/execute")
    def execute_module(
        module_type: str,
        payload: Any = Body(...),
    ):
        try:
            return module_registry.execute(module_type, payload)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=error.errors(include_url=False),
            ) from error
        except ModuleExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
