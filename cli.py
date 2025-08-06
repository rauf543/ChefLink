#!/usr/bin/env python3
import asyncio
from pathlib import Path

import typer
from rich import print
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import AsyncSessionLocal
from app.services.pdf.processor import PDFProcessor
from app.services.recipe_service import RecipeService

app = typer.Typer(help="ChefLink Developer CLI")
console = Console()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


@app.command(name="ingest")
def ingest_recipe(
    pdf_path: Path = typer.Argument(..., help="Path to PDF file"),
    book: bool = typer.Option(False, "--book", "-b", help="Ingest as recipe book"),
    book_title: str = typer.Option(None, "--title", "-t", help="Recipe book title"),
):
    """Ingest a single recipe or recipe book from PDF."""
    asyncio.run(_ingest_recipe(pdf_path, book, book_title))


async def _ingest_recipe(pdf_path: Path, is_book: bool, book_title: str | None):
    if not pdf_path.exists():
        console.print(f"[red]Error: File not found: {pdf_path}[/red]")
        raise typer.Exit(1)
        
    if not pdf_path.suffix.lower() == '.pdf':
        console.print(f"[red]Error: File must be a PDF: {pdf_path}[/red]")
        raise typer.Exit(1)

    try:
        # Read PDF content
        pdf_content = PDFProcessor.read_pdf_file(str(pdf_path))
        
        async for db in get_db():
            recipe_service = RecipeService(db)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                
                if is_book:
                    if not book_title:
                        book_title = pdf_path.stem  # Use filename as default title
                        
                    task = progress.add_task(
                        f"[cyan]Ingesting recipe book: {book_title}...", 
                        total=None
                    )
                    
                    recipes = await recipe_service.ingest_recipe_book(pdf_content, book_title)
                    progress.remove_task(task)
                    
                    # Display results
                    console.print(f"\n[green]Successfully ingested {len(recipes)} recipes from {book_title}[/green]\n")
                    
                    table = Table(title="Ingested Recipes")
                    table.add_column("Recipe Name", style="cyan")
                    table.add_column("Page", style="magenta")
                    table.add_column("Calories", style="green")
                    
                    for recipe in recipes:
                        table.add_row(
                            recipe.recipe_name,
                            recipe.page_reference or "N/A",
                            str(recipe.calories_per_serving)
                        )
                        
                    console.print(table)
                    
                else:
                    task = progress.add_task(
                        "[cyan]Extracting recipe from PDF...", 
                        total=None
                    )
                    
                    recipe = await recipe_service.ingest_single_recipe(pdf_content)
                    progress.remove_task(task)
                    
                    # Display result
                    console.print(f"\n[green]Successfully ingested recipe: {recipe.recipe_name}[/green]\n")
                    
                    # Recipe details
                    console.print(f"[bold]Author:[/bold] {recipe.recipe_author or 'Unknown'}")
                    console.print(f"[bold]Servings:[/bold] {recipe.servings}")
                    console.print(f"[bold]Calories per serving:[/bold] {recipe.calories_per_serving}")
                    console.print(f"[bold]Macros:[/bold] {recipe.macro_nutrients['protein_g']}g protein, "
                                f"{recipe.macro_nutrients['fat_g']}g fat, "
                                f"{recipe.macro_nutrients['carbohydrates_g']}g carbs")
                    console.print(f"\n[bold]Main proteins:[/bold] {', '.join(recipe.main_protein) or 'None'}")
                    console.print(f"\n[bold]Ingredients:[/bold]")
                    for ingredient in recipe.ingredients:
                        console.print(f"  • {ingredient}")
                        
    except ValueError as e:
        console.print(f"[red]Validation error: {str(e)}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command(name="list")
def list_recipes(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of recipes to show"),
    search: str = typer.Option(None, "--search", "-s", help="Search recipe names"),
):
    """List all recipes in the database."""
    asyncio.run(_list_recipes(limit, search))


async def _list_recipes(limit: int, search: str | None):
    try:
        async for db in get_db():
            from sqlalchemy import select
            from app.database.models import Recipe
            
            query = select(Recipe).order_by(Recipe.recipe_name).limit(limit)
            
            if search:
                query = query.where(Recipe.recipe_name.ilike(f"%{search}%"))
                
            result = await db.execute(query)
            recipes = result.scalars().all()
            
            if not recipes:
                console.print("[yellow]No recipes found[/yellow]")
                return
                
            table = Table(title=f"Recipes ({len(recipes)} shown)")
            table.add_column("ID", style="dim")
            table.add_column("Name", style="cyan")
            table.add_column("Book", style="magenta")
            table.add_column("Calories", style="green")
            table.add_column("Protein", style="yellow")
            
            for recipe in recipes:
                table.add_row(
                    str(recipe.id)[:8],
                    recipe.recipe_name,
                    recipe.recipe_book or "—",
                    str(recipe.calories_per_serving),
                    f"{recipe.macro_nutrients['protein_g']}g"
                )
                
            console.print(table)
            
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


@app.command(name="stats")
def show_stats():
    """Show database statistics."""
    asyncio.run(_show_stats())


async def _show_stats():
    try:
        async for db in get_db():
            from sqlalchemy import func, select
            from app.database.models import Recipe, User, MealPlan
            
            # Get counts
            recipe_count = await db.scalar(select(func.count(Recipe.id)))
            user_count = await db.scalar(select(func.count(User.id)))
            meal_plan_count = await db.scalar(select(func.count(MealPlan.id)))
            
            # Get unique books
            book_result = await db.execute(
                select(Recipe.recipe_book).distinct().where(Recipe.recipe_book.isnot(None))
            )
            books = book_result.scalars().all()
            
            console.print("\n[bold cyan]ChefLink Database Statistics[/bold cyan]\n")
            console.print(f"[bold]Total Recipes:[/bold] {recipe_count}")
            console.print(f"[bold]Total Users:[/bold] {user_count}")
            console.print(f"[bold]Total Meal Plans:[/bold] {meal_plan_count}")
            console.print(f"[bold]Recipe Books:[/bold] {len(books)}")
            
            if books:
                console.print("\n[bold]Books in database:[/bold]")
                for book in books[:10]:  # Show first 10
                    console.print(f"  • {book}")
                if len(books) > 10:
                    console.print(f"  ... and {len(books) - 10} more")
                    
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()