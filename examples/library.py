#!/usr/bin/env python3
"""
Example 3: Library Management System
======================================
Demonstrates:
  - ManyToManyField usage (Book <-> Author, Book <-> Genre)
  - Through tables for intermediate relationships
  - SlugField for URL-friendly identifiers
  - PositiveIntegerField for page counts and ratings
  - DateField for publication dates
  - select_related() and prefetch_related() hints
  - Complex filtering across multiple related models
  - Bulk operations and batch processing
"""

import os
import argparse
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mikiorm
from mikiorm import models, register

DB_PATH = os.path.join(os.path.dirname(__file__), "library.db")


def cleanup():
    import shutil

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    mig_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations")
    if os.path.exists(mig_dir):
        shutil.rmtree(mig_dir)


def configure(backend="sqlite"):
    if backend == "postgres":
        mikiorm.configure({
            "default": {
                "ENGINE": "postgresql",
                "NAME": "test",
                "USER": "postgres",
                "PASSWORD": "admin",
                "HOST": "localhost",
                "PORT": 5432,
            }
        })
    else:
        mikiorm.configure({
            "default": {
                "ENGINE": "sqlite",
                "NAME": DB_PATH,
            }
        })


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------

@register
class Author(models.Model):
    """Book author or co-author."""
    name = models.CharField(max_length=100)
    slug = models.SlugField()
    birth_year = models.PositiveIntegerField(null=True)
    nationality = models.CharField(max_length=50, null=True)
    is_alive = models.BooleanField(default=True)

    class Meta:
        table_name = "authors"

    def __repr__(self):
        return f"<Author {self.name}>"


@register
class Genre(models.Model):
    """Book genre/category."""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField()
    description = models.TextField(null=True)

    class Meta:
        table_name = "genres"

    def __repr__(self):
        return f"<Genre {self.name}>"


@register
class Publisher(models.Model):
    """Book publisher."""
    name = models.CharField(max_length=150)
    slug = models.SlugField()
    founded_year = models.PositiveIntegerField(null=True)
    website = models.URLField(null=True)

    class Meta:
        table_name = "publishers"

    def __repr__(self):
        return f"<Publisher {self.name}>"


@register
class Book(models.Model):
    """A book with multiple authors and genres."""
    title = models.CharField(max_length=300)
    slug = models.SlugField()
    isbn = models.CharField(max_length=20, unique=True)
    authors = models.ManyToManyField(to="Author", related_name="books")
    genres = models.ManyToManyField(to="Genre", related_name="books")
    publisher = models.ForeignKey(to="Publisher", on_delete=models.SET_NULL, null=True)
    publication_date = models.DateField(null=True)
    page_count = models.PositiveIntegerField(default=0)
    rating = models.PositiveIntegerField(default=0, help_text="Average rating 0-5")
    is_available = models.BooleanField(default=True)
    summary = models.TextField(null=True)

    class Meta:
        table_name = "books"

    def __repr__(self):
        return f"<Book '{self.title}'>"


@register
class Member(models.Model):
    """Library member who can borrow books."""
    name = models.CharField(max_length=100)
    email = models.EmailField()
    join_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    borrowed_books = models.ManyToManyField(to="Book", through="BorrowRecord")

    class Meta:
        table_name = "members"

    def __repr__(self):
        return f"<Member {self.name}>"


