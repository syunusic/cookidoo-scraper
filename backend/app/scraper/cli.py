import asyncio
import click

from app.database import init_db
from app.scraper.cookidoo import scrape_recipes, scrape_single_recipe


@click.group()
def cli():
    """Cookidoo Recipe Scraper"""
    pass


@cli.command()
@click.option("--languages", "-l", default="es-ES", help="Comma-separated language codes")
@click.option("--limit", "-n", default=0, type=int, help="Max recipes to scrape (0 = unlimited)")
def scrape(languages, limit):
    """Scrape recipes from Cookidoo (public pages)"""
    asyncio.run(_scrape(languages.split(","), limit))


@cli.command()
@click.argument("recipe_id")
@click.option("--lang", default="es-ES", help="Language code")
def recipe(recipe_id, lang):
    """Scrape a single recipe by ID"""
    asyncio.run(_scrape_single(recipe_id, lang))


@cli.command()
@click.option("--email", "-e", prompt="Cookidoo email", help="Your Cookidoo email")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Your Cookidoo password")
@click.option("--limit", "-n", default=0, type=int, help="Max recipes to scrape (0 = unlimited)")
def login_and_scrape(email, password, limit):
    """Login to Cookidoo and scrape recipes (full access)"""
    asyncio.run(_login_scrape(email, password, limit))


@cli.command()
@click.option("--email", "-e", prompt="Cookidoo email", help="Your Cookidoo email")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Your Cookidoo password")
def login(email, password):
    """Login to Cookidoo and save cookies"""
    from app.scraper.playwright_auth import login
    cookies = login(email, password)
    if cookies:
        click.echo(f"Login successful! {len(cookies)} cookies saved.")
    else:
        click.echo("Login failed.")


async def _scrape(languages, limit):
    await init_db()
    click.echo(f"Scraping recipes for languages: {languages}")
    count = await scrape_recipes(languages, limit)
    click.echo(f"Done! Scraped {count} recipes.")


async def _scrape_single(recipe_id, lang):
    await init_db()
    click.echo(f"Scraping recipe r{recipe_id} ({lang})...")
    success = await scrape_single_recipe(recipe_id, lang)
    if success:
        click.echo("Recipe saved!")
    else:
        click.echo("Failed to scrape recipe.")


async def _login_scrape(email, password, limit):
    await init_db()

    from app.scraper.playwright_auth import login, scrape_all

    click.echo("Logging in to Cookidoo...")

    loop = asyncio.get_running_loop()
    cookies = await loop.run_in_executor(None, login, email, password)

    if not cookies:
        click.echo("Login failed. Cannot scrape.")
        return

    click.echo(f"Logged in! Starting to scrape recipes...")
    count = await scrape_all(limit=limit)
    click.echo(f"Done! Scraped {count} recipes total.")


if __name__ == "__main__":
    cli()
