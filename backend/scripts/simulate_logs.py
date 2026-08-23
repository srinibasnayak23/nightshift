#!/usr/bin/env python3
"""
Nightshift Log Stream Simulator (Phase 1: The Observer)

Simulates continuous, realistic microservice logs (info, warn, error)
and POSTs them to the /logs/ingest endpoint at random intervals (2-5s).

Usage:
    python scripts/simulate_logs.py
    python scripts/simulate_logs.py --url http://localhost:8000/logs/ingest --min-delay 1.5 --max-delay 3.5
"""

import argparse
import datetime
import json
import random
import sys
import time
import urllib.error
import urllib.request

# Realistic mock log templates per service and level
MOCK_LOG_DATA = {
    "auth-service": {
        "info": [
            "User authentication successful for user_id={user_id} via OAuth2 (28ms)",
            "JWT token refreshed successfully for session_id={session_id}",
            "API key validated for client_id={client_id}",
            "Password reset request initiated for user_id={user_id}",
            "User session established from IP {ip_addr}",
        ],
        "warn": [
            "Multiple failed login attempts ({count}) detected for IP {ip_addr}",
            "JWT token near expiration (remaining: 45s) for user_id={user_id}",
            "Rate limit threshold reached (82%) for client_id={client_id}",
            "Unusual login location detected for user_id={user_id} from {ip_addr}",
        ],
        "error": [
            "Invalid cryptographic signature on authorization header from {ip_addr}",
            "LDAP identity provider timeout after 5000ms",
            "Redis session store connection refused on 10.0.1.45:6379",
            "OAuth2 provider certificate validation failed",
        ],
    },
    "payment-gateway": {
        "info": [
            "Payment intent pi_{hex_id} confirmed for amount ${amount:.2f} USD",
            "Refund ref_{hex_id} processed successfully for order #{order_id}",
            "Webhook event payment_intent.succeeded dispatched to subscriber",
            "Stripe token verification succeeded in 115ms",
        ],
        "warn": [
            "Payment gateway response latency high: {latency}ms (threshold: 800ms)",
            "Idempotency key collision detected for transaction #{hex_id}; returning cached state",
            "Card issuer returned decline code 'insufficient_funds' for user_id={user_id}",
        ],
        "error": [
            "Payment processor returned 500 Internal Server Error during charge capture",
            "Database deadlock encountered during ledger debit transaction #{order_id}",
            "TLS handshake failure connecting to banking gateway endpoint",
        ],
    },
    "order-processor": {
        "info": [
            "Order #{order_id} created with {item_count} items (total: ${amount:.2f})",
            "Order #{order_id} transitioned from PENDING to PROCESSING",
            "Fulfillment batch #{batch_id} queued to warehouse dispatcher",
            "Customer receipt email enqueued for order #{order_id}",
        ],
        "warn": [
            "Order queue depth elevated: {queue_depth} messages pending processing",
            "Slow database query on orders table: {latency}ms",
            "Inventory lock reservation approaching expiration (15s remaining) for order #{order_id}",
        ],
        "error": [
            "Failed to finalize order #{order_id}: OptimisticLockException on inventory",
            "Order processing worker crashed: OutOfMemoryError on worker-04",
            "Kafka message deserialization error on topic 'order.events.v1'",
        ],
    },
    "inventory-api": {
        "info": [
            "Stock level decremented by {count} for SKU-{sku_id} (remaining: {stock})",
            "Inventory reconciliation sync completed with warehouse-west",
            "Catalog cache warmed up: 14,200 SKUs loaded into Redis",
        ],
        "warn": [
            "SKU-{sku_id} stock level below minimum safety threshold (remaining: {low_stock})",
            "Warehouse sync batch delayed by {latency}s due to upstream queue pressure",
            "High concurrency lock contention on SKU-{sku_id}",
        ],
        "error": [
            "Database connection timeout connecting to primary PostgreSQL cluster",
            "Corrupt inventory record encountered for SKU-{sku_id}: null quantity",
            "Third-party supplier catalog feed HTTP 503 Service Unavailable",
        ],
    },
    "notification-worker": {
        "info": [
            "Transactional email dispatched to user_{user_id}@example.com via SES",
            "Push notification delivered to {count} devices for alert #{hex_id}",
            "SMS notification delivered via Twilio in 320ms",
        ],
        "warn": [
            "Email bounce rate elevated: 3.8% over last 15 minutes",
            "FCM push notification queue latency: {latency}ms",
            "SMS provider rate limit threshold reached (80%)",
        ],
        "error": [
            "Amazon SES credentials rejected: InvalidClientTokenId",
            "RabbitMQ connection lost on amqp://notification-mq:5672",
            "APNS certificate expired for iOS push notifications",
        ],
    },
    "ingress-router": {
        "info": [
            "GET /api/v1/products 200 OK ({latency_short}ms) - {ip_addr}",
            "POST /api/v1/checkout 202 Accepted ({latency}ms) - {ip_addr}",
            "GET /health 200 OK (2ms) - K8s Liveness Probe",
            "GET /ws/logs 101 Switching Protocols - {ip_addr}",
        ],
        "warn": [
            "Elevated response latency ({latency}ms) on POST /api/v1/search",
            "Client {ip_addr} sent malformed query headers; request sanitized",
            "TLS certificate for *.api.nightshift.io expires in 12 days",
        ],
        "error": [
            "504 Gateway Timeout: Upstream backend-worker-02 did not respond in 30000ms",
            "502 Bad Gateway: Upstream connection refused on port 8080",
            "Nginx worker process terminated unexpectedly (signal 9)",
        ],
    },
}

