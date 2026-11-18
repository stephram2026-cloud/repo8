#!/bin/bash
# usage: term.sh <stack.sh|prestack.sh> <worker container> [key]
S=$1; W=$2; K=$3
out=$(./$S exec ${K:+-e RD_KEY=$K} -- python /tools/p3.py start 60); echo "$out"
jid=$(echo "$out" | grep ^JOB | cut -d' ' -f2)
docker kill -s TERM $W >/dev/null; echo "SIGTERM sent to worker"
./$S exec ${K:+-e RD_KEY=$K} -- python /tools/p3.py watch $jid 40 61 2>&1 | cut -c1-1500
docker logs $W 2>&1 | grep -v "leaning registries" | tail -8 | cut -c1-400
