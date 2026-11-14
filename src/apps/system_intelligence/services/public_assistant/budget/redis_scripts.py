"""The Redis Lua scripts that reserve, reconcile and release a budget atomically (``cache_store`` runs them)."""

_RESERVE_SCRIPT = """
local current_raw = redis.call('GET', KEYS[1])
local current = tonumber(current_raw or '0')
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local window_ms = tonumber(ARGV[3])
local proposed_window_id = ARGV[4]
if limit > 0 and current + amount > limit then
  return -1
end

local budget_ttl
local window_id
if current_raw then
  redis.call('INCRBY', KEYS[1], amount)
  budget_ttl = redis.call('PTTL', KEYS[1])
  if budget_ttl <= 0 then
    budget_ttl = window_ms
    redis.call('PEXPIRE', KEYS[1], budget_ttl)
  end
  window_id = redis.call('GET', KEYS[2]) or proposed_window_id
else
  budget_ttl = window_ms
  window_id = proposed_window_id
  redis.call('PSETEX', KEYS[1], budget_ttl, amount)
end

-- All state for one fixed budget window shares its remaining lifetime. A
-- reservation must never survive the counter it was charged to, otherwise a
-- late reconcile could alter the next window.
redis.call('PSETEX', KEYS[2], budget_ttl, window_id)
redis.call('PSETEX', KEYS[3], budget_ttl, tostring(amount) .. ':' .. window_id)
return current + amount
"""

_RECONCILE_SCRIPT = """
local reservation = redis.call('GET', KEYS[3])
if not reservation then
  return 0
end
local separator = string.find(reservation, ':', 1, true)
if not separator then
  redis.call('DEL', KEYS[3])
  return 0
end
local reserved = tonumber(string.sub(reservation, 1, separator - 1))
local reservation_window_id = string.sub(reservation, separator + 1)
local active_window_id = redis.call('GET', KEYS[2])
if not reserved or not active_window_id or
   active_window_id ~= reservation_window_id or
   redis.call('EXISTS', KEYS[1]) == 0 then
  redis.call('DEL', KEYS[3])
  return 0
end
local actual = tonumber(ARGV[1])
local delta = actual - reserved
if delta ~= 0 then
  redis.call('INCRBY', KEYS[1], delta)
end
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current < 0 then
  local ttl = redis.call('PTTL', KEYS[1])
  if ttl > 0 then
    redis.call('PSETEX', KEYS[1], ttl, 0)
  else
    redis.call('DEL', KEYS[1])
    redis.call('DEL', KEYS[2])
  end
end
redis.call('DEL', KEYS[3])
return 1
"""

_RELEASE_SCRIPT = """
local reservation = redis.call('GET', KEYS[3])
if not reservation then
  return 0
end
local separator = string.find(reservation, ':', 1, true)
if not separator then
  redis.call('DEL', KEYS[3])
  return 0
end
local reserved = tonumber(string.sub(reservation, 1, separator - 1))
local reservation_window_id = string.sub(reservation, separator + 1)
local active_window_id = redis.call('GET', KEYS[2])
if not reserved or not active_window_id or
   active_window_id ~= reservation_window_id or
   redis.call('EXISTS', KEYS[1]) == 0 then
  redis.call('DEL', KEYS[3])
  return 0
end
redis.call('INCRBY', KEYS[1], -reserved)
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current < 0 then
  local ttl = redis.call('PTTL', KEYS[1])
  if ttl > 0 then
    redis.call('PSETEX', KEYS[1], ttl, 0)
  else
    redis.call('DEL', KEYS[1])
    redis.call('DEL', KEYS[2])
  end
end
redis.call('DEL', KEYS[3])
return 1
"""
