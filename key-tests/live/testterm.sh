#!/bin/bash
# Proof: POST /api/data_sources/<id>/test answers "success" when the test job itself failed (worker shut down mid-test).
# usage: testterm.sh <stack.sh|prestack.sh> <worker container> [api key]
S=$1; W=$2; K=$3
( sleep 4; docker kill -s TERM $W >/dev/null; echo "[SIGTERM sent to worker $W]" ) &
./$S exec ${K:+-e RD_KEY=$K} -- python /tools/p6.py term
wait
docker logs $W 2>&1 | grep -i "test_connection\|ShutDown\|Job OK\|exception raised" | tail -4 | cut -c1-260
