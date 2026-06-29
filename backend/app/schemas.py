from pydantic import BaseModel
from typing import Optional


class IngredientOut(BaseModel):
    id: int
    raw_text: str
    ingredient_name: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    note: Optional[str] = None

    class Config:
        from_attributes = True


class RecipeOut(BaseModel):
    id: int
    cookidoo_id: str
    name: str
    url: Optional[str] = None
    image_url: Optional[str] = None
    language: Optional[str] = None
    total_time: Optional[str] = None
    prep_time: Optional[str] = None
    yield_amount: Optional[str] = None
    difficulty: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    categories: Optional[list] = None
    calories: Optional[str] = None
    ingredients: list[IngredientOut] = []

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    recipe: RecipeOut
    match_score: float
    missing_ingredients: list[str]
    total_ingredients: int
    matched_ingredients: int


class SearchRequest(BaseModel):
    ingredients: list[str]
    max_missing: int = 3
    language: Optional[str] = None
    country: Optional[str] = None
    limit: int = 20
