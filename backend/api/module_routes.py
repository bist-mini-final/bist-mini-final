from typing import Callable, Type

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from pydantic import ValidationError

from ..module_documentation import render_module_markdown
from ..module_registry import ModuleRegistry
from ..modules.base import ModuleExecutionError


def _execution_handler(
    module_registry: ModuleRegistry,
    module_type: str,
    request_model: Type[BaseModel],
) -> Callable[..., object]:
    """Build a statically typed FastAPI handler for one dynamic module class."""

    def execute_module(request):
        try:
            return module_registry.execute(
                module_type,
                request.input,
                request.config,
            )
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail=error.errors(include_url=False),
            ) from error
        except ModuleExecutionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    execute_module.__name__ = f"execute_{module_type}"
    execute_module.__doc__ = (
        "Execute this module independently through its exact Input and Config DTOs."
    )
    execute_module.__annotations__ = {"request": request_model}
    return execute_module


def create_module_router(module_registry: ModuleRegistry) -> APIRouter:
    router = APIRouter(tags=["Modules"])

    for definition in module_registry.definitions():
        module = module_registry.get(definition["type"])
        router.add_api_route(
            f"/modules/{definition['type']}/execute",
            _execution_handler(
                module_registry,
                definition["type"],
                module.request_model,
            ),
            methods=["POST"],
            response_model=module.output_model,
            operation_id=f"execute_module_{definition['type']}",
            summary=f"Execute {definition['label']}",
            description=(
                f"{definition['description']}\n\n"
                "Input DTO and Config DTO are validated independently. "
                "The response is the module's Output DTO JSON."
            ),
        )

    @router.get("/modules", summary="List registered module contracts")
    def get_modules():
        """Return palette metadata and canonical DTO schemas for every module."""

        return {"modules": module_registry.definitions()}

    @router.get("/modules/{module_type}", summary="Get one module contract")
    def get_module(module_type: str):
        """Return exact Input, Config, Output, branch, and execution schemas."""

        try:
            return module_registry.definition(module_type)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get(
        "/modules/{module_type}/docs",
        response_class=PlainTextResponse,
        summary="Read a generated module usage guide",
    )
    def get_module_docs(module_type: str):
        """Render Markdown from the same Pydantic models used for execution."""

        try:
            return render_module_markdown(module_registry.get(module_type))
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return router
