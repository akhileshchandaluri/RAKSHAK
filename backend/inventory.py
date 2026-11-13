"""Local review ledger. Approved inventory is immutable within a simulation run."""
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from uuid import uuid4
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from config import APPLIANCE_CATALOG


class ApplianceRequest(BaseModel):
    building_id: int = Field(ge=0, lt=500)
    appliance_id: str | None = Field(default=None, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    catalog_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=20)
    power_w: float = Field(gt=0, le=20000)
    requested: bool = True
    tier: Literal[0, 1, 2, 3]
    consent: bool = False
    source: HttpUrl
    justification: str = Field(min_length=10, max_length=2000)

    @model_validator(mode="after")
    def supported_control(self):
        if self.catalog_key not in APPLIANCE_CATALOG and self.catalog_key != "custom":
            raise ValueError("Select a catalog appliance or custom")
        return self


class ReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=10, max_length=2000)


class InventoryStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("RAKSHAK_INVENTORY_DB", Path(__file__).resolve().parents[1] / "var" / "inventory.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reason TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP, reviewed TEXT, revision INTEGER)")

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.row_factory = sqlite3.Row
            yield db

    def submit(self, request):
        request_id = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO requests (id,payload) VALUES (?,?)", (request_id, request.model_dump_json()))
        return request_id

    def list(self):
        with self.connect() as db:
            return [dict(row) | {"payload": json.loads(row["payload"])} for row in db.execute("SELECT * FROM requests ORDER BY created DESC, id")]

    def review(self, request_id, review):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT rowid AS submission_order, * FROM requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                raise KeyError(request_id)
            if row["status"] != "pending":
                raise ValueError("Request already reviewed")
            payload = json.loads(row["payload"])
            if review.decision == "approved" and payload.get("appliance_id"):
                for other in db.execute(
                    "SELECT payload FROM requests WHERE status='approved' AND rowid > ?",
                    (row["submission_order"],),
                ):
                    prior = json.loads(other["payload"])
                    if (prior["building_id"], prior.get("appliance_id")) == (payload["building_id"], payload["appliance_id"]):
                        raise ValueError("A conflicting change was approved; submit a fresh request")
            revision = db.execute("SELECT COALESCE(MAX(revision),0)+1 FROM requests").fetchone()[0]
            db.execute("UPDATE requests SET status=?,reason=?,reviewed=CURRENT_TIMESTAMP,revision=? WHERE id=?", (review.decision, review.reason, revision, request_id))
        return revision

    def snapshot(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,payload,revision FROM requests WHERE status='approved' ORDER BY revision").fetchall()
        return {"revision": max((row["revision"] for row in rows), default=0),
                "items": [json.loads(row["payload"]) | {"request_id": row["id"]} for row in rows]}
