from __future__ import annotations

from contextlib import contextmanager
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List


class EngineDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "EngineDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.close()

    @contextmanager
    def transaction(self):
        try:
            yield
        except Exception:
            self.conn.rollback()
            raise
        else:
            self.conn.commit()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS brand_records (
                brand_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                tier TEXT NOT NULL,
                industry TEXT,
                country TEXT,
                parent_company TEXT,
                knowledge_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS image_records (
                image_id TEXT PRIMARY KEY,
                external_key TEXT NOT NULL UNIQUE,
                brand_hint TEXT,
                category TEXT,
                source_name TEXT,
                source_channel TEXT,
                source_kind TEXT,
                scene_bucket TEXT,
                image_url TEXT,
                local_image_path TEXT,
                image_phash TEXT,
                quality_status TEXT,
                quality_score REAL,
                quality_gate_json TEXT,
                difficulty_flags_json TEXT,
                last_gated_at TEXT,
                tier TEXT NOT NULL,
                capture_context_json TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_image_records_phash ON image_records(image_phash);
            CREATE INDEX IF NOT EXISTS idx_image_records_channel ON image_records(source_channel);
            CREATE INDEX IF NOT EXISTS idx_image_records_tier ON image_records(tier);

            CREATE TABLE IF NOT EXISTS logo_instances (
                instance_id TEXT PRIMARY KEY,
                image_id TEXT NOT NULL,
                brand_id TEXT,
                merged_brand_name TEXT,
                detector_name TEXT,
                ocr_engine TEXT,
                clip_engine TEXT,
                bbox_json TEXT,
                polygon_json TEXT,
                rotated_box_json TEXT,
                mask_path TEXT,
                detector_score REAL,
                ocr_text TEXT,
                ocr_confidence REAL,
                clip_score REAL,
                caption_text TEXT,
                caption_model TEXT,
                attribution_json TEXT,
                knowledge_json TEXT,
                risk_json TEXT,
                confidence REAL,
                ambiguity_note TEXT,
                review_status TEXT,
                tier TEXT NOT NULL,
                provenance_json TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(image_id) REFERENCES image_records(image_id) ON DELETE CASCADE,
                FOREIGN KEY(brand_id) REFERENCES brand_records(brand_id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_logo_instances_image ON logo_instances(image_id);
            CREATE INDEX IF NOT EXISTS idx_logo_instances_brand ON logo_instances(brand_id);
            CREATE INDEX IF NOT EXISTS idx_logo_instances_tier ON logo_instances(tier);

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                command_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._ensure_column("image_records", "quality_status", "TEXT")
        self._ensure_column("image_records", "quality_score", "REAL")
        self._ensure_column("image_records", "quality_gate_json", "TEXT")
        self._ensure_column("image_records", "difficulty_flags_json", "TEXT")
        self._ensure_column("image_records", "last_gated_at", "TEXT")
        self._ensure_column("logo_instances", "caption_text", "TEXT")
        self._ensure_column("logo_instances", "caption_model", "TEXT")
        self._ensure_column("logo_instances", "attribution_json", "TEXT")
        self._ensure_column("logo_instances", "knowledge_json", "TEXT")
        self._ensure_column("logo_instances", "risk_json", "TEXT")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_image_records_quality_status ON image_records(quality_status)")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        existing = {
            str(row["name"])
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def _execute_many(self, query: str, rows: Iterable[Dict[str, Any]]) -> None:
        self.conn.executemany(query, list(rows))

    def upsert_brand_records(self, rows: Iterable[Dict[str, Any]], *, commit: bool = True) -> int:
        rows = list(rows)
        if not rows:
            return 0
        self._execute_many(
            """
            INSERT INTO brand_records (
                brand_id, canonical_name, display_name, tier, industry, country,
                parent_company, knowledge_json, created_at, updated_at
            )
            VALUES (
                :brand_id, :canonical_name, :display_name, :tier, :industry, :country,
                :parent_company, :knowledge_json, :created_at, :updated_at
            )
            ON CONFLICT(brand_id) DO UPDATE SET
                canonical_name=excluded.canonical_name,
                display_name=excluded.display_name,
                tier=excluded.tier,
                industry=excluded.industry,
                country=excluded.country,
                parent_company=excluded.parent_company,
                knowledge_json=excluded.knowledge_json,
                updated_at=excluded.updated_at
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)

    def upsert_image_records(self, rows: Iterable[Dict[str, Any]], *, commit: bool = True) -> int:
        rows = list(rows)
        if not rows:
            return 0
        self._execute_many(
            """
            INSERT INTO image_records (
                image_id, external_key, brand_hint, category, source_name, source_channel,
                source_kind, scene_bucket, image_url, local_image_path, image_phash,
                quality_status, quality_score, quality_gate_json, difficulty_flags_json, last_gated_at,
                tier, capture_context_json, raw_json, created_at, updated_at
            )
            VALUES (
                :image_id, :external_key, :brand_hint, :category, :source_name, :source_channel,
                :source_kind, :scene_bucket, :image_url, :local_image_path, :image_phash,
                :quality_status, :quality_score, :quality_gate_json, :difficulty_flags_json, :last_gated_at,
                :tier, :capture_context_json, :raw_json, :created_at, :updated_at
            )
            ON CONFLICT(image_id) DO UPDATE SET
                external_key=excluded.external_key,
                brand_hint=excluded.brand_hint,
                category=excluded.category,
                source_name=excluded.source_name,
                source_channel=excluded.source_channel,
                source_kind=excluded.source_kind,
                scene_bucket=excluded.scene_bucket,
                image_url=excluded.image_url,
                local_image_path=excluded.local_image_path,
                image_phash=excluded.image_phash,
                quality_status=COALESCE(excluded.quality_status, image_records.quality_status),
                quality_score=COALESCE(excluded.quality_score, image_records.quality_score),
                quality_gate_json=COALESCE(excluded.quality_gate_json, image_records.quality_gate_json),
                difficulty_flags_json=COALESCE(excluded.difficulty_flags_json, image_records.difficulty_flags_json),
                last_gated_at=COALESCE(excluded.last_gated_at, image_records.last_gated_at),
                tier=excluded.tier,
                capture_context_json=excluded.capture_context_json,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)

    def upsert_logo_instances(self, rows: Iterable[Dict[str, Any]], *, commit: bool = True) -> int:
        rows = list(rows)
        if not rows:
            return 0
        self._execute_many(
            """
            INSERT INTO logo_instances (
                instance_id, image_id, brand_id, merged_brand_name, detector_name, ocr_engine,
                clip_engine, bbox_json, polygon_json, rotated_box_json, mask_path, detector_score,
                ocr_text, ocr_confidence, clip_score, caption_text, caption_model, attribution_json,
                knowledge_json, risk_json,
                confidence, ambiguity_note, review_status,
                tier, provenance_json, raw_json, created_at, updated_at
            )
            VALUES (
                :instance_id, :image_id, :brand_id, :merged_brand_name, :detector_name, :ocr_engine,
                :clip_engine, :bbox_json, :polygon_json, :rotated_box_json, :mask_path, :detector_score,
                :ocr_text, :ocr_confidence, :clip_score, :caption_text, :caption_model, :attribution_json,
                :knowledge_json, :risk_json,
                :confidence, :ambiguity_note, :review_status,
                :tier, :provenance_json, :raw_json, :created_at, :updated_at
            )
            ON CONFLICT(instance_id) DO UPDATE SET
                image_id=excluded.image_id,
                brand_id=excluded.brand_id,
                merged_brand_name=excluded.merged_brand_name,
                detector_name=excluded.detector_name,
                ocr_engine=excluded.ocr_engine,
                clip_engine=excluded.clip_engine,
                bbox_json=excluded.bbox_json,
                polygon_json=excluded.polygon_json,
                rotated_box_json=excluded.rotated_box_json,
                mask_path=excluded.mask_path,
                detector_score=excluded.detector_score,
                ocr_text=excluded.ocr_text,
                ocr_confidence=excluded.ocr_confidence,
                clip_score=excluded.clip_score,
                caption_text=excluded.caption_text,
                caption_model=excluded.caption_model,
                attribution_json=excluded.attribution_json,
                knowledge_json=excluded.knowledge_json,
                risk_json=excluded.risk_json,
                confidence=excluded.confidence,
                ambiguity_note=excluded.ambiguity_note,
                review_status=excluded.review_status,
                tier=excluded.tier,
                provenance_json=excluded.provenance_json,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)

    def existing_phashes(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT image_phash FROM image_records WHERE image_phash IS NOT NULL AND image_phash != ''"
        ).fetchall()
        return {str(row["image_phash"]) for row in rows}

    def existing_external_keys(self) -> set[str]:
        rows = self.conn.execute("SELECT external_key FROM image_records").fetchall()
        return {str(row["external_key"]) for row in rows}

    def existing_instance_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT instance_id FROM logo_instances").fetchall()
        return {str(row["instance_id"]) for row in rows}

    def quality_passed_phashes(self) -> List[str]:
        rows = self.conn.execute(
            """
            SELECT image_phash
            FROM image_records
            WHERE image_phash IS NOT NULL
              AND image_phash != ''
              AND quality_status = 'passed'
            """
        ).fetchall()
        return [str(row["image_phash"]) for row in rows]

    def brand_name_index(self) -> Dict[str, str]:
        rows = self.conn.execute("SELECT brand_id, canonical_name, display_name, knowledge_json FROM brand_records").fetchall()
        index: Dict[str, str] = {}
        for row in rows:
            brand_id = str(row["brand_id"])
            for key in (row["canonical_name"], row["display_name"]):
                if key:
                    index[str(key).strip().lower()] = brand_id
            try:
                payload = json.loads(str(row["knowledge_json"]))
            except json.JSONDecodeError:
                payload = {}
            for alias in payload.get("aliases_en") or []:
                alias = str(alias).strip().lower()
                if alias:
                    index[alias] = brand_id
        return index

    def brand_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT brand_id FROM brand_records").fetchall()
        return {str(row["brand_id"]) for row in rows}

    def table_counts(self) -> Dict[str, int]:
        return {
            table: int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("brand_records", "image_records", "logo_instances")
        }

    def quality_status_counts(self) -> Dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT COALESCE(quality_status, 'pending') AS quality_status, COUNT(*) AS total
            FROM image_records
            GROUP BY COALESCE(quality_status, 'pending')
            ORDER BY quality_status
            """
        ).fetchall()
        return {str(row["quality_status"]): int(row["total"]) for row in rows}

    def update_image_quality(self, rows: Iterable[Dict[str, Any]], *, commit: bool = True) -> int:
        rows = list(rows)
        if not rows:
            return 0
        self._execute_many(
            """
            UPDATE image_records
            SET quality_status = :quality_status,
                quality_score = :quality_score,
                quality_gate_json = :quality_gate_json,
                difficulty_flags_json = :difficulty_flags_json,
                last_gated_at = :last_gated_at,
                updated_at = :updated_at
            WHERE image_id = :image_id
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)

    def export_joined_records(self) -> List[Dict[str, Any]]:
        image_rows = self.conn.execute("SELECT * FROM image_records ORDER BY created_at, image_id").fetchall()
        brand_rows = self.conn.execute("SELECT * FROM brand_records").fetchall()
        logo_rows = self.conn.execute("SELECT * FROM logo_instances ORDER BY created_at, instance_id").fetchall()
        brand_name_index = self.brand_name_index()

        brands = {
            str(row["brand_id"]): {
                "brand_id": row["brand_id"],
                "canonical_name": row["canonical_name"],
                "display_name": row["display_name"],
                "tier": row["tier"],
                **json.loads(str(row["knowledge_json"])),
            }
            for row in brand_rows
        }

        logos_by_image: Dict[str, List[Dict[str, Any]]] = {}
        for row in logo_rows:
            image_id = str(row["image_id"])
            logos_by_image.setdefault(image_id, []).append(
                {
                    "instance_id": row["instance_id"],
                    "brand_id": row["brand_id"],
                    "merged_brand_name": row["merged_brand_name"],
                    "detector_name": row["detector_name"],
                    "ocr_engine": row["ocr_engine"],
                    "clip_engine": row["clip_engine"],
                    "bbox": json.loads(row["bbox_json"]) if row["bbox_json"] else None,
                    "polygon": json.loads(row["polygon_json"]) if row["polygon_json"] else None,
                    "rotated_box": json.loads(row["rotated_box_json"]) if row["rotated_box_json"] else None,
                    "mask_path": row["mask_path"],
                    "detector_score": row["detector_score"],
                    "ocr_text": row["ocr_text"],
                    "ocr_confidence": row["ocr_confidence"],
                    "clip_score": row["clip_score"],
                    "caption_text": row["caption_text"],
                    "caption_model": row["caption_model"],
                    "attribution": json.loads(str(row["attribution_json"])) if row["attribution_json"] else None,
                    "knowledge": json.loads(str(row["knowledge_json"])) if row["knowledge_json"] else None,
                    "risk": json.loads(str(row["risk_json"])) if row["risk_json"] else None,
                    "confidence": row["confidence"],
                    "ambiguity_note": row["ambiguity_note"],
                    "review_status": row["review_status"],
                    "tier": row["tier"],
                    "provenance": json.loads(str(row["provenance_json"])),
                    "brand_record": brands.get(str(row["brand_id"])) if row["brand_id"] else None,
                }
            )

        exported: List[Dict[str, Any]] = []
        for row in image_rows:
            payload = json.loads(str(row["raw_json"]))
            payload["image_id"] = row["image_id"]
            payload["engine_tier"] = row["tier"]
            payload["engine_quality_status"] = row["quality_status"]
            payload["engine_quality_score"] = row["quality_score"]
            payload["engine_quality_gate"] = json.loads(str(row["quality_gate_json"])) if row["quality_gate_json"] else None
            payload["difficulty_flags"] = json.loads(str(row["difficulty_flags_json"])) if row["difficulty_flags_json"] else []
            payload["engine_brand_record"] = brands.get(brand_name_index.get(str(row["brand_hint"] or "").lower(), ""))
            payload["logo_instances"] = logos_by_image.get(str(row["image_id"]), [])
            exported.append(payload)
        return exported

    def export_image_records(self, quality_status: str | None = None, limit: int | None = None) -> List[Dict[str, Any]]:
        query = "SELECT raw_json FROM image_records"
        params: List[Any] = []
        if quality_status is not None:
            query += " WHERE COALESCE(quality_status, 'pending') = ?"
            params.append(quality_status)
        query += " ORDER BY created_at, image_id"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))
        rows = self.conn.execute(query, params).fetchall()
        return [json.loads(str(row["raw_json"])) for row in rows]

    def apply_review_decisions(self, rows: Iterable[Dict[str, Any]], *, commit: bool = True) -> int:
        rows = list(rows)
        if not rows:
            return 0
        self._execute_many(
            """
            UPDATE logo_instances
            SET review_status = :review_status,
                tier = :tier,
                updated_at = :updated_at
            WHERE instance_id = :instance_id
            """,
            rows,
        )
        if commit:
            self.conn.commit()
        return len(rows)
