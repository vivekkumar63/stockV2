from fastapi import APIRouter

router = APIRouter(tags=["market-data"])


@router.get("/stocks")
def list_stocks():
    return []