SERVICES = list(MOCK_LOG_DATA.keys())
LEVEL_WEIGHTS = [("info", 0.65), ("warn", 0.25), ("error", 0.10)]


def generate_sample_message(service: str, level: str) -> str:
    """Generate a realistic randomized message for a given service and level."""
    templates = MOCK_LOG_DATA[service][level]
    template = random.choice(templates)
    return template.format(
        user_id=random.randint(1000, 99999),
        session_id=f"sess_{random.randint(100000, 999999)}",
        client_id=f"app_{random.choice(['ios', 'android', 'web', 'cli'])}_{random.randint(10, 99)}",
        ip_addr=f"{random.choice([10, 172, 192])}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}",
        count=random.randint(2, 8),
        hex_id=f"{random.randint(0x100000, 0xFFFFFF):06x}",
        order_id=random.randint(10000, 99999),
        batch_id=random.randint(100, 999),
        amount=round(random.uniform(9.99, 499.99), 2),
        item_count=random.randint(1, 6),
        queue_depth=random.randint(850, 4200),
        latency=random.randint(450, 2800),
        latency_short=random.randint(12, 95),
        sku_id=f"{random.randint(1000, 9999)}",
        stock=random.randint(20, 250),
        low_stock=random.randint(1, 4),
    )


def choose_level() -> str:
    """Pick log level according to realistic distribution (65% info, 25% warn, 10% error)."""
    levels, weights = zip(*LEVEL_WEIGHTS)
    return random.choices(levels, weights=weights, k=1)[0]


def format_console_log(timestamp: str, service: str, level: str, message: str, status_code: int) -> str:
    """Format console output with ANSI color codes."""
    color_map = {
        "info": "\033[92m[INFO ]\033[0m",
        "warn": "\033[93m[WARN ]\033[0m",
        "error": "\033[91m[ERROR]\033[0m",
    }
    level_tag = color_map.get(level, f"[{level.upper()}]")
    status_tag = f"\033[90m({status_code})\033[0m"
    return f"{timestamp} | {level_tag} \033[96m{service:<19}\033[0m | {message} {status_tag}"


def post_log(url: str, payload: dict) -> int:
    """Post JSON payload to ingest endpoint using standard urllib."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Nightshift-Simulator/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status


def main() -> None:
    # Ensure stdout/stderr handle UTF-8 cleanly on Windows
    if sys.platform == "win32" and sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(
        description="Nightshift Real-Time Log Simulator (Phase 1)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8000/logs/ingest",
        help="Target log ingestion URL",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=2.0,
        help="Minimum delay between logs in seconds",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=5.0,
        help="Maximum delay between logs in seconds",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Number of log entries to generate (0 = run indefinitely)",
    )

    args = parser.parse_args()

    print("=" * 80)
    print(" [*] Nightshift AI SRE -- Log Ingestion Simulator")
    print(f" Target Endpoint: {args.url}")
    print(f" Interval Range : {args.min_delay}s - {args.max_delay}s")
    print(f" Target Count   : {'Unlimited (Ctrl+C to stop)' if args.count == 0 else args.count}")
    print("=" * 80)

    sent_count = 0
    try:
        while True:
            # Generate fake log payload
            service = random.choice(SERVICES)
            level = choose_level()
            message = generate_sample_message(service, level)
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

            payload = {
                "timestamp": timestamp,
                "service": service,
                "level": level,
                "message": message,
            }

            try:
                status_code = post_log(args.url, payload)
                sent_count += 1
                print(format_console_log(timestamp, service, level, message, status_code))
            except urllib.error.HTTPError as http_err:
                print(
                    f"\033[91m[HTTP ERROR]\033[0m Failed to POST log to {args.url}: HTTP {http_err.code} - {http_err.reason}",
                    file=sys.stderr,
                )
            except urllib.error.URLError as url_err:
                print(
                    f"\033[91m[CONN ERROR]\033[0m Could not connect to {args.url} ({url_err.reason}). Is the FastAPI server running?",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(f"\033[91m[ERROR]\033[0m Unexpected error: {exc}", file=sys.stderr)

            if args.count > 0 and sent_count >= args.count:
                print(f"\n[+] Completed sending {sent_count} log entries.")
                break

            # Sleep for random interval
            sleep_time = random.uniform(args.min_delay, args.max_delay)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        print(f"\n\n[!] Log simulator stopped by user. Total logs sent: {sent_count}")
        sys.exit(0)


if __name__ == "__main__":
    main()

