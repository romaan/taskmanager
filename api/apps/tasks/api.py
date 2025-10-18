from fastapi import APIRouter

router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["Tasks"]
)


@router.get("/")
async def get_tasks():
    return {"message": "Hello World"}
