"""Register the container leader and wake it for dashboard tasks."""
import json
import sys
import uuid

from clawteam.spawn.registry import register_agent
from clawteam.team.leader_watcher import LeaderWatcher
from clawteam.team.manager import TeamManager


class DashboardWatcher(LeaderWatcher):
    def _signature(self, snapshot):
        # Upstream omits pending tasks, so New Task otherwise waits for a heartbeat.
        state = json.loads(super()._signature(snapshot))
        state['pending'] = snapshot['pending']
        return json.dumps(state, sort_keys=True, ensure_ascii=False)


def prepare(team):
    config = TeamManager.get_team(team)
    if config is None:
        config = TeamManager.create_team(team, 'leader', uuid.uuid4().hex[:12])
    leader = TeamManager.get_leader_name(team)
    member = next(member for member in config.members if member.name == leader)
    register_agent(team, leader, 'tmux', tmux_target=f'clawteam-{team}:{leader}')
    print(leader, member.agent_id)


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare(sys.argv[2])
    elif sys.argv[1] == 'watch':
        DashboardWatcher(sys.argv[2], sys.argv[3], interval=5,
                         heartbeat_interval=3600, redis_mode='off', verbose=True).run()
    else:
        raise SystemExit('Expected prepare TEAM or watch TEAM LEADER')
