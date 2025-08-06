from typing import Any

from pydantic import BaseModel, Field, field_validator


class MacroNutrients(BaseModel):
    protein_g: int = Field(..., ge=0)
    fat_g: int = Field(..., ge=0)
    carbohydrates_g: int = Field(..., ge=0)


class RecipeBase(BaseModel):
    recipe_name: str = Field(..., min_length=1, max_length=255)
    recipe_author: str | None = None
    recipe_book: str | None = None
    page_reference: str | None = None
    servings: int = Field(1, ge=1)
    instructions: str = Field(..., min_length=1)
    ingredients: list[str] = Field(..., min_items=1)
    ingredients_original: list[str] | None = None
    main_protein: list[str] = Field(..., min_items=0)
    calories_per_serving: int = Field(..., ge=0)
    macro_nutrients: MacroNutrients


class RecipeCreate(RecipeBase):
    pass


class RecipeInDB(RecipeBase):
    id: str

    class Config:
        from_attributes = True


class RecipeSearch(BaseModel):
    calories_min: int | None = Field(None, ge=0)
    calories_max: int | None = Field(None, ge=0)
    protein_min: int | None = Field(None, ge=0)
    protein_max: int | None = Field(None, ge=0)
    main_protein: str | None = None
    name: str | None = None
    randomize: bool = False
    limit: int = Field(10, ge=1, le=100)


class RecipeIngestionRequest(BaseModel):
    pdf_content: bytes | None = None
    pdf_path: str | None = None

    @field_validator("pdf_content", "pdf_path")
    def validate_pdf_input(cls, v: Any, values: dict[str, Any]) -> Any:
        if not v and not values.get("pdf_path") and not values.get("pdf_content"):
            raise ValueError("Either pdf_content or pdf_path must be provided")
        return v


class RecipeIngestionResponse(BaseModel):
    success: bool
    recipe: RecipeInDB | None = None
    error: str | None = None