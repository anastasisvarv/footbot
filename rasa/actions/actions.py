"""
Rasa custom actions for Footbot.
All data is sourced exclusively from local files via DataRepository.
No live HTTP calls are made here — run `python -m pipeline update` to refresh data.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from .data_repository import DataRepository
from . import predictor as pred

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _repo() -> DataRepository:
    return DataRepository.get()


def _get_entity(tracker: Tracker, entity: str, role: Optional[str] = None) -> Optional[str]:
    """Extract the first matching entity value, optionally filtered by role."""
    for e in tracker.latest_message.get("entities", []):
        if e.get("entity") == entity:
            if role is None or e.get("role") == role:
                return e.get("value")
    return None


def _get_teams(tracker: Tracker):
    """Return (home_team, away_team) preferring role-annotated entities."""
    home = _get_entity(tracker, "team", "home")
    away = _get_entity(tracker, "team", "away")
    if home and away:
        return home, away
    # Fallback: positional order
    teams = [
        e["value"]
        for e in tracker.latest_message.get("entities", [])
        if e.get("entity") == "team"
    ]
    if len(teams) >= 2:
        return teams[0], teams[1]
    return None, None


def _get_single_team(tracker: Tracker) -> Optional[str]:
    return _get_entity(tracker, "team")


def _get_league(tracker: Tracker) -> Optional[str]:
    return _get_entity(tracker, "league")


_NO_DATA_HINT = "\nRun `python -m pipeline update` to refresh local data."


# ---------------------------------------------------------------------------
# Action: predict_match
# ---------------------------------------------------------------------------

class ActionPredictMatch(Action):
    def name(self) -> Text:
        return "action_predict_match"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        home_team, away_team = _get_teams(tracker)
        if not home_team or not away_team:
            dispatcher.utter_message(
                text="🤔 I need two teams to make a prediction.\n"
                     "Try: **predict Liverpool vs Arsenal**"
            )
            return []

        repo = _repo()
        home_stats = repo.get_team_stats(home_team)
        away_stats = repo.get_team_stats(away_team)

        if not home_stats or not away_stats:
            missing = home_team if not home_stats else away_team
            dispatcher.utter_message(
                text=f"⚠️ No data found for **{missing}**." + _NO_DATA_HINT
            )
            return []

        league_slug = home_stats.get("league", "default")
        computed_avg = repo.get_league_avg_goals(league_slug)
        result = pred.predict(home_stats, away_stats, league=league_slug, league_avg=computed_avg)
        home_form = pred.format_form(home_stats.get("form", []))
        away_form = pred.format_form(away_stats.get("form", []))
        ht = home_stats["team"]
        at = away_stats["team"]

        # Confidence: the dominant outcome probability indicates model certainty
        max_pct = max(result["home_win_pct"], result["draw_pct"], result["away_win_pct"])
        if max_pct >= 55:
            confidence_label = "HIGH"
            confidence_icon  = "🟢"
        elif max_pct >= 42:
            confidence_label = "MEDIUM"
            confidence_icon  = "🟡"
        else:
            confidence_label = "LOW"
            confidence_icon  = "🔴"

        msg = (
            f"🎯 **MATCH PREDICTION**\n"
            f"🏠 {ht}  vs  {at} ✈️\n"
            f"{'─' * 35}\n"
            f"📊 Win Probabilities:\n"
            f"  {ht}: **{result['home_win_pct']}%**\n"
            f"  Draw: **{result['draw_pct']}%**\n"
            f"  {at}: **{result['away_win_pct']}%**\n\n"
            f"⚽ Expected Goals (xG):\n"
            f"  {ht}: {result['home_xg']}\n"
            f"  {at}: {result['away_xg']}\n\n"
            f"🏆 Most Likely Score: **{result['most_likely_score']}** "
            f"({result['most_likely_prob']}% probability)\n\n"
            f"📋 Recent Form:\n"
            f"  {ht}: {home_form}\n"
            f"  {at}: {away_form}\n\n"
            f"{confidence_icon} Model Confidence: **{confidence_label}** ({max_pct}%)"
        )
        dispatcher.utter_message(text=msg)
        return []


# ---------------------------------------------------------------------------
# Action: get_team_stats
# ---------------------------------------------------------------------------

class ActionGetTeamStats(Action):
    def name(self) -> Text:
        return "action_get_team_stats"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        team = _get_single_team(tracker)
        if not team:
            dispatcher.utter_message(
                text="Which team would you like stats for?\n"
                     "Try: **Liverpool stats**"
            )
            return []

        stats = _repo().get_team_stats(team)
        if not stats:
            dispatcher.utter_message(
                text=f"⚠️ No data for **{team}**." + _NO_DATA_HINT
            )
            return []

        form_str = pred.format_form(stats.get("form", []))
        p = stats.get("played", 0)
        w = stats.get("won", 0)
        d = stats.get("drawn", 0)
        l = stats.get("lost", 0)

        msg = (
            f"📊 **{stats['team']} — Team Stats**\n"
            f"{'─' * 35}\n"
            f"📅 Last {p} matches: {w}W / {d}D / {l}L\n\n"
            f"⚽ Avg Goals Scored:    {stats['avg_goals_scored']}\n"
            f"🛡️  Avg Goals Conceded: {stats['avg_goals_conceded']}\n\n"
            f"📋 Recent Form (last 5): {form_str}"
        )
        dispatcher.utter_message(text=msg)
        return []


# ---------------------------------------------------------------------------
# Action: compare_teams
# ---------------------------------------------------------------------------

class ActionCompareTeams(Action):
    def name(self) -> Text:
        return "action_compare_teams"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        team1, team2 = _get_teams(tracker)
        if not team1 or not team2:
            dispatcher.utter_message(
                text="I need two teams to compare.\n"
                     "Try: **compare Liverpool vs Arsenal**"
            )
            return []

        repo = _repo()
        s1 = repo.get_team_stats(team1)
        s2 = repo.get_team_stats(team2)

        if not s1 or not s2:
            dispatcher.utter_message(
                text="⚠️ Couldn't fetch stats for both teams. Check names and try again."
            )
            return []

        form1 = pred.format_form(s1.get("form", []))
        form2 = pred.format_form(s2.get("form", []))
        t1n, t2n = s1["team"], s2["team"]

        scored_edge1  = "🔥" if s1["avg_goals_scored"]   > s2["avg_goals_scored"]   else ""
        scored_edge2  = "🔥" if s2["avg_goals_scored"]   > s1["avg_goals_scored"]   else ""
        conceded_edge1 = "🔥" if s1["avg_goals_conceded"] < s2["avg_goals_conceded"] else ""
        conceded_edge2 = "🔥" if s2["avg_goals_conceded"] < s1["avg_goals_conceded"] else ""

        msg = (
            f"⚔️ **TEAM COMPARISON**\n"
            f"{'─' * 35}\n"
            f"{'Stat':<22} {t1n:<18} {t2n}\n"
            f"{'─' * 35}\n"
            f"{'Avg Goals Scored':<22} {s1['avg_goals_scored']:<8} {scored_edge1:<4}   "
            f"{s2['avg_goals_scored']} {scored_edge2}\n"
            f"{'Avg Goals Conceded':<22} {s1['avg_goals_conceded']:<8} {conceded_edge1:<4}   "
            f"{s2['avg_goals_conceded']} {conceded_edge2}\n"
            f"{'Last 10: W/D/L':<22} {s1['won']}/{s1['drawn']}/{s1['lost']:<8}   "
            f"{s2['won']}/{s2['drawn']}/{s2['lost']}\n\n"
            f"📋 Form: {t1n}: {form1}\n"
            f"         {t2n}: {form2}"
        )
        dispatcher.utter_message(text=msg)
        return []


# ---------------------------------------------------------------------------
# Action: get_standings
# ---------------------------------------------------------------------------

class ActionGetStandings(Action):
    def name(self) -> Text:
        return "action_get_standings"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        repo = _repo()
        league_raw = _get_league(tracker)

        if not league_raw:
            # Try to infer from the raw message text
            league_raw = tracker.latest_message.get("text", "")

        league_slug = repo.resolve_league(league_raw)
        if not league_slug:
            dispatcher.utter_message(
                text=(
                    "Which league? Try:\n"
                    "  **show Premier League table**\n"
                    "  **La Liga standings**\n"
                    "Supported: Premier League, La Liga, Serie A, "
                    "Bundesliga, Ligue 1, Super League"
                )
            )
            return []

        standings = repo.get_standings(league_slug)
        display_name = repo.league_display_name(league_slug)

        if not standings:
            dispatcher.utter_message(
                text=f"⚠️ No standings data for **{display_name}**." + _NO_DATA_HINT
            )
            return []

        rows = "\n".join(
            f"  {r['position']}. {r['team']:<25} Pts: {r['points']}  "
            f"({r['won']}W/{r['draw']}D/{r['lost']}L)  GD: {r['gd']}"
            for r in standings[:5]
        )
        msg = (
            f"🏆 **{display_name} — Top 5 Standings**\n"
            f"{'─' * 35}\n"
            f"{rows}"
        )
        dispatcher.utter_message(text=msg)
        return []


# ---------------------------------------------------------------------------
# Action: get_recent_form
# ---------------------------------------------------------------------------

class ActionGetRecentForm(Action):
    def name(self) -> Text:
        return "action_get_recent_form"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        team = _get_single_team(tracker)
        if not team:
            dispatcher.utter_message(
                text="Which team's form do you want?\n"
                     "Try: **Liverpool recent form**"
            )
            return []

        repo = _repo()
        stats = repo.get_team_stats(team)
        if not stats:
            dispatcher.utter_message(
                text=f"⚠️ No data for **{team}**." + _NO_DATA_HINT
            )
            return []

        form_str = pred.format_form(stats.get("form", []))
        canonical = stats["team"]
        canonical_lower = canonical.lower()
        matches = stats.get("recent_matches", [])

        match_lines: List[str] = []
        for m in matches[:5]:
            hg = m.get("home_goals", "?")
            ag = m.get("away_goals", "?")
            home = m["home_team"]
            away = m["away_team"]
            date = m.get("date", "")
            comp = m.get("competition", "")

            is_home = home.lower() == canonical_lower
            if isinstance(hg, int) and isinstance(ag, int):
                if hg == ag:
                    icon = "⬜"
                elif (is_home and hg > ag) or (not is_home and ag > hg):
                    icon = "✅"
                else:
                    icon = "❌"
            else:
                icon = "❓"

            match_lines.append(
                f"  {icon} {date}  {home} {hg}-{ag} {away}  ({comp})"
            )

        matches_text = (
            "\n".join(match_lines) if match_lines
            else "  No recent match details available."
        )
        msg = (
            f"📋 **{canonical} — Recent Form**\n"
            f"{'─' * 35}\n"
            f"Last 5 results: {form_str}\n\n"
            f"Recent Matches:\n{matches_text}"
        )
        dispatcher.utter_message(text=msg)
        return []


# ---------------------------------------------------------------------------
# Action: get_head_to_head
# ---------------------------------------------------------------------------

class ActionGetHeadToHead(Action):
    def name(self) -> Text:
        return "action_get_head_to_head"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        team1, team2 = _get_teams(tracker)
        if not team1 or not team2:
            dispatcher.utter_message(
                text="I need two teams for H2H.\n"
                     "Try: **Liverpool vs Arsenal head to head**"
            )
            return []

        h2h = _repo().get_head_to_head(team1, team2)
        if not h2h:
            dispatcher.utter_message(
                text=(
                    f"⚠️ No H2H data found for **{team1}** vs **{team2}**.\n"
                    "These teams may not have met in the scraped seasons."
                )
            )
            return []

        recent_lines = [
            f"  {m.get('date', '')}  {m['home_team']} "
            f"{m.get('home_goals','?')}-{m.get('away_goals','?')} {m['away_team']}"
            for m in h2h.get("recent_h2h", [])[:5]
        ]
        recent_text = (
            "\n".join(recent_lines) if recent_lines
            else "  No recent meetings found."
        )

        msg = (
            f"🔁 **HEAD TO HEAD**\n"
            f"{h2h['team1']} vs {h2h['team2']}\n"
            f"{'─' * 35}\n"
            f"Matches analysed: {h2h['matches_found']}\n\n"
            f"  {h2h['team1']} wins: {h2h['team1_wins']}\n"
            f"  Draws:           {h2h['draws']}\n"
            f"  {h2h['team2']} wins: {h2h['team2_wins']}\n\n"
            f"Recent Meetings:\n{recent_text}"
        )
        dispatcher.utter_message(text=msg)
        return []
