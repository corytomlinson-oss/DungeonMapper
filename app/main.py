import os
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db, SessionLocal
from app.models import SavedDungeon
from app.dungeon_gen import generate_dungeon

os.makedirs("data", exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    saved = db.query(SavedDungeon).order_by(SavedDungeon.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(request, "index.html", {"saved": saved})


@app.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    area_type: str = Form(...),
    size: str = Form(...),
    num_levels: int = Form(...),
    seed: str = Form(""),
):
    parsed_seed = int(seed) if seed.strip().isdigit() else None
    dungeon = generate_dungeon(area_type, size, num_levels, parsed_seed)
    return templates.TemplateResponse(request, "partials/dungeon_result.html", {"dungeon": dungeon})


@app.post("/save", response_class=HTMLResponse)
def save_dungeon(
    request: Request,
    name: str = Form(""),
    area_type: str = Form(...),
    size: str = Form(...),
    num_levels: int = Form(...),
    seed: int = Form(...),
    db: Session = Depends(get_db),
):
    record = SavedDungeon(
        name=name.strip() or None,
        area_type=area_type,
        size=size,
        num_levels=num_levels,
        seed=seed,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return HTMLResponse(
        f"<p class='text-green-600 font-semibold'>Saved!</p>"
        f"<script>window.dispatchEvent(new Event('dungeon-saved'))</script>"
    )


@app.get("/dungeons", response_class=HTMLResponse)
def list_dungeons(request: Request, db: Session = Depends(get_db)):
    saved = db.query(SavedDungeon).order_by(SavedDungeon.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(request, "partials/saved_list.html", {"saved": saved})


@app.get("/dungeons/{dungeon_id}", response_class=HTMLResponse)
def load_dungeon(dungeon_id: int, request: Request, db: Session = Depends(get_db)):
    record = db.query(SavedDungeon).get(dungeon_id)
    if not record:
        return HTMLResponse("<p class='text-red-500'>Dungeon not found.</p>", status_code=404)
    dungeon = generate_dungeon(record.area_type, record.size, record.num_levels, record.seed)
    dungeon["saved_name"] = record.name
    return templates.TemplateResponse(request, "partials/dungeon_result.html", {"dungeon": dungeon})


@app.post("/dungeons/{dungeon_id}/delete", response_class=HTMLResponse)
def delete_dungeon(dungeon_id: int, request: Request, db: Session = Depends(get_db)):
    record = db.query(SavedDungeon).get(dungeon_id)
    if record:
        db.delete(record)
        db.commit()
    saved = db.query(SavedDungeon).order_by(SavedDungeon.created_at.desc()).limit(20).all()
    return templates.TemplateResponse(request, "partials/saved_list.html", {"saved": saved})
