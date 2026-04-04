from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw

from .db import EngineDB
from .record_types import ReviewDecisionRow
from .schema import utcnow_iso


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Logo Data Engine review UI server.")
    parser.add_argument("--db", required=True, help="Path to engine SQLite DB")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument(
        "--image-root",
        default="/raid/ming/logo",
        help="Root directory for serving images (default: /raid/ming/logo)",
    )
    return parser.parse_args()


def safe_resolve(path_str: str, root: Path) -> Path:
    candidate = Path(path_str).expanduser().resolve()
    root_resolved = root.resolve()
    if not str(candidate).startswith(str(root_resolved)):
        raise HTTPException(status_code=403, detail="Path not allowed")
    return candidate


def fetch_rows(
    db: EngineDB,
    *,
    status: Optional[str],
    tier: Optional[str],
    brand: Optional[str],
    limit: int,
    offset: int,
) -> List[Dict[str, Any]]:
    clauses = []
    params: List[Any] = []
    if status:
        clauses.append("COALESCE(li.review_status, 'needs_review') = ?")
        params.append(status)
    if tier:
        clauses.append("li.tier = ?")
        params.append(tier)
    if brand:
        clauses.append("LOWER(li.merged_brand_name) LIKE ?")
        params.append(f"%{brand.lower()}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT li.instance_id, li.image_id, li.merged_brand_name, li.review_status, li.tier,
               li.detector_score, li.clip_score, li.ocr_text, li.caption_text,
               li.knowledge_json, li.risk_json, li.bbox_json, li.mask_path,
               ir.local_image_path, ir.source_channel, ir.category
        FROM logo_instances li
        JOIN image_records ir ON li.image_id = ir.image_id
        {where}
        ORDER BY li.created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([int(limit), int(offset)])
    rows = db.conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def fetch_total(db: EngineDB, *, status: Optional[str], tier: Optional[str], brand: Optional[str]) -> int:
    clauses = []
    params: List[Any] = []
    if status:
        clauses.append("COALESCE(li.review_status, 'needs_review') = ?")
        params.append(status)
    if tier:
        clauses.append("li.tier = ?")
        params.append(tier)
    if brand:
        clauses.append("LOWER(li.merged_brand_name) LIKE ?")
        params.append(f"%{brand.lower()}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT COUNT(*) AS total
        FROM logo_instances li
        JOIN image_records ir ON li.image_id = ir.image_id
        {where}
    """
    row = db.conn.execute(query, params).fetchone()
    return int(row["total"]) if row else 0


def fetch_record(db: EngineDB, instance_id: str) -> Dict[str, Any]:
    query = """
        SELECT li.*, ir.local_image_path, ir.source_channel, ir.category, ir.raw_json AS image_raw_json
        FROM logo_instances li
        JOIN image_records ir ON li.image_id = ir.image_id
        WHERE li.instance_id = ?
    """
    row = db.conn.execute(query, [instance_id]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    payload = dict(row)
    payload["bbox_json"] = json.loads(str(row["bbox_json"])) if row["bbox_json"] else None
    payload["attribution_json"] = json.loads(str(row["attribution_json"])) if row["attribution_json"] else None
    payload["knowledge_json"] = json.loads(str(row["knowledge_json"])) if row["knowledge_json"] else None
    payload["risk_json"] = json.loads(str(row["risk_json"])) if row["risk_json"] else None
    payload["provenance_json"] = json.loads(str(row["provenance_json"])) if row["provenance_json"] else None
    payload["raw_json"] = json.loads(str(row["raw_json"])) if row["raw_json"] else None
    payload["image_raw_json"] = json.loads(str(row["image_raw_json"])) if row["image_raw_json"] else None
    return payload


def _open_mask(mask_path: str, image_size: tuple[int, int], image_root: Path) -> Image.Image | None:
    try:
        resolved = safe_resolve(mask_path, image_root)
    except HTTPException:
        return None
    if not resolved.exists():
        return None
    with Image.open(resolved) as mask:
        return mask.convert("L").resize(image_size)


def render_overlay(record: Dict[str, Any], image_root: Path) -> bytes:
    image_path = str(record.get("local_image_path") or "")
    resolved = safe_resolve(image_path, image_root)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="image not found")

    with Image.open(resolved) as image:
        base = image.convert("RGBA")
        draw = ImageDraw.Draw(base)

        bbox = record.get("bbox_json")
        if isinstance(bbox, list) and len(bbox) == 4:
            x0, y0, x1, y1 = [int(round(float(v))) for v in bbox]
            draw.rectangle([x0, y0, x1, y1], outline=(255, 80, 80, 255), width=6)

        mask_path = record.get("mask_path")
        if mask_path:
            mask = _open_mask(str(mask_path), base.size, image_root)
            if mask is not None:
                overlay = Image.new("RGBA", base.size, (50, 180, 120, 0))
                alpha = mask.point(lambda p: 110 if p > 0 else 0)
                overlay.putalpha(alpha)
                base = Image.alpha_composite(base, overlay)

        out = io.BytesIO()
        base.save(out, format="PNG")
        return out.getvalue()


def create_app(db_path: Path, image_root: Path) -> FastAPI:
    app = FastAPI(title="Logo Data Engine Review UI")
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "ui"))

    @app.get("/", response_class=HTMLResponse)
    def index(
        request: Request,
        status: Optional[str] = Query(default="needs_review"),
        tier: Optional[str] = Query(default=None),
        brand: Optional[str] = Query(default=None),
        limit: int = Query(default=24, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> HTMLResponse:
        with EngineDB(db_path) as db:
            rows = fetch_rows(db, status=status, tier=tier, brand=brand, limit=limit, offset=offset)
            total = fetch_total(db, status=status, tier=tier, brand=brand)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "rows": rows,
                "total": total,
                "limit": limit,
                "offset": offset,
                "status": status,
                "tier": tier,
                "brand": brand,
            },
        )

    @app.get("/record/{instance_id}", response_class=HTMLResponse)
    def record_view(request: Request, instance_id: str) -> HTMLResponse:
        with EngineDB(db_path) as db:
            payload = fetch_record(db, instance_id)
        return templates.TemplateResponse(
            "record.html",
            {"request": request, "record": payload},
        )

    @app.get("/api/record/{instance_id}")
    def record_api(instance_id: str) -> JSONResponse:
        with EngineDB(db_path) as db:
            payload = fetch_record(db, instance_id)
        return JSONResponse(payload)

    @app.post("/api/decision")
    async def decision_api(request: Request) -> JSONResponse:
        payload = await request.json()
        instance_id = str(payload.get("instance_id") or "").strip()
        if not instance_id:
            raise HTTPException(status_code=400, detail="instance_id required")
        tier = str(payload.get("tier") or "proposal").strip().lower()
        review_status = str(payload.get("review_status") or "needs_review").strip().lower()
        rows: List[ReviewDecisionRow] = [
            {
                "instance_id": instance_id,
                "tier": tier,
                "review_status": review_status,
                "updated_at": utcnow_iso(),
            }
        ]
        with EngineDB(db_path) as db:
            db.apply_review_decisions(rows)
        return JSONResponse({"instance_id": instance_id, "tier": tier, "review_status": review_status})

    @app.get("/image")
    def image_proxy(path: str) -> FileResponse:
        if not path:
            raise HTTPException(status_code=400, detail="path required")
        resolved = safe_resolve(path, image_root)
        if not resolved.exists():
            raise HTTPException(status_code=404, detail="image not found")
        return FileResponse(str(resolved))

    @app.get("/overlay/{instance_id}")
    def overlay_image(instance_id: str) -> Response:
        with EngineDB(db_path) as db:
            record = fetch_record(db, instance_id)
        png = render_overlay(record, image_root)
        return Response(content=png, media_type="image/png")

    return app


def main() -> None:
    args = parse_args()
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    app = create_app(Path(args.db), Path(args.image_root))
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
