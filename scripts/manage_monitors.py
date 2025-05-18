import json
import os
import requests
from opensearchpy import OpenSearch

DEFAULT_LOCAL_PATH = os.path.join(os.path.dirname(__file__), '..', 'input', 'monitors.json')

def load_monitors():
    remote_url = os.getenv("MONITORS_URL")
    if remote_url:
        print(f"[INFO] Fetching monitor config from remote URL: {remote_url}")
        try:
            response = requests.get(remote_url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[ERROR] Failed to fetch remote monitors.json: {e}")
            return []
    else:
        print(f"[INFO] Loading monitor config from local file: {DEFAULT_LOCAL_PATH}")
        try:
            with open(DEFAULT_LOCAL_PATH, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load local monitors.json: {e}")
            return []

    monitors = data.get("Monitors", [])
    print(f"[INFO] Loaded {len(monitors)} monitor(s) from configuration")
    return monitors


def connect_to_opensearch():
    host = os.environ.get("OPENSEARCH_HOST", "localhost")
    port = int(os.environ.get("OPENSEARCH_PORT", 9200))
    auth = (os.environ.get("OPENSEARCH_USER", "admin"), os.environ.get("OPENSEARCH_PASS", "admin"))

    print(f"[INFO] Connecting to OpenSearch at {host}:{port}")
    client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=False,
        ssl_show_warn=False
    )
    return client


def get_notification_channels(client):
    try:
        response = client.transport.perform_request(
            method="GET",
            url="/_plugins/_notifications/channels"
        )
        return response.get("channel_list", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch notification channels: {e}")
        return []


def resolve_channel_id(client, channel_name):
    channels = get_notification_channels(client)
    for ch in channels:
        if ch.get("name") == channel_name:
            return ch.get("config_id")
    print(f"[WARNING] Notification channel not found: {channel_name}")
    return None


def get_existing_monitors(client):
    monitors = []
    try:
        response = client.alerting.search_monitor({"query": {"match_all": {}}})
        for hit in response.get("hits", {}).get("hits", []):
            monitor = hit.get("_source", {})
            monitors.append({"id": hit["_id"], "name": monitor.get("name")})
        print(f"[INFO] Found {len(monitors)} existing monitor(s) in OpenSearch")
    except Exception as e:
        print(f"[ERROR] Error fetching existing monitors: {e}")
    return monitors


def delete_monitor(client, monitor_id):
    try:
        client.alerting.delete_monitor(monitor_id=monitor_id)
        print(f"[INFO] Deleted monitor ID: {monitor_id}")
    except Exception as e:
        print(f"[ERROR] Failed to delete monitor ID '{monitor_id}': {e}")


def create_monitor(client, monitor_def):
    monitor_name = monitor_def["Monitor_Name"]
    index = monitor_def["Index"]
    keyword = monitor_def["Text2Scan_in_Message"]
    time_window = monitor_def["Time2Scan"]
    channel_name = monitor_def["notification_channel"]

    channel_id = resolve_channel_id(client, channel_name)
    if not channel_id:
        print(f"[ERROR] Notification channel '{channel_name}' not found. Skipping monitor '{monitor_name}'")
        return

    monitor_body = {
        "type": "monitor",
        "name": monitor_name,
        "enabled": True,
        "schedule": {
            "period": {
                "interval": int(time_window.rstrip("m")),
                "unit": "MINUTES"
            }
        },
        "inputs": [
            {
                "search": {
                    "indices": [index],
                    "query": {
                        "size": 0,
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "match_phrase": {
                                            "message": keyword
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        ],
        "triggers": [
            {
                "name": f"{monitor_name} Trigger",
                "severity": "1",
                "condition": {
                    "script": {
                        "source": "ctx.results[0].hits.total.value > 0",
                        "lang": "painless"
                    }
                },
                "actions": [
                    {
                        "name": "Slack Notification",
                        "destination_id": channel_id,
                        "message_template": {
                            "source": (
                                "🚨 Monitor {{ctx.monitor.name}} just entered an alert state. Please investigate the issue.\n"
                                "- Trigger: {{ctx.trigger.name}}\n"
                                "- Severity: {{ctx.trigger.severity}}\n"
                                "- Period start: {{ctx.periodStart}}\n"
                                "- Period end: {{ctx.periodEnd}}"
                            ),
                            "lang": "mustache"
                        },
                        "throttle_enabled": False
                    }
                ]
            }
        ]
    }

    try:
        client.alerting.create_monitor(body=monitor_body)
        print(f"[INFO] Created monitor: {monitor_name}")
    except Exception as e:
        print(f"[ERROR] Failed to create monitor '{monitor_name}': {e}")


def sync_monitors(client, desired_monitors):
    existing = get_existing_monitors(client)
    existing_map = {m["name"]: m["id"] for m in existing}
    desired_map = {m["Monitor_Name"]: m for m in desired_monitors}

    for monitor_name in desired_map:
        if monitor_name not in existing_map:
            print(f"[INFO] Creating monitor: {monitor_name}")
            create_monitor(client, desired_map[monitor_name])

    for monitor_name in existing_map:
        if monitor_name not in desired_map:
            print(f"[INFO] Deleting orphaned monitor: {monitor_name}")
            delete_monitor(client, existing_map[monitor_name])


def main():
    monitors = load_monitors()
    if not monitors:
        print("[INFO] No monitors found in input file.")
        return

    print("[INFO] Parsed Monitors:")
    for m in monitors:
        print(f"  - {m['Monitor_Name']} (Index: {m['Index']}, Keyword: {m['Text2Scan_in_Message']}, Time: {m['Time2Scan']}, Channel: {m['notification_channel']})")

    client = connect_to_opensearch()
    info = client.info()
    print(f"[INFO] Connected to OpenSearch {info['version']['number']} @ {info['cluster_name']}")

    print("[INFO] Syncing monitors...")
    sync_monitors(client, monitors)

    response = client.alerting.search_monitor({"query": {"match_all": {}}})
    monitors = response.get("hits", {}).get("hits", [])
    print(f"[INFO] Total monitors after sync: {len(monitors)}")
    for hit in monitors:
        monitor = hit.get("_source", {})
        print(f"  - {monitor.get('name')}")


if __name__ == "__main__":
    main()
