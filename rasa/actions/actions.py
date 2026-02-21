"""
Rasa custom actions for Footbot.
Six action classes + helper utilities.
"""

import logging
from typing import Any, Dict, List, Optional, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from . import football_data as fd
from . import predictor as pred

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_entity(tracker: Tracker, entity: str, role: Optional[str] = None) -> Optional[str]:
    """Extract first entity value, optionally filtered by role."""
    for e in tracker.latest_message.get("entities", []):
        if e.get("entity") == entity:
            if role is None or e.get("role") == role:
                return e.get("value")
    return None


def _get_teams(tracker: Tracker):
    """Return (home_team, away_team) from role-annotated entities."""
    home = _get_entity(tracker, "team", "home")
    away = _get_entity(tracker, "team", "away")

    if home and away:
        return home, away

    # Fallback: collect all team entities in order
    teams = [e["value"] for e in tracker.latest_message.get("entities", []) if e.get("entity") == "team"]
    if len(teams) >= 2:
        return teams[0], teams[1]
    return None, None


def _get_single_team(tracker: Tracker) -> Optional[str]:
    """Return first team entity (any role)."""
    return _get_entity(tracker, "team")


def _get_league(tracker: Tracker) -> Optional[str]:
    return _get_entity(tracker, "league")


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

        home_stats = fd.get_team_stats(home_team)
        away_stats = fd.get_team_stats(away_team)

        if not home_stats or not away_stats:
            dispatcher.utter_message(
                text=f"⚠️ Couldn't fetch stats for {home_team} or {away_team}. "
                     "Please check the team names and try again."
            )
            return []

        # Detect league from stats or default
        league = "default"
        result = pred.predict(home_stats, away_stats, league)

        home_form = pred.format_form(home_stats.get("form", []))
        away_form = pred.format_form(away_stats.get("form", []))
        fallback_note = "\n_(Using estimated data — API key may not be set)_" if home_stats.get("_fallback") else ""

        msg = (
            f"🎯 **MATCH PREDICTION**\n"
            f"🏠 {home_team.title()}  vs  {away_team.title()} ✈️\n"
            f"{'─' * 35}\n"
            f"📊 Win Probabilities:\n"
            f"  {home_team.title()}: **{result['home_win_pct']}%**\n"
            f"  Draw: **{result['draw_pct']}%**\n"
            f"  {away_team.title()}: **{result['away_win_pct']}%**\n\n"
            f"⚽ Expected Goals (xG):\n"
            f"  {home_team.title()}: {result['home_xg']}\n"
            f"  {away_team.title()}: {result['away_xg']}\n\n"
            f"🏆 Most Likely Score: **{result['most_likely_score']}** "
            f"({result['most_likely_prob']}% probability)\n\n"
            f"📋 Recent Form:\n"
            f"  {home_team.title()}: {home_form}\n"
            f"  {away_team.title()}: {away_form}"
            f"{fallback_note}"
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

        stats = fd.get_team_stats(team)

        if not stats:
            dispatcher.utter_message(
                text=f"⚠️ Couldn't find stats for **{team}**. Check the team name and try again."
            )
            return []

        form_str = pred.format_form(stats.get("form", []))
        fallback_note = "\n_(Estimated data — API key may not be set)_" if stats.get("_fallback") else ""
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
            f"{fallback_note}"
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

        s1 = fd.get_team_stats(team1)
        s2 = fd.get_team_stats(team2)

        if not s1 or not s2:
            dispatcher.utter_message(
                text=f"⚠️ Couldn't fetch stats for both teams. Check the names and try again."
            )
            return []

        form1 = pred.format_form(s1.get("form", []))
        form2 = pred.format_form(s2.get("form", []))

        def _edge(v1, v2, higher_is_better=True):
            if higher_is_better:
                return "🔥" if v1 > v2 else ("🔥" if v2 > v1 else "=")
            else:
                return "🔥" if v1 < v2 else ("🔥" if v2 < v1 else "=")

        t1n = s1["team"]
        t2n = s2["team"]
        scored_edge1 = "🔥" if s1["avg_goals_scored"] > s2["avg_goals_scored"] else ""
        scored_edge2 = "🔥" if s2["avg_goals_scored"] > s1["avg_goals_scored"] else ""
        conceded_edge1 = "🔥" if s1["avg_goals_conceded"] < s2["avg_goals_conceded"] else ""
        conceded_edge2 = "🔥" if s2["avg_goals_conceded"] < s1["avg_goals_conceded"] else ""

        msg = (
            f"⚔️ **TEAM COMPARISON**\n"
            f"{'─' * 35}\n"
            f"{'Stat':<22} {t1n:<18} {t2n}\n"
            f"{'─' * 35}\n"
            f"{'Avg Goals Scored':<22} {s1['avg_goals_scored']:<8} {scored_edge1:<4}   {s2['avg_goals_scored']} {scored_edge2}\n"
            f"{'Avg Goals Conceded':<22} {s1['avg_goals_conceded']:<8} {conceded_edge1:<4}   {s2['avg_goals_conceded']} {conceded_edge2}\n"
            f"{'Last 10: W/D/L':<22} {s1['won']}/{s1['drawn']}/{s1['lost']:<8}   {s2['won']}/{s2['drawn']}/{s2['lost']}\n\n"
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

        league_raw = _get_league(tracker)
        if not league_raw:
            # Try to infer from message text
            text = tracker.latest_message.get("text", "")
            league_raw = fd.resolve_league(text)

        if not league_raw:
            dispatcher.utter_message(
                text="Which league? Try:\n"
                     "  **show Premier League table**\n"
                     "  **La Liga standings**\n"
                     "Supported: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Super League"
            )
            return []

        standings = fd.get_standings(league_raw)

        if not standings:
            dispatcher.utter_message(
                text=f"⚠️ Couldn't fetch standings for **{league_raw}**. "
                     "Make sure the API key is set in .env and the league name is correct."
            )
            return []

        rows = "\n".join(
            f"  {r['position']}. {r['team']:<25} Pts: {r['points']}  "
            f"({r['won']}W/{r.get('draw', r.get('drawn', 0))}D/{r['lost']}L)  "
            f"GD: {r['gd']}"
            for r in standings[:5]
        )

        msg = (
            f"🏆 **{league_raw} — Top 5 Standings**\n"
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

        stats = fd.get_team_stats(team)
        if not stats:
            dispatcher.utter_message(
                text=f"⚠️ Couldn't fetch form data for **{team}**."
            )
            return []

        form_str = pred.format_form(stats.get("form", []))
        matches = stats.get("recent_matches", [])

        match_lines = []
        team_norm = fd._normalise_team(team)
        for m in matches[:5]:
            hg = m.get("home_goals", "?")
            ag = m.get("away_goals", "?")
            home = m["home_team"]
            away = m["away_team"]
            date = m.get("date", "")
            comp = m.get("competition", "")

            # Determine result from team's perspective
            is_home = team_norm in home.lower()
            if hg == "?" or ag == "?":
                result_icon = "❓"
            elif hg == ag:
                result_icon = "⬜"
            elif (is_home and hg > ag) or (not is_home and ag > hg):
                result_icon = "✅"
            else:
                result_icon = "❌"

            match_lines.append(
                f"  {result_icon} {date}  {home} {hg}-{ag} {away}  ({comp})"
            )

        matches_text = "\n".join(match_lines) if match_lines else "  No recent match details available."
        fallback_note = "\n_(Estimated data — API key may not be set)_" if stats.get("_fallback") else ""

        msg = (
            f"📋 **{stats['team']} — Recent Form**\n"
            f"{'─' * 35}\n"
            f"Last 5 results: {form_str}\n\n"
            f"Recent Matches:\n{matches_text}"
            f"{fallback_note}"
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

        h2h = fd.get_head_to_head(team1, team2)

        if not h2h:
            dispatcher.utter_message(
                text=f"⚠️ No head-to-head data found for **{team1}** vs **{team2}**.\n"
                     "This may be because both teams haven't met recently or the API key is not set."
            )
            return []

        recent_lines = []
        for m in h2h.get("recent_h2h", [])[:5]:
            hg = m.get("home_goals", "?")
            ag = m.get("away_goals", "?")
            date = m.get("date", "")
            recent_lines.append(f"  {date}  {m['home_team']} {hg}-{ag} {m['away_team']}")

        recent_text = "\n".join(recent_lines) if recent_lines else "  No recent meetings found in API data."

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
