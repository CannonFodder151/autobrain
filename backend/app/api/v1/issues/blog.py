from fastapi import APIRouter

router = APIRouter(tags=["issues-blog"])

_POSTS: list = []


@router.get("/issues/blog", summary="List issue blog posts")
async def list_blog_posts() -> list:
    return _POSTS


@router.post("/issues/blog", summary="Create issue blog post")
async def create_blog_post(payload: dict) -> dict:
    post = {"id": str(len(_POSTS) + 1), **payload}
    _POSTS.append(post)
    return post
