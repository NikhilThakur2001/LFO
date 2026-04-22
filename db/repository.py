from datetime import datetime, timedelta
from models.signal import TradeSignal
from db.schema import get_connection


def save_signal(signal: TradeSignal, dispatched: bool, skip_reason: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO signals
            (id, asset, direction, entry_price, sl, tp1, tp2, confidence,
             inference_path, dispatched, skip_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.signal_id, signal.asset, signal.direction,
                signal.entry_price, signal.sl, signal.tp1, signal.tp2,
                signal.confidence, signal.inference_path,
                1 if dispatched else 0, skip_reason,
                signal.timestamp.isoformat(),
            ),
        )


def save_audit_event(event_type: str, asset: str, detail: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_events (event_type, asset, detail) VALUES (?, ?, ?)",
            (event_type, asset, detail),
        )


def get_weekly_summary() -> dict:
    since = (datetime.utcnow() - timedelta(days=7)).isoformat()
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE created_at >= ?", (since,)
        ).fetchone()[0]
        dispatched = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE dispatched=1 AND created_at >= ?", (since,)
        ).fetchone()[0]
        skip_reasons = conn.execute(
            """
            SELECT skip_reason, COUNT(*) as cnt FROM signals
            WHERE dispatched=0 AND skip_reason != '' AND created_at >= ?
            GROUP BY skip_reason ORDER BY cnt DESC LIMIT 5
            """,
            (since,),
        ).fetchall()
        runpod_calls = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE inference_path='runpod' AND created_at >= ?",
            (since,),
        ).fetchone()[0]

    return {
        "total": total,
        "dispatched": dispatched,
        "skipped": total - dispatched,
        "top_skip_reasons": [(r["skip_reason"], r["cnt"]) for r in skip_reasons],
        "runpod_calls": runpod_calls,
        "fast_calls": dispatched - runpod_calls if dispatched > runpod_calls else 0,
    }


def count_recent_signals(asset: str, direction: str, zone_key: float, within_minutes: int = 60) -> int:
    since = (datetime.utcnow() - timedelta(minutes=within_minutes)).isoformat()
    price_tol = zone_key * 0.005
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT COUNT(*) FROM signals
            WHERE asset=? AND direction=? AND dispatched=1
            AND entry_price BETWEEN ? AND ?
            AND created_at >= ?
            """,
            (asset, direction, zone_key - price_tol, zone_key + price_tol, since),
        ).fetchone()[0]
