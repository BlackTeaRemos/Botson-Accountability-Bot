from __future__ import annotations
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Dict, Tuple, Any
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy.orm import Session
# from sqlalchemy import text  # kept for potential future raw SQL use
from ..db.connection import Database
from ..db.models import HabitDailyScore
from ..core.config import AppConfig

class ReportingService:
    """Generates tabular image reports for daily habit completion.

    Pulls aggregated daily scores, normalizes them against a configurable
    daily goal, and renders a matplotlib table image.
    """
    def __init__(self, db: Database, config: AppConfig):
        self.db = db
        self.config = config

    def _fetch_raw_scores(self, days: int) -> List[Dict[str, Any]]:
        """Return raw daily score rows; windowing is applied after normalization.

        We intentionally fetch all rows ordered by date, because tests insert
        historical fixed dates and expect `days` to mean "last N unique dates present"
        rather than relative to current wall-clock time.
        """
        session: Session = self.db.GetSession()
        try:
            # Query using SQLAlchemy ORM – fetch all and order by date
            scores = (
                session.query(HabitDailyScore)
                .order_by(HabitDailyScore.date.asc())
                .all()
            )

            # Convert to dictionary format matching the original structure
            result: List[Dict[str, Any]] = []
            for score in scores:
                # Explicitly convert to builtin types for stable typing
                result.append({
                    'user_id': str(score.user_id),
                    'date': str(score.date),
                    'raw_score_sum': float(getattr(score, 'raw_score_sum')),  # robust attribute access
                })
            # Fallback: if ORM returned no rows (edge case in tests with multiple engines), use raw SQL
            if not result:
                raw_rows = self.db.QueryRaw(
                    "SELECT user_id, date, raw_score_sum FROM habit_daily_scores ORDER BY date ASC"
                )
                for user_id, date_str, raw_sum in raw_rows:
                    try:
                        result.append({
                            'user_id': str(user_id),
                            'date': str(date_str),
                            'raw_score_sum': float(raw_sum),
                        })
                    except Exception:
                        # Skip malformed raw rows silently; normalization will handle typical cases
                        continue
            return result
        finally:
            session.close()

    def _normalize(self, rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, float]], List[str]]:
        """Convert raw_score_sum (sum of per-message raw ratios) into a 0-5 scale based on absolute completion, not relative to other users.

        Assumption: Each message raw_ratio is (filled / total). Summing raw_ratio across messages for a day approximates tasks completed.
        We cap daily score at 5.0 to keep scale consistent.
        TODO: If we want more precise task counts, store per-message total tasks and completed tasks separately and compute fraction.
        """
        warnings: List[str] = []
        scores: Dict[str, Dict[str, float]] = {}
        for row_index, row in enumerate(rows):
            try:
                raw_user_id = row.get('user_id')
                raw_date = row.get('date')
                raw_score = row.get('raw_score_sum')
                # Validate/repair date
                date: str
                if isinstance(raw_date, str):
                    try:
                        # Accept YYYY-MM-DD primary format
                        datetime.strptime(raw_date, '%Y-%m-%d')
                        date = raw_date
                    except ValueError:
                        # Try common alternative formats
                        reparsed_date = None
                        for fmt in ('%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y', '%Y%m%d'):
                            try:
                                reparsed_date = datetime.strptime(raw_date, fmt)
                                break
                            except ValueError:
                                continue
                        if reparsed_date:
                            date = reparsed_date.strftime('%Y-%m-%d')
                            warnings.append(f"Repaired date '{raw_date}' -> '{date}' (row {row_index}).")
                        else:
                            warnings.append(f"Dropped row {row_index}: unparseable date '{raw_date}'.")
                            continue
                else:
                    warnings.append(f"Dropped row {row_index}: date not a string ('{raw_date}').")
                    continue
                # Sanitize score number; coerce strings, clamp negatives
                normalized_score: float
                try:
                    if isinstance(raw_score, (int, float)):
                        normalized_score = float(raw_score)
                    else:
                        normalized_score = float(str(raw_score).strip())
                except Exception:
                    warnings.append(f"Dropped row {row_index}: malformed score '{raw_score}'.")
                    continue
                if normalized_score < 0:
                    warnings.append(f"Clamped negative score {normalized_score} -> 0 (row {row_index}).")
                    normalized_score = 0.0
                user = str(raw_user_id)
                scores.setdefault(user, {})[date] = scores.setdefault(user, {}).get(date, 0.0) + normalized_score
            except Exception as e:  # catch-all so one bad row not fatal
                warnings.append(f"Skipped row {row_index}: unexpected error {e}.")
                continue
        # Scale raw_score_sum directly to 0-5 (assuming raw_score_sum already in 0-1 range aggregated; if it exceeds 1 we still cap)
        normalized: Dict[str, Dict[str, float]] = {}
        for user, date_score_map in scores.items():
            normalized[user] = {
                date: round(
                    min(score_value, self.config.daily_goal_tasks)
                    / self.config.daily_goal_tasks * 5,
                    2
                )
                for date, score_value in date_score_map.items()
            }
        return normalized, warnings

    def generate_weekly_table_image(self, days: int = 7, style: str = "style1", user_names: Dict[str, str] | None = None) -> Tuple[BytesIO, List[str], List[str]]:
        rows = self._fetch_raw_scores(days)
        if not rows:
            return BytesIO(), [], []
        normalized, warnings = self._normalize(rows)
        # Use dates from the normalized result (these were repaired to ISO) instead
        all_dates_full = sorted({d for user_map in normalized.values() for d in user_map.keys()})
        # Adjust to start from Monday of the latest week
        if all_dates_full:
            latest_date = datetime.strptime(all_dates_full[-1], '%Y-%m-%d')
            monday = latest_date - timedelta(days=latest_date.weekday())
            candidate_dates = [(monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
            all_dates = candidate_dates  # Use the full week, scores will be 0 if no data
        else:
            all_dates = []
        # Keep the last `days` unique dates present in data
        all_dates = all_dates[-days:] if days and days > 0 else all_dates
        if not all_dates:
            return BytesIO(), [], warnings
        data: List[List[Any]] = []
        # Build rows in a clearly-indented block so the analyzer knows 'row' and 'score_map' are bound
        for user_id, score_map in sorted(normalized.items(), key=lambda kv: float(sum(kv[1].values())), reverse=True):
            # score_map: Dict[str, float]
            display_name = user_names.get(user_id, user_id) if user_names else user_id
            if len(display_name) > 15:
                display_name = display_name[:12] + '...'
            row: List[Any] = [display_name] + [float(score_map.get(date, 0.0)) for date in all_dates]
            total_val = round(sum(float(score_map.get(date, 0.0)) for date in all_dates), 2)
            row.append(total_val)
            data.append(row)
        columns = ['User'] + [datetime.strptime(d, '%Y-%m-%d').strftime('%a ') for d in all_dates] + ['Total']
        df = pd.DataFrame(data, columns=columns)
        # Pixel-perfect sizing: 10px per character, 100 DPI
        max_user_len = max(len(name) for name in df['User']) if not df.empty else 0
        user_width_px = max(100, max_user_len * 10)  # Minimum 100px, 10px per character
        weekday_px = 50  # 5 characters * 10px
        total_px = 70    # 7 characters * 10px
        total_width_px = user_width_px + len(all_dates) * weekday_px + total_px
        figsize_width_inches = total_width_px / 100  # Convert to inches at 100 DPI
        
        figure_and_axis = plt.subplots(
            figsize=(
                figsize_width_inches,  # Pixel-perfect width
                max(2, 0.5 * len(df))  # Height remains relative
            ),
            dpi=100  # Fixed DPI for pixel control
        )
        figure, axis = figure_and_axis  # type: ignore
        figure.patch.set_alpha(0.0)
        axis.set_facecolor('none')
        axis.axis('off')
        # Convert DataFrame values and columns to plain Python lists to satisfy matplotlib typing
        cell_texts = df.values.tolist()
        column_labels = list(df.columns)
        table = axis.table(
            cellText=cell_texts,
            colLabels=column_labels,
            loc='center',
            cellLoc='center',
            colWidths=[user_width_px / total_width_px] + [weekday_px / total_width_px] * len(all_dates) + [total_px / total_width_px]
        )  # type: ignore
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1.1, 1.2)

        # TODO Rework into correct hashmap with configuration details and custorm styling
        def apply_style(style_name: str) -> None:
            if style_name == "style1":  # dark translucent
                header_bg = (0.15, 0.17, 0.20, 0.85)
                body_alt = (0.12, 0.14, 0.17, 0.35)
                body_base = (0.10, 0.12, 0.15, 0.15)
                text_color = '#e6e6'
                edge = (0.3, 0.3, 0.3, 0.4)
            elif style_name == "style2":  # light glass
                header_bg = (1, 1, 1, 0.85)
                body_alt = (1, 1, 1, 0.55)
                body_base = (1, 1, 1, 0.35)
                text_color = '#222'
                edge = (0.6, 0.6, 0.6, 0.5)
            elif style_name == "style3":  # high-contrast neon
                header_bg = (0.0, 0.0, 0.0, 0.85)
                body_alt = (0.05, 0.0, 0.10, 0.55)
                body_base = (0.0, 0.0, 0.08, 0.35)
                text_color = '#39ff14'
                edge = (0.2, 0.9, 0.2, 0.6)
            elif style_name == "style4":  # warm earth
                header_bg = (0.25, 0.18, 0.10, 0.9)
                body_alt = (0.30, 0.22, 0.14, 0.55)
                body_base = (0.28, 0.20, 0.12, 0.35)
                text_color = '#f5e9d6'
                edge = (0.55, 0.45, 0.30, 0.5)
            else:  # fallback style1
                return apply_style("style1")
            # Iterate the table cells and apply visuals. Use typing.cast to Any to quiet the type checker.
            table_any = table
            for (row_i, _col_j), cell in table_any.get_celld().items():
                cell_any = cell
                try:
                    cell_any.set_edgecolor(edge)
                except Exception:
                    # backend dependent
                    pass
                if row_i == 0:
                    try:
                        cell_any.set_text_props(weight='bold', color=text_color)
                    except Exception:
                        pass
                    try:
                        cell_any.set_facecolor(header_bg)
                    except Exception:
                        pass
                else:
                    try:
                        cell_any.set_text_props(color=text_color)
                    except Exception:
                        pass
                    try:
                        cell_any.set_facecolor(body_alt if row_i % 2 == 0 else body_base)
                    except Exception:
                        pass

        apply_style(style)
        # Remove all padding: expand table to full figure
        figure.subplots_adjust(left=0, right=1, top=1, bottom=0)
        # Save with no extra padding
        buf = BytesIO()
        figure.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, dpi=180, transparent=True)  # type: ignore
        buf.seek(0)
        plt.close(figure)
        human_dates = [datetime.strptime(d, '%Y-%m-%d').strftime('%a ') for d in all_dates]
        return buf, human_dates, warnings

    def get_weekly_structured(self, days: int = 7) -> Tuple[List[str], List[Dict[str, float | str]], Dict[str, float], List[str]]:
        """Return (dates, per_user_rows, totals) for embed rendering.

        per_user_rows: list of {"user_id": str, date1: score, ..., "total": totalScore}
        totals: date -> sum across users (optional aggregate)
        """
        rows = self._fetch_raw_scores(days)
        if not rows:
            return [], [], {}, []
        normalized, warnings = self._normalize(rows)
        # Use dates from normalized (ISO YYYY-MM-DD) to avoid raw DB formatting quirks
        all_dates_full = sorted({d for user_map in normalized.values() for d in user_map.keys()})
        # Adjust to start from Monday of the latest week
        if all_dates_full:
            latest_date = datetime.strptime(all_dates_full[-1], '%Y-%m-%d')
            monday = latest_date - timedelta(days=latest_date.weekday())
            candidate_dates = [(monday + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
            all_dates = candidate_dates  # Use the full week, scores will be 0 if no data
        else:
            all_dates = []
        # Keep the last `days` unique dates present in data
        all_dates = all_dates[-days:] if days and days > 0 else all_dates
        if not all_dates:
            return [], [], {}, warnings
        per_user: List[Dict[str, float | str]] = []
        for user_id, score_map in sorted(normalized.items(), key=lambda kv: sum(kv[1].values()), reverse=True):
            user_entry: Dict[str, float | str] = {"user_id": user_id}
            total = 0.0
            for date in all_dates:
                val = score_map.get(date, 0.0)
                user_entry[date] = val
                total += val
            user_entry["total"] = round(total, 2)
            per_user.append(user_entry)
        # per_user is a list of mappings from date->float
        totals: Dict[str, float] = {}
        for date in all_dates:
            scores_for_date: List[float] = [float(u.get(date, 0.0)) for u in per_user]
            totals[date] = round(sum(scores_for_date), 2)
        return all_dates, per_user, totals, warnings
