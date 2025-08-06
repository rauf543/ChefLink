import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base


class UserRole(str, enum.Enum):
    FAMILY_MEMBER = "family_member"
    CHEF = "chef"


class MealType(str, enum.Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class MealPlanStatus(str, enum.Enum):
    UNLOCKED = "unlocked"
    LOCKED = "locked"


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipe_name = Column(String(255), nullable=False, index=True)
    recipe_author = Column(String(255), nullable=True)
    recipe_book = Column(String(255), nullable=True)
    page_reference = Column(String(500), nullable=True)
    servings = Column(Integer, nullable=False, default=1)
    instructions = Column(Text, nullable=False)
    ingredients = Column(JSON, nullable=False)  # List of single-serving amounts
    ingredients_original = Column(JSON, nullable=True)  # Original amounts
    main_protein = Column(JSON, nullable=False)  # List of proteins
    calories_per_serving = Column(Integer, nullable=False)
    macro_nutrients = Column(JSON, nullable=False)  # {protein_g, fat_g, carbohydrates_g}
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meal_plans = relationship("MealPlan", back_populates="recipe")

    # Unique constraint to prevent duplicates
    __table_args__ = (
        UniqueConstraint("recipe_name", "recipe_book", "recipe_author", name="uq_recipe_identity"),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    dietary_preferences = Column(JSON, nullable=True, default=dict)
    invitation_code = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    meal_plans = relationship("MealPlan", back_populates="user")


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    meal_type = Column(Enum(MealType), nullable=False)
    recipe_id = Column(UUID(as_uuid=True), ForeignKey("recipes.id"), nullable=False)
    servings = Column(Integer, nullable=False, default=1)
    status = Column(Enum(MealPlanStatus), nullable=False, default=MealPlanStatus.UNLOCKED)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="meal_plans")
    recipe = relationship("Recipe", back_populates="meal_plans")

    # Unique constraint to prevent duplicate meals
    __table_args__ = (
        UniqueConstraint("user_id", "date", "meal_type", name="uq_user_date_meal"),
    )