@register
class BorrowRecord(models.Model):
    """Through model for Member <-> Book borrowing relationship."""
    member = models.ForeignKey(to="Member", on_delete=models.CASCADE)
    book = models.ForeignKey(to="Book", on_delete=models.CASCADE)
    borrowed_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True)
    is_returned = models.BooleanField(default=False)

    class Meta:
        table_name = "borrow_records"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run(backend="sqlite"):
    if backend == "sqlite":
        cleanup()
    
    configure(backend)

    # Create tables via migration API
    print(f"--- Setting up {backend} database ---")
    mikiorm.makemigrations()
    mikiorm.migrate()
    print("  [OK] Database schema initialized.")

    # ---- Create authors ----
    tolkien = Author.objects.create(
        name="J.R.R. Tolkien", slug="jr-r-tolkien",
        birth_year=1892, nationality="British", is_alive=False,
    )
    martin = Author.objects.create(
        name="George R.R. Martin", slug="grrm",
        birth_year=1948, nationality="American", is_alive=True,
    )
    king = Author.objects.create(
        name="Stephen King", slug="stephen-king",
        birth_year=1947, nationality="American", is_alive=True,
    )
    print(f"Authors: {Author.objects.count()}")

    # ---- Create genres ----
    fantasy = Genre.objects.create(name="Fantasy", slug="fantasy")
    horror = Genre.objects.create(name="Horror", slug="horror")
    scifi = Genre.objects.create(name="Science Fiction", slug="scifi")
    drama = Genre.objects.create(name="Drama", slug="drama")
    print(f"Genres: {Genre.objects.count()}")

    # ---- Create publishers ----
    houghton = Publisher.objects.create(
        name="Houghton Mifflin Harcourt", slug="hmh",
        founded_year=1832,
    )
    bantam = Publisher.objects.create(
        name="Bantam Books", slug="bantam",
        founded_year=1945,
    )
    print(f"Publishers: {Publisher.objects.count()}")

    # ---- Create books ----
    lotr = Book.objects.create(
        title="The Lord of the Rings",
        slug="lord-of-the-rings",
        isbn="978-0544003415",
        publisher=houghton,
        publication_date="1954-07-29",
        page_count=1178,
        rating=5,
        summary="An epic high-fantasy novel.",
    )
    got = Book.objects.create(
        title="A Game of Thrones",
        slug="game-of-thrones",
        isbn="978-0553593716",
        publisher=bantam,
        publication_date="1996-08-01",
        page_count=835,
        rating=5,
        summary="The first volume of A Song of Ice and Fire.",
    )
    shining = Book.objects.create(
        title="The Shining",
        slug="the-shining",
        isbn="978-0307743657",
        publisher=bantam,
        publication_date="1977-01-28",
        page_count=447,
        rating=4,
        summary="A family heads to an isolated hotel for the winter.",
    )
    it = Book.objects.create(
        title="It",
        slug="it",
        isbn="978-1501142970",
        publisher=bantam,
        publication_date="1986-09-15",
        page_count=1138,
        rating=4,
        summary="A group of kids battle an ancient evil in Derry, Maine.",
    )
    print(f"Books: {Book.objects.count()}")

    # ---- ManyToMany: Assign authors to books ----
    lotr.authors.add(tolkien)
    got.authors.add(martin)
    shining.authors.add(king)
    it.authors.add(king)
    print("\nAuthors assigned to books")

    # ---- ManyToMany: Assign genres to books ----
    lotr.genres.add(fantasy, drama)
    got.genres.add(fantasy, drama)
    shining.genres.add(horror)
    it.genres.add(horror, drama)
    print("Genres assigned to books")

    # ---- Create members ----
    member1 = Member.objects.create(
        name="Sarah Connor", email="sarah@example.com",
    )
    member2 = Member.objects.create(
        name="John Connor", email="john@example.com",
    )
    print(f"\nMembers: {Member.objects.count()}")

    # ---- Through model: Borrow books ----
    BorrowRecord.objects.create(member=member1, book=lotr)
    BorrowRecord.objects.create(member=member1, book=shining)
    BorrowRecord.objects.create(member=member2, book=got)
    BorrowRecord.objects.create(member=member2, book=it)
    print("Borrow records created")

    # ---- Query: Books by a specific author ----
    king_books = Book.objects.filter(authors=king)
    print(f"\nStephen King's books: {[b.title for b in king_books]}")

    # ---- Query: Books in a genre ----
    fantasy_books = Book.objects.filter(genres=fantasy)
    print(f"Fantasy books: {[b.title for b in fantasy_books]}")

    # ---- Query: Books rated 5 ----
    top_rated = Book.objects.filter(rating=5)
    print(f"Top rated books (5 stars): {[b.title for b in top_rated]}")

    # ---- Query: Long books (> 800 pages) ----
    long_books = Book.objects.filter(page_count__gte=800).order_by("-page_count")
    print(f"\nLong books (800+ pages):")
    for b in long_books:
        print(f"  {b.title}: {b.page_count} pages")

    # ---- Query: Books published before 2000 ----
    classics = Book.objects.filter(publication_date__lt="2000-01-01")
    print(f"\nClassics (published before 2000): {[b.title for b in classics]}")

    # ---- Query: Available books by publisher ----
    bantam_books = Book.objects.filter(publisher=bantam, is_available=True)
    print(f"\nBantam available books: {[b.title for b in bantam_books]}")

    # ---- Query: Members who borrowed books ----
    borrowers = Member.objects.filter(borrowed_books__is_available=False)
    print(f"\nMembers with borrowed books: {[m.name for m in borrowers]}")

    # ---- Through model queries: Active borrow records ----
    active_borrows = BorrowRecord.objects.filter(is_returned=False)
    print(f"Active borrow records: {active_borrows.count()}")
    for rec in active_borrows:
        print(f"  {rec.member.name} borrowed '{rec.book.title}' on {rec.borrowed_at}")

    # ---- Values: Get ISBN and titles ----
    book_data = Book.objects.values("isbn", "title", "page_count")
    print(f"\nBook data (values): {book_data}")

    # ---- Values_list: Get titles ----
    titles = Book.objects.values_list("title", flat=False)
    print(f"Book titles (as tuples): {titles}")

    # ---- Bulk create more authors ----
    new_authors = [
        Author(name=f"Author {i}", slug=f"author-{i}")
        for i in range(1, 4)
    ]
    Author.objects.bulk_create(new_authors)
    print(f"\nAfter bulk create — total authors: {Author.objects.count()}")

    # ---- UPDATE: Give all horror books rating 5 ----
    updated = Book.objects.filter(genres=horror).update(rating=5)
    print(f"Updated {updated} horror books to rating 5")

    # ---- EXCLUDE: All books NOT by Stephen King ----
    not_king = Book.objects.exclude(authors=king)
    print(f"\nBooks NOT by Stephen King: {[b.title for b in not_king]}")

    # ---- DELETE: Remove a book ----
    it.delete()
    print(f"Deleted 'It' — remaining books: {Book.objects.count()}")

    # ---- First / Last ----
    first_book = Book.objects.all().first()
    last_book = Book.objects.all().last()
    print(f"First book: {first_book.title}")
    print(f"Last book:  {last_book.title}")

    # ---- to_dict ----
    print(f"\nBook as dict: {lotr.to_dict()}")

    # ---- select_related / prefetch_related hints ----
    # These are hints stored on the QuerySet (actual join logic depends on
    # adapter support — here we demonstrate the API):
    qs = Book.objects.select_related("publisher").prefetch_related("authors", "genres")
    print(f"\nQuerySet with hints: {qs}")

    print("\n✅ Example 3 — Library system completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["sqlite", "postgres"], default="sqlite")
    args = parser.parse_args()
    
    run(args.backend)