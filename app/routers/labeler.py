"""Provides a route for fetching labels for CURIEs/IDs."""
import logging
from typing import List

from fastapi import APIRouter, Query

from app.utils.ontology.ontology_utils import batch_fetch_labels
from app.utils.settings import get_user_agent

log = logging.getLogger(__name__)

USER_AGENT = get_user_agent()
router = APIRouter()


@router.get("/api/ontol/labeler", tags=["ontol/labeler"])
async def expand_curie(id: List[str] = Query(...)):
    """Fetches a map from CURIEs/IDs to labels."""
    for i in id:
        if "MGI:MGI" in i:
            id.remove(i)
            id.append(i.replace("MGI:MGI", "MGI:"))

    return batch_fetch_labels(id)
