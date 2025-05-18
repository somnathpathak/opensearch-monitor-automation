#!/bin/bash

# Configuration
OPENSEARCH_URL="https://localhost:9200"
USERNAME="admin"
PASSWORD="admin"
INDICES=("index_a" "index_b" "index_c")
KEYWORDS=("error" "failure" "critical")

echo "[INFO] Checking if OpenSearch is reachable at $OPENSEARCH_URL..."
curl -k -u "$USERNAME:$PASSWORD" -s "$OPENSEARCH_URL" > /dev/null

if [ $? -ne 0 ]; then
  echo "[ERROR] OpenSearch is not reachable at $OPENSEARCH_URL"
  echo "        Ensure port-forwarding is active:"
  echo "        kubectl port-forward svc/my-first-cluster 9200 -n opensearch"
  exit 1
fi

# Insert documents into indices
for i in "${!INDICES[@]}"; do
  index="${INDICES[$i]}"
  keyword="${KEYWORDS[$i]}"

  echo "[INFO] Inserting test documents into index: $index"
  for j in $(seq 1 10); do
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    doc=$(jq -n --arg msg "$keyword message $j" --arg ts "$timestamp" \
        '{message: $msg, timestamp: $ts}')
    
    curl -k -u "$USERNAME:$PASSWORD" -s -X POST "$OPENSEARCH_URL/$index/_doc" \
      -H 'Content-Type: application/json' -d "$doc" > /dev/null
  done
done

echo "[INFO] All test documents inserted successfully."
