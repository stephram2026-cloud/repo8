#!/bin/bash
# usage: canceldead.sh <stack.sh|prestack.sh> <worker container> <server container> [api key]
S=$1; W=$2; SRV=$3; K=$4
out=$(./$S exec ${K:+-e RD_KEY=$K} -- python /tools/p8.py start); echo "$out"
jid=$(echo "$out" | grep ^JOB | cut -d' ' -f2)
docker kill -s KILL $W >/dev/null; t0=$(date +%s); echo "worker container SIGKILLed"
for at in 80 135; do
  while [ $(( $(date +%s) - t0 )) -lt $at ]; do sleep 1; done
  echo "--- ${at}s after the worker died: user clicks Cancel"
  ./$S exec ${K:+-e RD_KEY=$K} -- python /tools/p8.py cancel $jid
done
docker logs $SRV 2>&1 | grep -B1 -A1 "^ValueError\|^rq.exceptions" | tail -8
