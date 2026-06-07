"""Periodic operator briefing — a plain-English control-room summary.

Builds a compact factual summary of the current incident picture and asks the
local text model to turn it into a short situational briefing for operators.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone

from . import config, vl


class BriefingGenerator:
    def __init__(self, state, store) -> None:
        self.state = state
        self.store = store
        self.text: str = ""
        self.generated_at: str | None = None
        self.task: asyncio.Task | None = None
        self._stop = False

    def _summary_text(self) -> str:
        incidents = self.store.incidents()
        if not incidents:
            return "No active incidents. All scanned cameras show clear, free-flowing traffic."
        by_cat = Counter(i["category"] for i in incidents)
        not_in_feed = sum(1 for i in incidents if not i.get("matched_disruption_id"))
        leads = [i for i in incidents if i.get("lead_time_seconds")]
        lines = [
            f"Active incidents: {len(incidents)}.",
            "By category: " + ", ".join(f"{n} {c}" for c, n in by_cat.most_common()) + ".",
        ]
        # a few representative locations per category
        for cat, _ in by_cat.most_common():
            locs = [i["common_name"] for i in incidents if i["category"] == cat][:4]
            lines.append(f"{cat}: {', '.join(locs)}.")
        lines.append(f"{not_in_feed} of {len(incidents)} not present in the official TfL disruption feed.")
        if leads:
            b = max(leads, key=lambda i: i["lead_time_seconds"])
            lines.append(
                f"Detected {b['category']} at {b['common_name']} "
                f"{round(b['lead_time_seconds'] / 60)} min before the official feed updated."
            )
        return " ".join(lines)

    async def run(self) -> None:
        print("[briefing] generator start")
        while not self._stop:
            try:
                summary = self._summary_text()
                text = await vl.generate_briefing(self.state.client, summary)
                if text:
                    self.text = text
                    self.generated_at = datetime.now(timezone.utc).isoformat()
                    print(f"[briefing] updated ({len(text)} chars)")
            except Exception as e:
                print(f"[briefing] error: {e}")
            await asyncio.sleep(config.BRIEFING_INTERVAL_SECONDS)

    def start(self) -> None:
        self.task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop = True
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass

    def latest(self) -> dict:
        return {"text": self.text, "generated_at": self.generated_at}
