from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import relationship
from app.database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True)
    cookidoo_id = Column(String, unique=True, index=True)
    name = Column(String)
    url = Column(String)
    image_url = Column(String)
    language = Column(String)
    country = Column(String)
    total_time = Column(String)
    prep_time = Column(String)
    cook_time = Column(String)
    yield_amount = Column(String)
    difficulty = Column(String)
    rating = Column(Float)
    review_count = Column(Integer)
    categories = Column(JSON)
    calories = Column(String)
    carbs = Column(String)
    fat = Column(String)
    protein = Column(String)
    fiber = Column(String)
    raw_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"))
    raw_text = Column(String)
    ingredient_name = Column(String, index=True)
    quantity = Column(Float)
    unit = Column(String)
    note = Column(String)
    is_alternative = Column(Integer, default=0)

    recipe = relationship("Recipe", back_populates="ingredients")
