import logging

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.core.feedback import get_feedback_stats, submit_feedback
from app.models.schemas import FeedbackRequest, FeedbackResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", dependencies=[Depends(get_current_user)])


@router.post("", response_model=FeedbackResponse, status_code=201)
async def create_feedback(body: FeedbackRequest, user: dict = Depends(get_current_user)):
    feedback_id = await submit_feedback(
        user_id=str(user["_id"]),
        conversation_id=body.conversation_id,
        message_id=body.message_id,
        rating=body.rating,
        comment=body.comment,
    )
    return FeedbackResponse(id=feedback_id)


@router.get("/stats")
async def feedback_stats(user: dict = Depends(get_current_user)):
    return await get_feedback_stats(user_id=str(user["_id"]))
