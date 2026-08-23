from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.cli.documentation.module_docs import render_module_markdown
from backend.engine.runtime.registry import ModuleRegistry


def create_module_router(module_registry: ModuleRegistry) -> APIRouter:
    router = APIRouter(tags=["Modules"])

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
