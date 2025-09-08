import shutil
from typing import Dict, Any
from sqlalchemy import func
from ..core.events import EventBus
from ..db.connection import Database
from ..db.models import Channel, Message, HabitDailyScore

class DiagnosticsService:
    """Collects and emits runtime diagnostics (DB accessibility, counts, disk space)."""
    def __init__(self, bus: EventBus, db: Database, db_path: str):
        self.bus = bus
        self.db = db
        self.db_path = db_path
        self.last_results: Dict[str, Any] | None = None  # cached latest diagnostics snapshot

    async def run_startup(self, version: str = "0.1.0"):
        results = self.collect()
        payload: Dict[str, Any] = {"version": version, "results": results}
        await self.bus.Emit("DiagnosticsCompleted", payload, {})

    def collect(self) -> Dict[str, Any]:
        """Collect a synchronous snapshot of diagnostics information.

        TODO: Consider adding latency metrics / event loop health.
        """
        results: Dict[str, Any] = {}
        session = self.db.GetSession()
        try:
            session.query(Channel).first()  # Simple test query
            results["database"] = {"status": "ok"}
        except Exception as e:
            results["database"] = {"status": "error", "error": str(e)}
        finally:
            session.close()
        
        # Disk space (use current working directory disk)
        try:
            _, _, free = shutil.disk_usage('.')
            results["disk"] = {"free_mb": round(free/1024/1024, 2)}
        except Exception as e:
            results["disk_error"] = str(e)
            
        try:
            import os
            db_path = self.db_path
            storage: Dict[str, Any] = {"db_path": db_path}
            try:
                if db_path and db_path not in (":memory:",) and os.path.exists(db_path):
                    size_bytes = os.path.getsize(db_path)
                    storage["db_size_mb"] = round(size_bytes / 1024 / 1024, 3)
            except Exception:
                # size is best-effort; ignore errors
                pass
            results["storage"] = storage
        except Exception:
            # Entire storage section is optional
            pass
        
        session = self.db.GetSession()
        try:
            counts: Dict[str, Any] = {}
            counts["channels"] = session.query(func.count(Channel.id)).scalar() or 0
            counts["messages"] = session.query(func.count(Message.id)).scalar() or 0
            counts["habit_daily_scores"] = session.query(func.count(HabitDailyScore.id)).scalar() or 0
            
            results["counts"] = counts
        except Exception as e:
            results["counts_error"] = str(e)
        finally:
            session.close()
            
        self.last_results = results
        return results
