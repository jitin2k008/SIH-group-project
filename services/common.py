import logging
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

log = logging.getLogger(__name__)

def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'The change conflicts with an existing record or database constraint')
    except SQLAlchemyError as exc:
        db.rollback()
        log.error('Database transaction failed: %s', type(exc).__name__)
        raise HTTPException(500, 'Could not save changes')

def get_or_404(db, model, row_id, *, lock=False):
    query = db.query(model).filter(model.id == row_id)
    if lock:
        query = query.populate_existing().with_for_update()
    row = query.first()
    if row is None:
        raise HTTPException(404, f'{model.__name__} not found')
    return row
