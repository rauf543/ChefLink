"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2025-08-05 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('telegram_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('FAMILY_MEMBER', 'CHEF', name='userrole'), nullable=False),
        sa.Column('dietary_preferences', sa.JSON(), nullable=True),
        sa.Column('invitation_code', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id')
    )
    
    # Create recipes table
    op.create_table('recipes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recipe_name', sa.String(length=255), nullable=False),
        sa.Column('recipe_author', sa.String(length=255), nullable=True),
        sa.Column('recipe_book', sa.String(length=255), nullable=True),
        sa.Column('page_reference', sa.String(length=500), nullable=True),
        sa.Column('servings', sa.Integer(), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('ingredients', sa.JSON(), nullable=False),
        sa.Column('ingredients_original', sa.JSON(), nullable=True),
        sa.Column('main_protein', sa.JSON(), nullable=False),
        sa.Column('calories_per_serving', sa.Integer(), nullable=False),
        sa.Column('macro_nutrients', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recipes_recipe_name'), 'recipes', ['recipe_name'], unique=False)
    
    # Create meal_plans table
    op.create_table('meal_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('recipe_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('meal_type', sa.Enum('BREAKFAST', 'LUNCH', 'DINNER', 'SNACK', name='mealtype'), nullable=False),
        sa.Column('servings', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('UNLOCKED', 'LOCKED', name='mealplanstatus'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['recipe_id'], ['recipes.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_meal_plans_date'), 'meal_plans', ['date'], unique=False)
    op.create_index(op.f('ix_meal_plans_user_id'), 'meal_plans', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_meal_plans_user_id'), table_name='meal_plans')
    op.drop_index(op.f('ix_meal_plans_date'), table_name='meal_plans')
    op.drop_table('meal_plans')
    op.drop_index(op.f('ix_recipes_recipe_name'), table_name='recipes')
    op.drop_table('recipes')
    op.drop_table('users')
    op.execute('DROP TYPE userrole')
    op.execute('DROP TYPE mealtype')
    op.execute('DROP TYPE mealplanstatus')