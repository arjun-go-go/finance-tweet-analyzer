#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/run"
LOG_DIR="$ROOT_DIR/logs"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
CELERY_QUEUES="${CELERY_QUEUES:-analysis,prediction,ingest,embed,report,default}"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

mkdir -p "$RUN_DIR" "$LOG_DIR"

services=(backend frontend worker beat)

pid_file() {
  case "$1" in
    backend) echo "$RUN_DIR/backend.pid" ;;
    frontend) echo "$RUN_DIR/frontend.pid" ;;
    worker) echo "$RUN_DIR/celery_worker.pid" ;;
    beat) echo "$RUN_DIR/celery_beat.pid" ;;
    *) return 1 ;;
  esac
}

log_file() {
  case "$1" in
    backend) echo "$LOG_DIR/backend.log" ;;
    frontend) echo "$LOG_DIR/frontend.log" ;;
    worker) echo "$LOG_DIR/celery_worker.log" ;;
    beat) echo "$LOG_DIR/celery_beat.log" ;;
    *) return 1 ;;
  esac
}

process_pattern() {
  case "$1" in
    backend) echo "uvicorn app.main:app.*--port ${BACKEND_PORT}" ;;
    frontend) echo "next-server|next.*start.*--port ${FRONTEND_PORT}" ;;
    worker) echo "celery.*app.celery_app worker" ;;
    beat) echo "celery.*app.celery_app beat" ;;
    *) return 1 ;;
  esac
}

is_pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

service_pid() {
  local file
  file="$(pid_file "$1")"
  [[ -f "$file" ]] && tr -d '[:space:]' < "$file"
}

is_service_running() {
  local pid
  pid="$(service_pid "$1" || true)"
  is_pid_running "$pid"
}

start_service() {
  local service="$1"
  local pid_file_path log_file_path
  pid_file_path="$(pid_file "$service")"
  log_file_path="$(log_file "$service")"

  if is_service_running "$service"; then
    echo "$service already running (pid $(service_pid "$service"))"
    return 0
  fi

  rm -f "$pid_file_path"

  case "$service" in
    backend)
      (
        cd "$ROOT_DIR"
        nohup uv run uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > "$log_file_path" 2>&1 &
        echo $! > "$pid_file_path"
      )
      ;;
    frontend)
      (
        cd "$ROOT_DIR/frontend"
        nohup npm run start -- --hostname "$FRONTEND_HOST" --port "$FRONTEND_PORT" > "$log_file_path" 2>&1 &
        echo $! > "$pid_file_path"
      )
      ;;
    worker)
      (
        cd "$ROOT_DIR"
        nohup uv run celery -A app.celery_app worker -Q "$CELERY_QUEUES" -l info > "$log_file_path" 2>&1 &
        echo $! > "$pid_file_path"
      )
      ;;
    beat)
      (
        cd "$ROOT_DIR"
        nohup uv run celery -A app.celery_app beat -l info > "$log_file_path" 2>&1 &
        echo $! > "$pid_file_path"
      )
      ;;
  esac

  sleep 1
  if is_service_running "$service"; then
    echo "$service started (pid $(service_pid "$service"))"
  else
    echo "$service failed to start; see $log_file_path" >&2
    return 1
  fi
}

stop_service() {
  local service="$1"
  local pid pid_file_path pattern
  pid_file_path="$(pid_file "$service")"
  pid="$(service_pid "$service" || true)"

  if is_pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    for _ in {1..15}; do
      if ! is_pid_running "$pid"; then
        break
      fi
      sleep 1
    done
    if is_pid_running "$pid"; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  fi

  pattern="$(process_pattern "$service")"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    pkill -f "$pattern" >/dev/null 2>&1 || true
  fi

  rm -f "$pid_file_path"
  echo "$service stopped"
}

status_service() {
  local service="$1"
  local pid
  pid="$(service_pid "$service" || true)"
  if is_pid_running "$pid"; then
    printf "%-8s running pid=%s log=%s\n" "$service" "$pid" "$(log_file "$service")"
  else
    printf "%-8s stopped log=%s\n" "$service" "$(log_file "$service")"
  fi
}

start_all() {
  start_service backend
  start_service worker
  start_service beat
  start_service frontend
}

stop_all() {
  stop_service frontend
  stop_service beat
  stop_service worker
  stop_service backend
}

status_all() {
  for service in "${services[@]}"; do
    status_service "$service"
  done
}

health_check() {
  local backend_url="${BACKEND_HEALTH_URL:-http://127.0.0.1:${BACKEND_PORT}/api/health}"
  local frontend_url="${FRONTEND_HEALTH_URL:-http://127.0.0.1:${FRONTEND_PORT}/}"

  echo "backend:  $backend_url"
  curl -fsS "$backend_url" || {
    echo
    echo "backend health failed" >&2
    return 1
  }
  echo

  echo "frontend: $frontend_url"
  curl -fsSI "$frontend_url" >/dev/null || {
    echo "frontend health failed" >&2
    return 1
  }
  echo "frontend ok"
}

show_logs() {
  local service="${1:-}"
  if [[ -z "$service" || "$service" == "all" ]]; then
    tail -n 80 -f "$LOG_DIR"/backend.log "$LOG_DIR"/frontend.log "$LOG_DIR"/celery_worker.log "$LOG_DIR"/celery_beat.log
    return 0
  fi
  log_file "$service" >/dev/null
  tail -n 120 -f "$(log_file "$service")"
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/manage.sh start|stop|restart|status|health
  bash scripts/manage.sh start|stop|restart|status backend|frontend|worker|beat
  bash scripts/manage.sh logs [backend|frontend|worker|beat|all]

Environment overrides:
  BACKEND_PORT=8000 FRONTEND_PORT=3000 CELERY_QUEUES=analysis,prediction,ingest,embed,report,default
EOF
}

command="${1:-}"
target="${2:-}"

case "$command" in
  start)
    if [[ -n "$target" ]]; then start_service "$target"; else start_all; fi
    ;;
  stop)
    if [[ -n "$target" ]]; then stop_service "$target"; else stop_all; fi
    ;;
  restart)
    if [[ -n "$target" ]]; then
      stop_service "$target"
      start_service "$target"
    else
      stop_all
      start_all
    fi
    ;;
  status)
    if [[ -n "$target" ]]; then status_service "$target"; else status_all; fi
    ;;
  health)
    health_check
    ;;
  logs)
    show_logs "$target"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "Unknown command: $command" >&2
    usage >&2
    exit 2
    ;;
esac
