from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models import ECGAnalysis, ECGUpload, User
from app.services.analysis_cleanup import delete_analysis_bundle, unlink_if_file

router = APIRouter()


@router.delete("/{upload_id}")
def delete_upload(upload_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.get(ECGUpload, upload_id)
    if not u or u.user_id != current.id:
        raise HTTPException(status_code=404, detail="Upload not found")
    a = db.query(ECGAnalysis).filter(ECGAnalysis.upload_id == u.id).first()
    if a:
        delete_analysis_bundle(db, a, u)
    else:
        unlink_if_file(u.stored_path)
        db.delete(u)
        db.commit()
    return {"ok": True, "deleted_upload_id": upload_id}
