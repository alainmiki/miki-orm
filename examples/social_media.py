#!/usr/bin/env python3
"""
Example 5: Social Media Platform
==================================
Demonstrates:
  - Self-referential ForeignKey (User -> User followers)
  - Complex multi-hop queries across related models
  - DateTimeField with auto_now_add for timestamps
  - TextField for post content
  - BooleanField for soft-delete / active status
  - JSONField for post metadata/reactions
  - Aggregate-style queries (counting likes, comments)
  - filter() with related field lookups
  - delete() with cascading implications
  - Bulk operations and data seeding
"""

import os
import argparse
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mikiorm
from mikiorm import makemigrations, migrate, models, register

DB_PATH = os.path.join(os.path.dirname(__file__), "social.db")

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations"
)


def cleanup():
    import shutil

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    if os.path.exists(MIGRATIONS_DIR):
        shutil.rmtree(MIGRATIONS_DIR)


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
class User(models.Model):
    """Social media user profile."""
    username = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    email = models.EmailField()
    password_hash = models.CharField(max_length=200)  # In practice, use proper hashing
    bio = models.TextField(null=True)
    avatar_url = models.URLField(null=True)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "users"

    def __repr__(self):
        return f"<User @{self.username}>"


@register
class Follow(models.Model):
    """User follows another user (self-referential FK)."""
    follower = models.ForeignKey(to="User", on_delete=models.CASCADE, related_name="following")
    followed = models.ForeignKey(to="User", on_delete=models.CASCADE, related_name="followers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "follows"


@register
class Post(models.Model):
    """A social media post."""
    author = models.ForeignKey(to="User", on_delete=models.CASCADE)
    content = models.TextField()
    image_url = models.URLField(null=True)
    metadata = models.JSONField(null=True)  # e.g. {"mentions": ["@bob"], "type": "text"}
    is_published = models.BooleanField(default=True)
    is_pinned = models.BooleanField(default=False)
    like_count_cache = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        table_name = "posts"

    def __repr__(self):
        return f"<Post by @{self.author.username}: {self.content[:40]}...>"


@register
class Comment(models.Model):
    """Comment on a post, supports nesting via parent reference."""
    post = models.ForeignKey(to="Post", on_delete=models.CASCADE)
    author = models.ForeignKey(to="User", on_delete=models.CASCADE)
    parent = models.ForeignKey(to="self", on_delete=models.CASCADE, null=True)
    content = models.CharField(max_length=1000)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "comments"


@register
class Like(models.Model):
    """Like on a post (could be extended to comments)."""
    user = models.ForeignKey(to="User", on_delete=models.CASCADE)
    post = models.ForeignKey(to="Post", on_delete=models.CASCADE)
    reaction_type = models.CharField(max_length=20, default="like")  # "like", "love", "haha", etc.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "likes"


@register
class Message(models.Model):
    """Direct message between users."""
    sender = models.ForeignKey(to="User", on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(to="User", on_delete=models.CASCADE, related_name="received_messages")
    content = models.CharField(max_length=2000)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        table_name = "messages"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def run(backend="sqlite"):
    if backend == "sqlite":
        cleanup()
    
    configure(backend)

    # Initialize schema via migration workflow
    makemigrations()
    migrate()
    print("  [OK] Schema initialized via migrations.")

    # ---- Create users ----
    users_data = [
        ("alice", "Alice Chen", "alice@social.com"),
        ("bob", "Bob Smith", "bob@social.com"),
        ("charlie", "Charlie Davis", "charlie@social.com"),
        ("diana", "Diana Evans", "diana@social.com"),
        ("eve", "Eve Foster", "eve@social.com"),
    ]
    users = {}
    for uname, dname, email in users_data:
        user = User.objects.create(
            username=uname, display_name=dname, email=email,
            password_hash=f"hashed_{uname}",  # placeholder
        )
        users[uname] = user
    print(f"Users created: {User.objects.count()}")

    # ---- Create follow relationships ----
    Follow.objects.create(follower=users["alice"], followed=users["bob"])
    Follow.objects.create(follower=users["alice"], followed=users["charlie"])
    Follow.objects.create(follower=users["bob"], followed=users["alice"])
    Follow.objects.create(follower=users["charlie"], followed=users["alice"])
    Follow.objects.create(follower=users["diana"], followed=users["alice"])
    Follow.objects.create(follower=users["eve"], followed=users["bob"])
    Follow.objects.create(follower=users["eve"], followed=users["charlie"])
    print(f"Follow relationships: {Follow.objects.count()}")

    # ---- Create posts ----
    post1 = Post.objects.create(
        author=users["alice"],
        content="Just started learning miki-orm! Loving the Django-like API. #python",
        metadata={"mentions": ["@bob"], "type": "text", "hashtags": ["python", "orm"]},
    )
    post2 = Post.objects.create(
        author=users["alice"],
        content="Second post — building a social platform with this ORM.",
        metadata={"type": "text"},
    )
    post3 = Post.objects.create(
        author=users["bob"],
        content="Check out my new blog post about ORM design patterns.",
        image_url="https://example.com/orm-patterns.png",
        metadata={"type": "article"},
    )
    post4 = Post.objects.create(
        author=users["charlie"],
        content="Morning coffee and coding ☕",
        metadata={"type": "text"},
    )
    print(f"Posts: {Post.objects.count()}")

    # ---- Create comments ----
    Comment.objects.create(post=post1, author=users["bob"], content="Great intro!")
    Comment.objects.create(post=post1, author=users["charlie"], content="Welcome aboard!")
    Comment.objects.create(post=post1, author=users["bob"], content="Thread reply!", parent=1)
    Comment.objects.create(post=post2, author=users["diana"], content="Interesting approach.")
    Comment.objects.create(post=post3, author=users["alice"], content="Well written!")
    Comment.objects.create(post=post3, author=users["eve"], content="Bookmarking this.")
    print(f"Comments: {Comment.objects.count()}")

    # ---- Create likes ----
    Like.objects.create(user=users["bob"], post=post1, reaction_type="like")
    Like.objects.create(user=users["charlie"], post=post1, reaction_type="love")
    Like.objects.create(user=users["diana"], post=post1, reaction_type="like")
    Like.objects.create(user=users["alice"], post=post3, reaction_type="like")
    Like.objects.create(user=users["eve"], post=post3, reaction_type="haha")
    Like.objects.create(user=users["charlie"], post=post4, reaction_type="like")
    print(f"Likes: {Like.objects.count()}")

    # ---- Create messages ----
    Message.objects.create(sender=users["alice"], recipient=users["bob"], content="Hey Bob, thanks for the comment!")
    Message.objects.create(sender=users["bob"], recipient=users["alice"], content="You're welcome!")
    Message.objects.create(sender=users["charlie"], recipient=users["alice"], content="Great posts as always!")
    print(f"Messages: {Message.objects.count()}")

    # ---- SOCIAL QUERIES ----

    # How many followers does Alice have?
    alice_followers = Follow.objects.filter(followed=users["alice"]).count()
    print(f"\nAlice has {alice_followers} followers")

    # Who does Alice follow?
    alice_following = Follow.objects.filter(follower=users["alice"])
    print(f"Alice follows: {[f.followed.username for f in alice_following]}")

    # Mutual follows (Alice follows them AND they follow Alice)
    for f in alice_following:
        mutual = Follow.objects.filter(follower=f.followed, followed=users["alice"])
        if mutual.exists():
            print(f"  ↔ Mutual follow with {f.followed.username}")

    # All posts by followed users (news feed for Alice)
    followed_users = [f.followed for f in alice_following]
    news_feed = Post.objects.filter(author__in=[u.id for u in followed_users])
    print(f"\nAlice's news feed ({news_feed.count()} posts):")
    for p in news_feed.order_by("-created_at"):
        print(f"  @{p.author.username}: {p.content[:50]}...")

    # Posts with specific hashtag in metadata
    tech_posts = Post.objects.filter(metadata__contains="python") if hasattr(
        Post.objects.filter(metadata__contains="python"), 'all'
    ) else Post.objects.all()  # Fallback: iterate all
    print(f"\nPosts mentioning 'python': checking metadata...")
    for p in Post.objects.all():
        if p.metadata and "python" in p.metadata.get("hashtags", []):
            print(f"  @{p.author.username}: {p.content[:50]}...")

    # Most liked posts
    posts_by_likes = []
    for p in Post.objects.all():
        like_count = Like.objects.filter(post=p).count()
        posts_by_likes.append((p, like_count))
    posts_by_likes.sort(key=lambda x: x[1], reverse=True)
    print(f"\nPosts ranked by likes:")
    for p, count in posts_by_likes:
        print(f"  {count} ❤️  @{p.author.username}: {p.content[:40]}...")

    # Users with most posts
    user_post_counts = {}
    for p in Post.objects.all():
        user_post_counts[p.author.username] = user_post_counts.get(p.author.username, 0) + 1
    print(f"\nPosts per user: {user_post_counts}")

    # Comments on a specific post
    post1_comments = Comment.objects.filter(post=post1, parent=None, is_deleted=False)
    print(f"\nComments on post1 ({post1_comments.count()}):")
    for c in post1_comments:
        print(f"  @{c.author.username}: {c.content}")

    # Unread messages for Alice
    unread = Message.objects.filter(recipient=users["alice"], is_read=False)
    print(f"\nUnread messages for Alice: {unread.count()}")

    # ---- Soft delete simulation (mark post as unpublished) ----
    post_to_hide = Post.objects.filter(author=users["charlie"]).first()
    if post_to_hide:
        post_to_hide.is_published = False
        post_to_hide.save()
        print(f"\nUnpublished post by Charlie")

    # Verify it's filtered out
    published = Post.objects.filter(is_published=True)
    print(f"Published posts: {published.count()} (was {Post.objects.count()} total)")

    # ---- pin a post ----
    post_to_pin = Post.objects.filter(author=users["alice"]).first()
    if post_to_pin:
        post_to_pin.is_pinned = True
        post_to_pin.save()
        pinned = Post.objects.filter(is_pinned=True)
        print(f"\nPinned posts: {pinned.count()}")

    # ---- UPDATE cache field ----
    for p in Post.objects.all():
        actual_likes = Like.objects.filter(post=p).count()
        p.like_count_cache = actual_likes
        p.save()
    print(f"\nUpdated like count cache for all posts")
    for p in Post.objects.all().order_by("-like_count_cache"):
        print(f"  Post {p.id}: {p.like_count_cache} likes")

    # ---- Bulk create users ----
    new_users = [
        User(username=f"user_{i}", display_name=f"User {i}",
             email=f"user{i}@example.com", password_hash=f"hash_{i}",
             is_verified=(i % 2 == 0))
        for i in range(3)
    ]
    User.objects.bulk_create(new_users)
    print(f"\nAfter bulk create — total users: {User.objects.count()}")

    # ---- Verify vs non-verified users ----
    verified = User.objects.filter(is_verified=True)
    print(f"Verified users: {verified.count()}")

    # ---- DELETE with cascade implications ----
    # Deleting Alice will cascade to her posts, comments, likes, messages, follow records
    alice_posts_count = Post.objects.filter(author=users["alice"]).count()
    print(f"\nBefore deleting Alice: she has {alice_posts_count} posts")

    users["alice"].delete()
    print(f"After deleting Alice: posts remaining = {Post.objects.count()}")
    print(f"Comments remaining = {Comment.objects.count()}")
    print(f"Likes remaining = {Like.objects.count()}")
    print(f"Follows remaining = {Follow.objects.count()}")

    # ---- EXCEPTION HANDLING ----
    try:
        User.objects.get(username="nonexistent")
    except models.ObjectDoesNotExist:
        print("\nObjectDoesNotExist correctly raised")

    try:
        User.objects.get(is_active=True)
    except models.MultipleObjectsReturned:
        print("MultipleObjectsReturned correctly raised for ambiguous query")

    # ---- to_dict ----
    bob = User.objects.get(username="bob")
    print(f"\nBob as dict: {bob.to_dict()}")

    print("\n✅ Example 5 — Social media platform completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["sqlite", "postgres"], default="sqlite")
    args = parser.parse_args()
    
    run(args.backend)