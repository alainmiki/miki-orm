#!/usr/bin/env python3
"""
Example 1: Basic CRUD Operations with a Blog System
=====================================================
Demonstrates:
  - Model definition with various field types (CharField, TextField, DateTimeField,
    BooleanField, SlugField, JSONField, EmailField)
  - AutoField primary key
  - create(), save(), delete() instance methods
  - QuerySet operations: filter(), exclude(), get(), all(), first(), last()
  - count(), exists(), values(), values_list()
  - get_or_create(), update_or_create()
  - Custom Meta options (table_name, ordering)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import myorm
from myorm import models

DB_PATH = os.path.join(os.path.dirname(__file__), "blog.db")


def cleanup():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


def configure():
    myorm.configure({
        "default": {
            "ENGINE": "sqlite",
            "NAME": DB_PATH,
        }
    })


# ---------------------------------------------------------------------------
# Model definitions
# ---------------------------------------------------------------------------

class Author(models.Model):
    """Represents a blog author."""
    name = models.CharField(max_length=100)
    email = models.EmailField()
    bio = models.TextField(null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "authors"
        ordering = ["name"]


class Category(models.Model):
    """Blog post categories (e.g. 'Technology', 'Lifestyle')."""
    name = models.CharField(max_length=50)
    slug = models.SlugField()
    description = models.TextField(null=True)

    class Meta:
        table_name = "categories"


class Post(models.Model):
    """A blog post with rich field types."""
    title = models.CharField(max_length=200)
    slug = models.SlugField()
    body = models.TextField()
    author = models.ForeignKey(to="Author", on_delete=models.CASCADE)
    category = models.ForeignKey(to="Category", on_delete=models.SET_NULL, null=True)
    is_published = models.BooleanField(default=False)
    tags = models.JSONField(null=True)          # e.g. ["python", "orm"]
    metadata = models.JSONField(null=True)      # e.g. {"read_time": 5}
    published_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        table_name = "posts"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run():
    cleanup()
    configure()

    # ---- CREATE via .objects.create() ----
    alice = Author.objects.create(
        name="Alice Chen",
        email="alice@example.com",
        bio="Full-stack developer and blogger",
    )
    bob = Author.objects.create(
        name="Bob Martinez",
        email="bob@example.com",
        bio="Data science enthusiast",
    )
    print(f"Created authors: {Author.objects.count()}")

    tech = Category.objects.create(name="Technology", slug="technology")
    life = Category.objects.create(name="Lifestyle", slug="lifestyle")
    print(f"Created categories: {Category.objects.count()}")

    # ---- CREATE with FK — pass model instance (ORM extracts PK via db_value) ----
    post1 = Post.objects.create(
        title="Introduction to miki-orm",
        slug="intro-to-miki-orm",
        body="miki-orm is a lightweight ORM inspired by Django...",
        author=alice,
        category=tech,
        is_published=True,
        tags=["python", "orm", "database"],
        metadata={"read_time": 8, "difficulty": "beginner"},
    )
    post2 = Post.objects.create(
        title="Advanced Query Patterns",
        slug="advanced-queries",
        body="Learn how to use filters, excludes, and ordering...",
        author=alice,
        category=tech,
        is_published=True,
        tags=["python", "queries"],
        metadata={"read_time": 12},
    )
    post3 = Post.objects.create(
        title="My Morning Routine",
        slug="morning-routine",
        body="A look at my daily habits for productivity...",
        author=bob,
        category=life,
        is_published=False,
    )
    print(f"Created posts: {Post.objects.count()}")

    # ---- CREATE via instance .save() ----
    post4 = Post(
        title="Working from Home Tips",
        slug="wfh-tips",
        body="Here are my tips for remote work...",
        author=bob,
        category=life,
        is_published=True,
    )
    post4.save()
    print(f"After .save() — total posts: {Post.objects.count()}")

    # ---- UPDATE via instance .save() ----
    post4.title = "Ultimate WFH Guide 2026"
    post4.save()
    refreshed = Post.objects.get(id=post4.id)
    print(f"Updated title: {refreshed.title}")

    # ---- READ: .all() and len() ----
    all_posts = Post.objects.all()
    print(f"\nAll posts ({len(all_posts)}):")
    for p in all_posts:
        author_name = Author.objects.get(id=p.author).name
        print(f"  [{p.id}] {p.title} by {author_name}")

    # ---- READ: .filter() with FK ID ----
    alice_posts = Post.objects.filter(author=alice.id)
    print(f"\nAlice's posts: {len(alice_posts)}")

    published = Post.objects.filter(is_published=True)
    print(f"Published posts: {len(published)}")

    # Chained filters
    tech_published = Post.objects.filter(category=tech.id).filter(is_published=True)
    print(f"Published tech posts: {len(tech_published)}")

    # ---- READ: .exclude() ----
    not_by_alice = Post.objects.exclude(author=alice.id)
    print(f"Posts NOT by Alice: {len(not_by_alice)}")

    # ---- READ: .get() ----
    fetched = Post.objects.get(slug="intro-to-miki-orm")
    print(f"\nFetched by slug: {fetched.title}")

    # ---- READ: .first() / .last() ----
    first_post = Post.objects.all().order_by("id").first()
    last_post = Post.objects.all().order_by("-id").last()
    print(f"First post:  {first_post.title}")
    print(f"Last post:   {last_post.title}")

    # ---- ORDERING ----
    ordered = Post.objects.all().order_by("-id")
    print(f"\nPosts ordered by id desc: {[p.title for p in ordered]}")

    # ---- COUNT ----
    print(f"\nTotal posts: {Post.objects.count()}")
    print(f"Draft posts: {Post.objects.filter(is_published=False).count()}")

    # ---- EXISTS ----
    print(f"\nExists 'Alice': {Author.objects.filter(name='Alice Chen').exists()}")
    print(f"Exists 'Zara': {Author.objects.filter(name='Zara').exists()}")

    # ---- VALUES ----
    titles = Post.objects.filter(is_published=True).values("title", "slug")
    print(f"\nPublished post values: {titles}")

    # ---- VALUES_LIST ----
    slugs = Post.objects.values_list("slug")
    print(f"All slugs (as tuples): {slugs}")

    # ---- GET_OR_CREATE ----
    new_author, created = Author.objects.get_or_create(
        name="Alice Chen",
        defaults={"email": "alice_new@example.com", "bio": "Updated bio"},
    )
    print(f"\nget_or_create — created: {created}, id: {new_author.id}")

    # ---- UPDATE_OR_CREATE ----
    updated_author, was_created = Author.objects.update_or_create(
        name="Alice Chen",
        defaults={"bio": "Chief Technology Officer"},
    )
    print(f"update_or_create — created: {was_created}, bio: {updated_author.bio}")

    # ---- BULK CREATE ----
    batch = [
        Author(name=f"Author {i}", email=f"author{i}@example.com")
        for i in range(5)
    ]
    Author.objects.bulk_create(batch)
    print(f"\nAfter bulk create — total authors: {Author.objects.count()}")

    # ---- BULK UPDATE via QuerySet ----
    authors_to_deactivate = Author.objects.filter(is_active=True)
    rows_updated = 0
    for a in authors_to_deactivate:
        a.is_active = False
        a.save()
        rows_updated += 1
    print(f"Deactivated {rows_updated} authors via instance save")

    # ---- DELETE ----
    deleted = Post.objects.filter(is_published=False).delete()
    print(f"\nDeleted {deleted} draft post(s)")
    print(f"Remaining posts: {Post.objects.count()}")

    # ---- DELETE instance ----
    post1.delete()
    print(f"After post1.delete(): {Post.objects.count()} posts remain")

    # ---- Exception handling ----
    try:
        Author.objects.get(name="NONEXISTENT")
    except models.ObjectDoesNotExist:
        print("\nObjectDoesNotExist: correctly raised")

    # ---- to_dict() ----
    print(f"\nPost as dict: {post2.to_dict()}")

    print("\n[DONE] Example 1 -- Basic CRUD completed successfully!")


if __name__ == "__main__":
    run()