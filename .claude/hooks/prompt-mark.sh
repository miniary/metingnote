#!/usr/bin/env bash
# 껍데기. 내용은 ~/.claude/skills/todo-guard/scripts/prompt-mark.sh 에 한 벌만 둔다.
#   exec 가 아니라 source 로 부른다. exec 는 bash 를 한 번 더 띄우는데
#   윈도우에서 그 한 번이 0.6초다. 도구를 부를 때마다 붙는 시간이다
#   투두가드를 설치하지 않은 팀원은 본체가 없으므로 아무것도 하지 않고 통과한다
f="$HOME/.claude/skills/todo-guard/scripts/prompt-mark.sh"
[ -f "$f" ] || exit 0
. "$f"
