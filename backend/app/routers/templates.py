import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Template
from ..schemas import TemplateCreate, TemplateOut, TemplateUpdate

router = APIRouter(prefix="/api/templates", tags=["templates"])


async def _get_or_404(session: AsyncSession, template_id: int) -> Template:
    tpl = await session.get(Template, template_id)
    if not tpl:
        raise HTTPException(404, "Template not found")
    return tpl


@router.get("", response_model=list[TemplateOut])
async def list_templates(session: AsyncSession = Depends(get_session)):
    result = await session.scalars(select(Template).order_by(Template.is_builtin.desc(), Template.id))
    return result.all()


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(body: TemplateCreate, session: AsyncSession = Depends(get_session)):
    base = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:60] or "template"
    tpl = Template(**body.model_dump(), slug=f"{base}-{secrets.token_hex(3)}", is_builtin=False)
    session.add(tpl)
    await session.commit()
    await session.refresh(tpl)
    return tpl


@router.put("/{template_id}", response_model=TemplateOut)
async def update_template(template_id: int, body: TemplateUpdate, session: AsyncSession = Depends(get_session)):
    tpl = await _get_or_404(session, template_id)
    if tpl.is_builtin:
        raise HTTPException(403, "Built-in templates are read-only. Duplicate it to customise.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(tpl, key, value)
    await session.commit()
    await session.refresh(tpl)
    return tpl


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: int, session: AsyncSession = Depends(get_session)):
    tpl = await _get_or_404(session, template_id)
    if tpl.is_builtin:
        raise HTTPException(403, "Built-in templates cannot be deleted.")
    await session.delete(tpl)
    await session.commit()
