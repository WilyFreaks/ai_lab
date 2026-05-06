import csv
import json
import os
import random
import re
import time
from configparser import ConfigParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")
SAMPLES_DIR = os.path.join(APP_ROOT, "samples")
SPOOL_ROOT = os.path.join(APP_ROOT, "var", "spool", "ai_lab")
GEN_LOG_DIR = os.path.join(SPOOL_ROOT, "ai_lab_log", "log_generation")
LOOKUPS_DIR = os.path.join(APP_ROOT, "lookups")

PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")

# TWAMP slice placeholders that inherit twamp#pca_twamp_csv#sample.csv#default.noise_stdev (delay/jitter only).
_TWAMP_DELAY_JITTER_NAME = re.compile(
    r"^slice\d+_(ul|dl|rt)_("
    r"dmin|dmax|dmean|dStdDev|dp25|dp50|dp75|dp95|dpLo|dpMi|dpHi|"
    r"jmin|jmax|jmean|jStdDev|jp25|jp50|jp75|jp95|jpLo|jpMi|jpHi|"
    r"dvmax|dvmean|dvp25|dvp50|dvp75|dvp95|dvpLo|dvpMi|dvpHi"
    r")$",
    re.I,
)

_TWAMP_SLICE_FROM_PLACEHOLDER = re.compile(r"^(slice\d+)_", re.I)


def twamp_slice_id_from_placeholder_key(placeholder_key):
    m = _TWAMP_SLICE_FROM_PLACEHOLDER.match(placeholder_key or "")
    return m.group(1) if m else None


def twamp_slice_noise_epsilons_for_placeholders(placeholders):
    """One standard-normal draw per slice per event: shared shift for all noisy TWAMP metrics in that slice."""
    eps = {}
    for ph in placeholders:
        sid = twamp_slice_id_from_placeholder_key(ph)
        if sid and sid not in eps:
            eps[sid] = random.gauss(0.0, 1.0)
    return eps


def stream_default_metric_prefix(prefix):
    parts = prefix.split("#", 3)
    if len(parts) != 4:
        return None
    return f"{parts[0]}#{parts[1]}#{parts[2]}#default"


def resolve_noise_stdev(cfg, section, prefix):
    own = f"{prefix}.noise_stdev"
    if cfg.has_option(section, own):
        return parse_float(cfg, section, own, default=0.0) or 0.0
    parts = prefix.split("#", 3)
    if len(parts) == 4 and parts[0] == "twamp" and parts[1] == "pca_twamp_csv":
        if _TWAMP_DELAY_JITTER_NAME.match(parts[3]):
            dp = stream_default_metric_prefix(prefix)
            if dp:
                return parse_float(cfg, section, f"{dp}.noise_stdev", default=0.0) or 0.0
    return 0.0


def format_pca_twamp_csv_metric(_placeholder, value):
    """PCA TWAMP CSV exports use integer cells (lab style); round after metric_value + noise."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return value


_PCA_TWAMP_TIME_KEYS = frozenset({"startTime", "timestamp"})


def normalize_pca_twamp_csv_replacements(replacements):
    """
    PCA TWAMP CSV cells are integer-only on the wire. Coerce numeric strings,
    floats, and any leftover metric outputs before templating.
    """
    for key, value in list(replacements.items()):
        if key in _PCA_TWAMP_TIME_KEYS:
            continue
        if isinstance(value, bool):
            continue
        if type(value) is int:
            continue
        if isinstance(value, float):
            replacements[key] = int(round(value))
            continue
        if isinstance(value, str):
            s = value.strip()
            if not s:
                continue
            try:
                replacements[key] = int(round(float(s)))
            except ValueError:
                pass


REGION_TZ = {
    "au": "Australia/Sydney",
    "jp": "Asia/Tokyo",
}

LIVE_CURSOR_KEY = "live_last_tick_epoch"
SEQUENCE_LAST_KEY = "sequence_last_value"
TWAMP_UL_LAST_STATE_KEY = "twamp_ul_lastpktseq_state_json"
IOS_BFD_LAST_EMIT_STATE_KEY = "ios_bfd_last_emit_state_json"
TWAMP_UL_FIRSTPKTSEQ_SEED = 5_000_000
# Cap how many minute ticks we process per scheduler pass when catching up (avoids a tight
# CPU loop if live_log was stopped for days). Override with AI_LAB_LIVE_CATCHUP_BATCH_MINUTES.
LIVE_CATCHUP_BATCH_MINUTES = max(
    1, int(os.environ.get("AI_LAB_LIVE_CATCHUP_BATCH_MINUTES", "120"))
)

def build_streams():
    return [
        {
            "index": "thousandeyes",
            "sourcetype": "cisco:thousandeyes:metric",
            "sample": os.path.join(
                SAMPLES_DIR, "thousandeyes", "cisco:thousandeyes:metric", "sample.json"
            ),
            "spool_dir": os.path.join(
                SPOOL_ROOT, "thousandeyes", "cisco_thousandeyes_metric"
            ),
        },
        {
            "index": "telemetry",
            "sourcetype": "cnc_interface_counter_json",
            "sample": os.path.join(
                SAMPLES_DIR, "telemetry", "cnc_interface_counter_json", "sample.json"
            ),
            "spool_dir": os.path.join(
                SPOOL_ROOT, "telemetry", "cnc_interface_counter_json"
            ),
        },
        {
            "index": "telemetry",
            "sourcetype": "cnc_srte_path_json",
            "sample": os.path.join(
                SAMPLES_DIR, "telemetry", "cnc_srte_path_json", "sample.txt"
            ),
            "spool_dir": os.path.join(SPOOL_ROOT, "telemetry", "cnc_srte_path_json"),
        },
        {
            "index": "telemetry",
            "sourcetype": "cnc_service_health_json",
            "sample": os.path.join(
                SAMPLES_DIR, "telemetry", "cnc_service_health_json", "sample.txt"
            ),
            "spool_dir": os.path.join(SPOOL_ROOT, "telemetry", "cnc_service_health_json"),
        },
        {
            "index": "ios",
            "sourcetype": "cisco:ios",
            "sample": os.path.join(
                SAMPLES_DIR, "ios", "cisco:ios", "sample_bfd.txt"
            ),
            "spool_dir": os.path.join(SPOOL_ROOT, "ios", "cisco_ios"),
            # Emit this sequence once per scenario activation when reroute starts.
            "scenario_reroute_start_once": "scenario_1",
        },
        {
            "index": "twamp",
            "sourcetype": "pca_twamp_csv",
            "sample": os.path.join(SAMPLES_DIR, "twamp", "pca_twamp_csv", "sample.csv"),
            "spool_dir": os.path.join(SPOOL_ROOT, "twamp", "pca_twamp_csv"),
        },
    ]


def stream_prefix_base(stream):
    sample_name = os.path.basename(stream["sample"])
    return f"{stream['index']}#{stream['sourcetype']}#{sample_name}#"


def telemetry_link_lookup_path():
    preferred = os.path.join(LOOKUPS_DIR, "router_if_connected_bidirectional.csv")
    if os.path.exists(preferred):
        return preferred
    return os.path.join(LOOKUPS_DIR, "router_if_connections_bidirectional.csv")


def load_telemetry_bidirectional_links():
    path = telemetry_link_lookup_path()
    if not os.path.exists(path):
        return []

    links = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r1 = str(row.get("router1", "")).strip()
            i1 = str(row.get("interface1", "")).strip()
            r2 = str(row.get("router2", "")).strip()
            i2 = str(row.get("interface2", "")).strip()
            if not (r1 and i1 and r2 and i2):
                continue
            links.append((r1, i1, r2, i2))
    return links


def telemetry_key(router_id, interface_name, direction):
    return (str(router_id).strip(), str(interface_name).strip(), str(direction).strip())


def index_telemetry_placeholders(placeholders):
    idx = {}
    for ph in placeholders:
        m = re.match(r"^(R\d+)_(.+)_(ifInPktsRate|ifOutPktsRate)$", ph)
        if not m:
            continue
        router_id = m.group(1)
        iface_token = m.group(2)
        direction = m.group(3)
        iface_name = iface_token
        if iface_name.startswith("Bundle_Ether"):
            iface_name = iface_name.replace("Bundle_Ether", "Bundle-Ether", 1)
        iface_name = iface_name.replace("_", "/")
        idx[telemetry_key(router_id, iface_name, direction)] = ph
    return idx


def telemetry_directional_min_receive_fraction(cfg, section):
    """Minimum peer ifIn as a fraction of local ifOut after post-processing (0..1). Baseline uses 0.99 (<=1% drop); scenario may set 0 to allow large intentional gaps."""
    pb = "telemetry#cnc_interface_counter_json#sample.json#"
    v = parse_float(cfg, section, f"{pb}directional_min_receive_fraction", default=None)
    if v is None:
        return 0.99
    return max(0.0, min(1.0, v))


def enforce_telemetry_directional_conservation(
    replacements, placeholder_index, links, cfg, section
):
    min_frac = telemetry_directional_min_receive_fraction(cfg, section)

    def _bounded_inbound(out_val, in_val):
        if out_val <= 0:
            return out_val
        lower = out_val * min_frac
        if in_val > out_val:
            return out_val
        if min_frac > 0 and in_val < lower:
            return lower
        return in_val

    for (r1, i1, r2, i2) in links:
        key_out_1 = telemetry_key(r1, i1, "ifOutPktsRate")
        key_in_2 = telemetry_key(r2, i2, "ifInPktsRate")
        ph_out_1 = placeholder_index.get(key_out_1)
        ph_in_2 = placeholder_index.get(key_in_2)
        if ph_out_1 and ph_in_2:
            out1 = float(replacements.get(ph_out_1, 0) or 0)
            in2 = float(replacements.get(ph_in_2, 0) or 0)
            replacements[ph_in_2] = round(_bounded_inbound(out1, in2), 6)

        key_out_2 = telemetry_key(r2, i2, "ifOutPktsRate")
        key_in_1 = telemetry_key(r1, i1, "ifInPktsRate")
        ph_out_2 = placeholder_index.get(key_out_2)
        ph_in_1 = placeholder_index.get(key_in_1)
        if ph_out_2 and ph_in_1:
            out2 = float(replacements.get(ph_out_2, 0) or 0)
            in1 = float(replacements.get(ph_in_1, 0) or 0)
            replacements[ph_in_1] = round(_bounded_inbound(out2, in1), 6)


def _new_cfg():
    return ConfigParser(interpolation=None, delimiters=("=",), strict=False)


def read_effective_conf():
    cfg = _new_cfg()
    if os.path.exists(DEFAULT_CONF):
        cfg.read(DEFAULT_CONF)
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def read_local_conf():
    cfg = _new_cfg()
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def write_local_conf(cfg):
    os.makedirs(os.path.dirname(LOCAL_CONF), exist_ok=True)
    with open(LOCAL_CONF, "w") as f:
        cfg.write(f)


def conf_file_signature(path):
    """
    Return a lightweight file signature for change detection.
    We use (mtime_ns, size) so long-running workers can detect config edits and
    refresh tick-time behavior without requiring a process restart.
    """
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return None


def effective_conf_signature():
    return (
        conf_file_signature(DEFAULT_CONF),
        conf_file_signature(LOCAL_CONF),
    )


def write_generation_log(event, **fields):
    os.makedirs(GEN_LOG_DIR, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": "live_log",
        "event": event,
    }
    payload.update(fields)
    path = os.path.join(
        GEN_LOG_DIR, f"log_generation_{int(time.time() * 1_000_000)}_{os.getpid()}.json"
    )
    with open(path, "w") as f:
        f.write(json.dumps(payload, separators=(",", ":")))
        f.write("\n")


def get_region_tz(cfg):
    region = cfg.get("baseline", "region", fallback="").strip().lower()
    tz_name = REGION_TZ.get(region, "UTC")
    return ZoneInfo(tz_name), region or "unknown"


def format_domain_timestamp(local_dt, _region):
    # ISO-style wall time with numeric offset (+0900 / +1000 / +1100) so Splunk strptime
    # matches reliably (CSV TWAMP had no TIME_FORMAT and mis-parsed "AEST" as ~1h fast).
    return local_dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def parse_float(cfg, section, key, default=None):
    try:
        return float(cfg.get(section, key))
    except Exception:
        return default


def clamp_probability(value):
    if value is None:
        return 1.0
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 1.0


def parse_int(cfg, section, key, default=None):
    try:
        return int(float(cfg.get(section, key)))
    except Exception:
        return default


def resolve_start_sequence():
    local_cfg = read_local_conf()
    return max(0, parse_int(local_cfg, "baseline", SEQUENCE_LAST_KEY, default=0) or 0)


def persist_last_sequence(value):
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    local_cfg.set("baseline", SEQUENCE_LAST_KEY, str(max(0, int(value))))
    write_local_conf(local_cfg)


def safe_int(value, default=None):
    try:
        return int(float(value))
    except Exception:
        return default


def safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def twamp_slice_prefixes(replacements):
    prefixes = set()
    for key in replacements:
        for direction in ("ul", "dl", "rt"):
            suffix = f"_{direction}_firstpktSeq"
            if key.endswith(suffix):
                prefixes.add(key[: -len(suffix)])
                break
    return sorted(p for p in prefixes if p)


def resolve_twamp_ul_last_state():
    local_cfg = read_local_conf()
    raw = local_cfg.get("baseline", TWAMP_UL_LAST_STATE_KEY, fallback="").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out = {}
    for key, value in parsed.items():
        seq = safe_int(value, default=None)
        if seq is None:
            continue
        out[str(key)] = max(0, seq)
    return out


def persist_twamp_ul_last_state(state):
    normalized = {}
    for key, value in (state or {}).items():
        seq = safe_int(value, default=None)
        if seq is None:
            continue
        normalized[str(key)] = max(0, seq)
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    local_cfg.set(
        "baseline",
        TWAMP_UL_LAST_STATE_KEY,
        json.dumps(normalized, separators=(",", ":")),
    )
    write_local_conf(local_cfg)


def resolve_ios_bfd_last_emit_state():
    local_cfg = read_local_conf()
    raw = local_cfg.get("baseline", IOS_BFD_LAST_EMIT_STATE_KEY, fallback="").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out = {}
    for key, value in parsed.items():
        activation = safe_int(value, default=None)
        if activation is None or activation <= 0:
            continue
        out[str(key)] = int(activation)
    return out


def persist_ios_bfd_last_emit_state(state):
    normalized = {}
    for key, value in (state or {}).items():
        activation = safe_int(value, default=None)
        if activation is None or activation <= 0:
            continue
        normalized[str(key)] = int(activation)
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    local_cfg.set(
        "baseline",
        IOS_BFD_LAST_EMIT_STATE_KEY,
        json.dumps(normalized, separators=(",", ":")),
    )
    write_local_conf(local_cfg)


def weekend_multiplier(local_dt, configured):
    if configured is None:
        return 1.0

    weekday = local_dt.weekday()  # Mon=0 .. Sun=6
    hour = local_dt.hour + (local_dt.minute / 60.0)

    weekend_weight = 0.0
    if weekday == 4 and hour >= 18.0:
        weekend_weight = min(max((hour - 18.0) / 6.0, 0.0), 1.0)
    elif weekday == 5:
        weekend_weight = 1.0
    elif weekday == 6:
        if hour < 18.0:
            weekend_weight = 1.0
        else:
            weekend_weight = max(0.0, 1.0 - ((hour - 18.0) / 6.0))

    return 1.0 + ((configured - 1.0) * weekend_weight)


def interpolated_hourly_peak_rate(cfg, section, prefix, local_dt):
    current_hour = local_dt.hour
    next_hour = (current_hour + 1) % 24
    current_rate = parse_float(
        cfg, section, f"{prefix}.peak_rate_{current_hour:02d}", default=None
    )
    next_rate = parse_float(cfg, section, f"{prefix}.peak_rate_{next_hour:02d}", default=None)
    if current_rate is None:
        return None
    if next_rate is None:
        next_rate = current_rate
    minute_progress = (local_dt.minute + (local_dt.second / 60.0)) / 60.0
    return current_rate + ((next_rate - current_rate) * minute_progress)


def metric_value(cfg, section, prefix, local_dt, twamp_shared_noise_epsilon=None):
    base = parse_float(cfg, section, prefix, default=None)
    if base is None:
        return None

    dmin = parse_float(cfg, section, f"{prefix}.daily_min", default=None)
    dmax = parse_float(cfg, section, f"{prefix}.daily_max", default=None)
    rate = interpolated_hourly_peak_rate(cfg, section, prefix, local_dt)

    if dmin is not None and dmax is not None and rate is not None:
        value = dmin + (dmax - dmin) * rate
    else:
        value = base

    wmul = parse_float(cfg, section, f"{prefix}.weekend_multiplier", default=None)
    value *= weekend_multiplier(local_dt, wmul)

    outlier_p = parse_float(cfg, section, f"{prefix}.outlier_probability", default=0.0) or 0.0
    if outlier_p > 0 and random.random() < outlier_p:
        omin = parse_float(cfg, section, f"{prefix}.outlier_min", default=value)
        omax = parse_float(cfg, section, f"{prefix}.outlier_max", default=value)
        if omin is not None and omax is not None:
            value = random.uniform(min(omin, omax), max(omin, omax))

    noise = resolve_noise_stdev(cfg, section, prefix)
    if noise > 0:
        if twamp_shared_noise_epsilon is not None:
            value += noise * twamp_shared_noise_epsilon
        else:
            value += random.gauss(0.0, noise)

    return value


def apply_twamp_ul_packet_sequence(
    replacements, stream, twamp_ul_last_state, cfg, section, local_dt
):
    stream_key = f"{stream['index']}#{stream['sourcetype']}"
    prefix_base = stream_prefix_base(stream)
    session_name = str(replacements.get("session_name", "")).strip()
    prefixes = twamp_slice_prefixes(replacements)
    if not prefixes:
        return

    for prefix in prefixes:
        for direction in ("ul", "dl", "rt"):
            first_key = f"{prefix}_{direction}_firstpktSeq"
            last_key = f"{prefix}_{direction}_lastpktSeq"
            rx_key = f"{prefix}_{direction}_rxpkts"
            expected_key = f"{prefix}_{direction}_rxpkts_expected"
            drop_rate_key = f"{prefix}_{direction}_rxpkts_drop_rate"
            rxbytes_key = f"{prefix}_{direction}_rxbytes"

            required = (first_key, last_key, rx_key)
            if not all(field in replacements for field in required):
                continue

            state_key_parts = [stream_key, prefix, direction]
            if session_name:
                state_key_parts.insert(1, session_name)
            state_key = ":".join(state_key_parts)

            prev_last = twamp_ul_last_state.get(state_key)
            if prev_last is None:
                prev_last = TWAMP_UL_FIRSTPKTSEQ_SEED - 1

            expected_rx = safe_int(replacements.get(expected_key), default=None)
            if expected_rx is None:
                mv = metric_value(cfg, section, f"{prefix_base}{expected_key}", local_dt)
                if mv is not None:
                    expected_rx = int(round(mv))
            if expected_rx is None:
                expected_rx = safe_int(replacements.get(rx_key), default=None)
            if expected_rx is None:
                seeded_first = safe_int(replacements.get(first_key), default=None)
                seeded_last = safe_int(replacements.get(last_key), default=None)
                if (
                    seeded_first is not None
                    and seeded_last is not None
                    and seeded_last >= seeded_first
                ):
                    expected_rx = seeded_last - seeded_first
                else:
                    expected_rx = 0
            expected_rx = max(0, int(expected_rx))

            dr_raw = replacements.get(drop_rate_key)
            if dr_raw is None or str(dr_raw).strip() == "":
                mv_dr = metric_value(cfg, section, f"{prefix_base}{drop_rate_key}", local_dt)
                drop_rate = float(mv_dr) if mv_dr is not None else 0.0
            else:
                drop_rate = safe_float(dr_raw, default=0.0)
                if drop_rate is None:
                    drop_rate = 0.0
            drop_rate = max(0.0, min(1.0, float(drop_rate)))

            first_pkt = int(prev_last) + 1
            last_pkt = first_pkt + expected_rx
            rx_pkts = int(round(expected_rx * (1.0 - drop_rate)))
            rx_pkts = max(0, min(expected_rx, rx_pkts))

            replacements[first_key] = first_pkt
            replacements[last_key] = last_pkt
            replacements[expected_key] = expected_rx
            replacements[drop_rate_key] = drop_rate
            replacements[rx_key] = rx_pkts
            replacements[rxbytes_key] = rx_pkts * 546
            lostpkts_key = f"{prefix}_{direction}_lostpkts"
            lostperc_key = f"{prefix}_{direction}_lostperc"
            lost = max(0, int(expected_rx) - int(rx_pkts))
            replacements[lostpkts_key] = lost
            if expected_rx > 0:
                # Integer percent 0-100 on the wire (dashboards use 0-100 loss% charts).
                replacements[lostperc_key] = int(
                    round(100.0 * float(lost) / float(expected_rx))
                )
            else:
                replacements[lostperc_key] = 0
            twamp_ul_last_state[state_key] = last_pkt


def telemetry_rate_max_step(cfg, section, prefix):
    dmin = parse_float(cfg, section, f"{prefix}.daily_min", default=None)
    dmax = parse_float(cfg, section, f"{prefix}.daily_max", default=None)
    noise = parse_float(cfg, section, f"{prefix}.noise_stdev", default=0.0) or 0.0
    range_step = 0.0
    if dmin is not None and dmax is not None:
        range_step = abs(dmax - dmin) * 0.25
    return max(range_step, noise * 6.0)


def smooth_telemetry_rate(prev_value, new_value, max_step):
    if prev_value is None:
        return new_value
    if max_step <= 0:
        return new_value
    delta = new_value - prev_value
    if abs(delta) <= max_step:
        return new_value
    return prev_value + (max_step if delta > 0 else -max_step)


def coerce_placeholder(
    cfg,
    section,
    prefix,
    placeholder,
    local_dt,
    sequence,
    stream,
    region,
    telemetry_rate_state,
    twamp_slice_noise=None,
):
    if placeholder == "timestamp":
        return format_domain_timestamp(local_dt, region)
    if placeholder == "startTime":
        return format_domain_timestamp(local_dt, region)
    if placeholder == "sequence":
        return sequence
    if placeholder == "sourcetype":
        return stream["sourcetype"]
    if placeholder == "intervalms":
        ib = stream_prefix_base(stream)
        eis = parse_int(cfg, section, f"{ib}event_interval_sec", default=None)
        if eis and eis > 0:
            return eis * 1000
        raw_value = cfg.get(section, prefix, fallback=None)
        if raw_value is not None:
            try:
                return int(float(str(raw_value).strip()))
            except Exception:
                pass
        return 0

    twamp_eps = None
    if twamp_slice_noise:
        sid = twamp_slice_id_from_placeholder_key(placeholder)
        if sid:
            twamp_eps = twamp_slice_noise.get(sid)

    value = metric_value(cfg, section, prefix, local_dt, twamp_eps)
    if value is not None:
        if placeholder.endswith("ifOutPktsRate") or placeholder.endswith("ifInPktsRate"):
            # Keep packet-rate transitions gradual for both baseline and scenario windows so
            # degraded-path reduction and bypass-path increase evolve smoothly over ticks.
            max_step = telemetry_rate_max_step(cfg, section, prefix)
            prev_value = telemetry_rate_state.get(prefix)
            value = smooth_telemetry_rate(prev_value, value, max_step)
            telemetry_rate_state[prefix] = value
        if placeholder in ("availability", "http_status_code"):
            return int(round(value))
        if stream.get("sourcetype") == "pca_twamp_csv":
            return format_pca_twamp_csv_metric(placeholder, value)
        return round(value, 6)

    # Fallback for non-numeric template values (for example JSON fragments used in .txt samples).
    raw_value = cfg.get(section, prefix, fallback=None)
    if raw_value is None:
        return 0
    s = str(raw_value).strip()
    if stream.get("sourcetype") == "pca_twamp_csv":
        try:
            return int(round(float(s)))
        except ValueError:
            return s
    return s


def scenario_happening_probability(cfg, section, prefix_base):
    key = f"{prefix_base}scenario_happening_probability"
    return clamp_probability(parse_float(cfg, section, key, default=1.0))


def sample_extension(sample_path):
    ext = os.path.splitext(sample_path)[1].lower()
    return ext or ".txt"


def csv_header_and_body(full_text, sample_path):
    """
    Split a CSV sample into the single header line (written once per output file)
    and the remaining template body (rendered for each event).
    """
    text = full_text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        raise ValueError(
            f"CSV sample must contain a header line and body: {sample_path}"
        )
    header_line, body = text.split("\n", 1)
    if not body.strip():
        raise ValueError(
            f"CSV sample must include at least one data line after header: {sample_path}"
        )
    return header_line, body


def render_template(template_text, replacements, sample_path):
    ext = sample_extension(sample_path)

    def _format_csv_number(n):
        if isinstance(n, bool):
            return str(n)
        if isinstance(n, int):
            return str(n)
        if isinstance(n, float):
            return str(int(round(n)))
        return str(n)

    def _sub(match):
        key = match.group(1)
        value = replacements.get(key, "")
        if ext == ".csv" and isinstance(value, (int, float)):
            return _format_csv_number(value)
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    rendered = PLACEHOLDER_RE.sub(_sub, template_text)
    if ext == ".json":
        # Keep NDJSON compact output for JSON templates.
        return [json.dumps(json.loads(rendered), separators=(",", ":"))]
    if ext in (".txt", ".csv", ".xml"):
        return [rendered.rstrip("\n")]
    raise ValueError(f"Unsupported sample extension for template rendering: {sample_path}")


def clone_cfg(cfg):
    out = _new_cfg()
    for section in cfg.sections():
        out.add_section(section)
        for key, value in cfg.items(section):
            out.set(section, key, value)
    return out


def active_scenarios_for_tick(cfg, tick_ts):
    names = []
    if not cfg.has_section("scenarios"):
        return names
    for key, value in cfg.items("scenarios"):
        if not key.endswith("_activated"):
            continue
        try:
            activated = int(float(value))
        except Exception:
            activated = 0
        if activated <= 0:
            continue
        scenario_name = key[: -len("_activated")]
        fault_start = parse_int(cfg, "scenarios", f"{scenario_name}_fault_start", default=0) or 0
        fault_duration = parse_int(
            cfg, "scenarios", f"{scenario_name}_fault_duration", default=0
        ) or 0
        start = activated + (fault_start * 60)
        end = start + (fault_duration * 60)
        if tick_ts < start:
            continue
        if fault_duration > 0 and tick_ts >= end:
            continue
        if not cfg.has_section(scenario_name):
            continue
        names.append(scenario_name)
    names.sort()
    return names


def effective_cfg_for_tick(base_cfg, tick_ts):
    cfg = clone_cfg(base_cfg)
    active = active_scenarios_for_tick(base_cfg, tick_ts)
    if not cfg.has_section("baseline"):
        cfg.add_section("baseline")
    for scenario_name in active:
        for key, value in base_cfg.items(scenario_name):
            if "#" not in key:
                continue
            cfg.set("baseline", key, value)
    return cfg, active


def scenario_start_epoch(cfg, scenario_name):
    if not cfg.has_section("scenarios"):
        return None
    activated = parse_int(cfg, "scenarios", f"{scenario_name}_activated", default=0) or 0
    if activated <= 0:
        return None
    fault_start = parse_int(cfg, "scenarios", f"{scenario_name}_fault_start", default=0) or 0
    return activated + (fault_start * 60)


def scenario_reroute_progress(cfg, scenario_name, tick_ts):
    # Primary key format (requested): prefixed telemetry scenario key.
    ramp_minutes = parse_int(
        cfg,
        scenario_name,
        "telemetry#cnc_interface_counter_json#sample.json#reroute_ramp_minutes",
        default=None,
    )
    if ramp_minutes is None:
        # Backward compatibility for transitional unprefixed key.
        ramp_minutes = parse_int(cfg, scenario_name, "reroute_ramp_minutes", default=None)
    if ramp_minutes is None:
        ramp_minutes = parse_int(
            cfg,
            scenario_name,
            "telemetry#cnc_interface_counter_json#sample.json#ramp_minutes",
            default=0,
        )
    ramp_minutes = ramp_minutes or 0
    if ramp_minutes <= 0:
        return 1.0
    start = scenario_start_epoch(cfg, scenario_name)
    if start is None:
        return 1.0
    start_delay_minutes = parse_int(
        cfg,
        scenario_name,
        "telemetry#cnc_interface_counter_json#sample.json#reroute_start_minutes",
        default=None,
    )
    if start_delay_minutes is None:
        start_delay_minutes = parse_int(
            cfg, scenario_name, "reroute_start_minutes", default=0
        )
    start_delay_minutes = max(0, start_delay_minutes or 0)
    ramp_start = start + (int(start_delay_minutes) * 60)
    elapsed_min = max(0.0, float(tick_ts - ramp_start) / 60.0)
    return max(0.0, min(1.0, elapsed_min / float(ramp_minutes)))


def scenario_reroute_start_epoch(cfg, scenario_name):
    start = scenario_start_epoch(cfg, scenario_name)
    if start is None:
        return None
    start_delay_minutes = parse_int(
        cfg,
        scenario_name,
        "telemetry#cnc_interface_counter_json#sample.json#reroute_start_minutes",
        default=None,
    )
    if start_delay_minutes is None:
        start_delay_minutes = parse_int(cfg, scenario_name, "reroute_start_minutes", default=0)
    start_delay_minutes = max(0, start_delay_minutes or 0)
    return start + (int(start_delay_minutes) * 60)


SLICE_TELEMETRY_RATE_KEYS = {
    # Impacted path slices (R2<->R3<->R5<->R7)
    "1002": [
        "r2_hundredgige0_0_0_2_ifoutpktsrate",
        "r3_hundredgige0_0_0_2_ifinpktsrate",
        "r3_hundredgige0_0_0_2_ifoutpktsrate",
        "r2_hundredgige0_0_0_2_ifinpktsrate",
        "r3_hundredgige0_0_0_1_ifoutpktsrate",
        "r5_hundredgige0_0_2_1_ifinpktsrate",
        "r5_hundredgige0_0_2_1_ifoutpktsrate",
        "r3_hundredgige0_0_0_1_ifinpktsrate",
    ],
    "1003": [
        "r5_hundredgige0_0_2_0_ifoutpktsrate",
        "r7_hundredgige0_0_0_1_ifinpktsrate",
        "r7_hundredgige0_0_0_1_ifoutpktsrate",
        "r5_hundredgige0_0_2_0_ifinpktsrate",
    ],
    # Reroute target slices (R2<->R4<->R6<->R7)
    "1001": [
        "r2_hundredgige0_0_0_0_ifoutpktsrate",
        "r4_hundredgige0_0_2_1_ifinpktsrate",
        "r4_hundredgige0_0_2_1_ifoutpktsrate",
        "r2_hundredgige0_0_0_0_ifinpktsrate",
    ],
    "1004": [
        "r4_hundredgige0_0_2_0_ifoutpktsrate",
        "r6_hundredgige0_1_0_0_ifinpktsrate",
        "r6_hundredgige0_1_0_0_ifoutpktsrate",
        "r4_hundredgige0_0_2_0_ifinpktsrate",
        "r6_hundredgige0_0_0_0_ifoutpktsrate",
        "r7_hundredgige0_1_0_0_ifinpktsrate",
        "r7_hundredgige0_1_0_0_ifoutpktsrate",
        "r6_hundredgige0_0_0_0_ifinpktsrate",
    ],
}


def parse_csv_list(cfg, section, key):
    raw = cfg.get(section, key, fallback="")
    if raw is None:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def apply_scenario_telemetry_reroute(base_cfg, stream_cfg, active_scenarios, tick_ts):
    """
    Apply scenario-driven reroute to telemetry packet-rate keys using slice groups:
    - reroute_from_slice: slices to reduce
    - reroute_to_slice: slices to increase
    - reroute_pct: target percent shift
    - reroute_ramp_minutes: linear ramp duration
    """
    out_cfg = clone_cfg(stream_cfg)
    section = "baseline"
    if not base_cfg.has_section(section):
        return out_cfg

    prefix_base = "telemetry#cnc_interface_counter_json#sample.json#"
    for scenario_name in active_scenarios:
        if not base_cfg.has_section(scenario_name):
            continue

        reroute_pct = parse_float(
            base_cfg,
            scenario_name,
            "telemetry#cnc_interface_counter_json#sample.json#reroute_pct",
            default=None,
        )
        if reroute_pct is None:
            reroute_pct = parse_float(base_cfg, scenario_name, "reroute_pct", default=0.0)
        reroute_pct = reroute_pct or 0.0
        reroute_pct = max(0.0, min(100.0, reroute_pct))
        if reroute_pct <= 0:
            continue

        from_slices = parse_csv_list(
            base_cfg,
            scenario_name,
            "telemetry#cnc_interface_counter_json#sample.json#reroute_from_slice",
        )
        if not from_slices:
            from_slices = parse_csv_list(base_cfg, scenario_name, "reroute_from_slice")
        to_slices = parse_csv_list(
            base_cfg,
            scenario_name,
            "telemetry#cnc_interface_counter_json#sample.json#reroute_to_slice",
        )
        if not to_slices:
            to_slices = parse_csv_list(base_cfg, scenario_name, "reroute_to_slice")
        if not from_slices and not to_slices:
            continue

        progress = scenario_reroute_progress(base_cfg, scenario_name, tick_ts)
        pct = (reroute_pct / 100.0) * progress

        from_keys = []
        seen_from = set()
        for sid in from_slices:
            for key_suffix in SLICE_TELEMETRY_RATE_KEYS.get(str(sid), []):
                full_key = f"{prefix_base}{key_suffix}"
                if full_key in seen_from:
                    continue
                seen_from.add(full_key)
                from_keys.append(full_key)

        to_keys = []
        seen_to = set()
        for sid in to_slices:
            for key_suffix in SLICE_TELEMETRY_RATE_KEYS.get(str(sid), []):
                full_key = f"{prefix_base}{key_suffix}"
                if full_key in seen_to:
                    continue
                seen_to.add(full_key)
                to_keys.append(full_key)

        if from_keys or to_keys:
            # 1) Reduce "from" keys by reroute percentage (ramped), and track total moved volume.
            total_moved = 0.0
            adjusted_values = {}
            baseline_values = {}
            for key in from_keys:
                baseline_raw = base_cfg.get(section, key, fallback=None)
                if baseline_raw is None:
                    continue
                try:
                    baseline_value = float(str(baseline_raw).strip())
                except Exception:
                    continue
                moved = baseline_value * pct
                value = baseline_value - moved
                total_moved += moved
                baseline_values[key] = baseline_value
                adjusted_values[key] = value

            # 2) Redistribute moved volume to "to" keys by baseline-weight share.
            # This models reroute as traffic conservation rather than independent +pct uplift.
            to_baselines = {}
            to_total = 0.0
            for key in to_keys:
                baseline_raw = base_cfg.get(section, key, fallback=None)
                if baseline_raw is None:
                    continue
                try:
                    baseline_value = float(str(baseline_raw).strip())
                except Exception:
                    continue
                to_baselines[key] = baseline_value
                to_total += baseline_value

            if to_baselines and total_moved > 0:
                equal_share = total_moved / float(len(to_baselines))
                for key, baseline_value in to_baselines.items():
                    if to_total > 0:
                        weight = baseline_value / to_total
                        added = total_moved * weight
                    else:
                        added = equal_share
                    baseline_values[key] = baseline_value
                    adjusted_values[key] = baseline_value + added

            # 3) Write adjusted values and scale daily bounds by value/baseline ratio.
            for key, value in adjusted_values.items():
                baseline_value = baseline_values.get(key, 0.0)
                out_cfg.set(section, key, str(value))
                ratio = 1.0
                if abs(baseline_value) > 1e-12:
                    ratio = value / baseline_value
                for suffix in (".daily_min", ".daily_max"):
                    bound_key = f"{key}{suffix}"
                    base_bound_raw = base_cfg.get(section, bound_key, fallback=None)
                    if base_bound_raw is None:
                        continue
                    try:
                        base_bound = float(str(base_bound_raw).strip())
                    except Exception:
                        continue
                    out_cfg.set(section, bound_key, str(base_bound * ratio))

        # Optional immediate directional gap rule (applies as soon as scenario is active),
        # independent from reroute_start/ramp timing.
        gap_pct = parse_float(
            base_cfg,
            scenario_name,
            "telemetry#cnc_interface_counter_json#sample.json#immediate_gap_pct",
            default=None,
        )
        if gap_pct is None:
            gap_pct = parse_float(base_cfg, scenario_name, "immediate_gap_pct", default=0.0)
        gap_pct = max(0.0, min(100.0, gap_pct or 0.0))
        if gap_pct > 0:
            out_suffix = base_cfg.get(
                scenario_name,
                "telemetry#cnc_interface_counter_json#sample.json#immediate_gap_out_key",
                fallback=None,
            )
            if not out_suffix:
                out_suffix = base_cfg.get(
                    scenario_name, "immediate_gap_out_key", fallback=None
                )
            in_suffix = base_cfg.get(
                scenario_name,
                "telemetry#cnc_interface_counter_json#sample.json#immediate_gap_in_key",
                fallback=None,
            )
            if not in_suffix:
                in_suffix = base_cfg.get(
                    scenario_name, "immediate_gap_in_key", fallback=None
                )
            if out_suffix and in_suffix:
                out_key = f"{prefix_base}{str(out_suffix).strip().lower()}"
                in_key = f"{prefix_base}{str(in_suffix).strip().lower()}"
                out_value = parse_float(out_cfg, section, out_key, default=None)
                if out_value is not None:
                    in_value = out_value * (1.0 - (gap_pct / 100.0))
                    out_cfg.set(section, in_key, str(in_value))
                    for suffix in (".daily_min", ".daily_max"):
                        out_bound = parse_float(
                            out_cfg, section, f"{out_key}{suffix}", default=None
                        )
                        if out_bound is None:
                            continue
                        out_cfg.set(
                            section,
                            f"{in_key}{suffix}",
                            str(out_bound * (1.0 - (gap_pct / 100.0))),
                        )

    return out_cfg


def apply_scenario_thousandeyes_back_to_baseline(
    base_cfg, stream_cfg, active_scenarios, tick_ts
):
    """
    For ThousandEyes metrics, allow scenario values to return to baseline after a delay,
    then ramp linearly to baseline over a configured duration.
    """
    out_cfg = clone_cfg(stream_cfg)
    section = "baseline"
    if not base_cfg.has_section(section):
        return out_cfg

    metric_prefix = "thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms"
    key_main = metric_prefix
    key_min = f"{metric_prefix}.daily_min"
    key_max = f"{metric_prefix}.daily_max"
    key_start_delay = f"{metric_prefix}.back_to_baseline_start_minutes"
    key_ramp = f"{metric_prefix}.back_to_baseline_ramp_minutes"

    for scenario_name in active_scenarios:
        if not base_cfg.has_section(scenario_name):
            continue
        if not base_cfg.has_option(scenario_name, key_start_delay) and not base_cfg.has_option(
            scenario_name, key_ramp
        ):
            continue
        start_epoch = scenario_start_epoch(base_cfg, scenario_name)
        if start_epoch is None:
            continue

        start_delay = parse_int(base_cfg, scenario_name, key_start_delay, default=0) or 0
        ramp_minutes = parse_int(base_cfg, scenario_name, key_ramp, default=0) or 0
        delay_epoch = start_epoch + (max(0, int(start_delay)) * 60)

        if tick_ts < delay_epoch:
            progress = 0.0
        elif ramp_minutes <= 0:
            progress = 1.0
        else:
            elapsed_min = max(0.0, float(tick_ts - delay_epoch) / 60.0)
            progress = max(0.0, min(1.0, elapsed_min / float(ramp_minutes)))

        for key in (key_main, key_min, key_max):
            baseline_value = parse_float(base_cfg, section, key, default=None)
            scenario_value = parse_float(out_cfg, section, key, default=None)
            if baseline_value is None or scenario_value is None:
                continue
            # progress=0 => keep scenario value; progress=1 => return to baseline.
            blended = scenario_value + ((baseline_value - scenario_value) * progress)
            out_cfg.set(section, key, str(blended))

    return out_cfg


def minute_due_for_interval(ts, interval_min):
    if interval_min <= 0:
        return False
    minute_of_hour = datetime.fromtimestamp(ts, tz=timezone.utc).minute
    return (minute_of_hour % interval_min) == 0


def event_timestamps_for_tick(tick_ts, interval_min, event_interval_sec):
    """
    When event_interval_sec is unset: one event at tick_ts (minute cursor), unchanged behavior.
    When set: N events ending at tick_ts, spaced by event_interval_sec, covering the interval window
    (N = max(1, (interval_min * 60) // event_interval_sec)).
    """
    interval_min = max(1, int(interval_min or 1))
    if not event_interval_sec or event_interval_sec <= 0:
        return [tick_ts]
    span_sec = interval_min * 60
    n = span_sec // int(event_interval_sec)
    if n <= 0:
        n = 1
    return [tick_ts - (n - 1 - i) * int(event_interval_sec) for i in range(n)]


def generate_single_event(
    cfg, stream, ts, tzinfo, region, sequence, telemetry_rate_state, twamp_ul_last_state
):
    section = "baseline"
    prefix_base = stream_prefix_base(stream)

    with open(stream["sample"], "r") as f:
        full_text = f.read()

    ext = sample_extension(stream["sample"])
    if ext == ".csv":
        _, template_text = csv_header_and_body(full_text, stream["sample"])
    else:
        template_text = full_text

    placeholders = sorted(set(PLACEHOLDER_RE.findall(template_text)))
    local_dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tzinfo)
    replacements = {}
    twamp_slice_noise = None
    if stream.get("sourcetype") == "pca_twamp_csv":
        twamp_slice_noise = twamp_slice_noise_epsilons_for_placeholders(placeholders)
    for ph in placeholders:
        prefix = f"{prefix_base}{ph}"
        replacements[ph] = coerce_placeholder(
            cfg,
            section,
            prefix,
            ph,
            local_dt,
            sequence,
            stream,
            region,
            telemetry_rate_state,
            twamp_slice_noise,
        )

    if stream["index"] == "telemetry" and stream["sourcetype"] == "cnc_interface_counter_json":
        placeholder_index = index_telemetry_placeholders(placeholders)
        links = load_telemetry_bidirectional_links()
        if links:
            enforce_telemetry_directional_conservation(
                replacements, placeholder_index, links, cfg, section
            )
    apply_twamp_ul_packet_sequence(
        replacements, stream, twamp_ul_last_state, cfg, section, local_dt
    )
    if stream.get("sourcetype") == "pca_twamp_csv":
        normalize_pca_twamp_csv_replacements(replacements)

    return render_template(template_text, replacements, stream["sample"])


def write_stream_events(stream, events, csv_header_line=None):
    if not events:
        return None
    os.makedirs(stream["spool_dir"], exist_ok=True)
    output_ext = sample_extension(stream["sample"])
    output_path = os.path.join(
        stream["spool_dir"],
        f"live_{int(time.time() * 1_000_000)}_{os.getpid()}_{stream['index']}_{stream['sourcetype'].replace(':', '_')}{output_ext}",
    )
    wrote_header = False
    with open(output_path, "w") as out:
        for payload in events:
            if csv_header_line is not None and not wrote_header:
                out.write(csv_header_line + "\n")
                wrote_header = True
            out.write(payload)
            if not payload.endswith("\n"):
                out.write("\n")
    return output_path


def resolve_start_tick(base_cfg):
    anchor = parse_int(base_cfg, "baseline", "backfill_start_time", default=None)
    if anchor is None:
        return None, "missing baseline.backfill_start_time"

    first_tick = ((anchor + 59) // 60) * 60
    local_cfg = read_local_conf()
    last_tick = parse_int(local_cfg, "baseline", LIVE_CURSOR_KEY, default=None)
    if last_tick is not None:
        start_tick = max(first_tick, last_tick + 60)
        return start_tick, "resume_from_live_cursor"
    return first_tick, "start_from_backfill_anchor"


def persist_live_cursor(tick_ts):
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    local_cfg.set("baseline", LIVE_CURSOR_KEY, str(int(tick_ts)))
    write_local_conf(local_cfg)


def process_tick(tick_ts, sequence_state, base_cfg=None):
    # Reload from disk per tick unless caller provides an already-refreshed config.
    if base_cfg is None:
        base_cfg = read_effective_conf()
    if not base_cfg.has_section("baseline"):
        return 0, [], {}

    tzinfo, region = get_region_tz(base_cfg)
    effective_cfg, active_scenarios = effective_cfg_for_tick(base_cfg, tick_ts)

    emitted = 0
    per_stream_counts = {}
    for stream in build_streams():
        prefix_base = stream_prefix_base(stream)
        stream_cfg = effective_cfg
        custom_timestamps = None
        bfd_emit_state_update = None
        if active_scenarios:
            probability = scenario_happening_probability(
                effective_cfg, "baseline", prefix_base
            )
            if random.random() >= probability:
                stream_cfg = base_cfg
        if (
            stream_cfg is effective_cfg
            and active_scenarios
            and stream["index"] == "telemetry"
            and stream["sourcetype"] == "cnc_interface_counter_json"
        ):
            stream_cfg = apply_scenario_telemetry_reroute(
                base_cfg, stream_cfg, active_scenarios, tick_ts
            )
        if (
            stream_cfg is effective_cfg
            and active_scenarios
            and stream["index"] == "thousandeyes"
            and stream["sourcetype"] == "cisco:thousandeyes:metric"
        ):
            stream_cfg = apply_scenario_thousandeyes_back_to_baseline(
                base_cfg, stream_cfg, active_scenarios, tick_ts
            )

        interval = parse_int(stream_cfg, "baseline", f"{prefix_base}interval", default=1)
        interval = max(interval or 1, 1)
        event_interval_sec = parse_int(
            stream_cfg, "baseline", f"{prefix_base}event_interval_sec", default=None
        )
        if event_interval_sec is not None and event_interval_sec <= 0:
            event_interval_sec = None
        scenario_once_name = stream.get("scenario_reroute_start_once")
        if scenario_once_name:
            if scenario_once_name not in active_scenarios:
                continue
            activation = parse_int(
                base_cfg, "scenarios", f"{scenario_once_name}_activated", default=0
            ) or 0
            if activation <= 0:
                continue
            already_emitted = sequence_state["ios_bfd_last_emit_state"].get(
                scenario_once_name
            )
            if already_emitted == activation:
                continue
            reroute_start_epoch = scenario_reroute_start_epoch(base_cfg, scenario_once_name)
            if reroute_start_epoch is None or tick_ts < int(reroute_start_epoch):
                continue
            custom_timestamps = [int(reroute_start_epoch)]
            bfd_emit_state_update = (scenario_once_name, activation)
        elif not minute_due_for_interval(tick_ts, interval):
            continue

        timestamps = custom_timestamps or event_timestamps_for_tick(
            tick_ts, interval, event_interval_sec
        )
        all_event_objs = []
        csv_header_line = None
        if sample_extension(stream["sample"]) == ".csv":
            with open(stream["sample"], "r") as sf:
                csv_header_line, _ = csv_header_and_body(sf.read(), stream["sample"])
        for ts in timestamps:
            sequence_state["seq"] += 1
            part = generate_single_event(
                stream_cfg,
                stream,
                ts,
                tzinfo,
                region,
                sequence_state["seq"],
                sequence_state["telemetry_rate_state"],
                sequence_state["twamp_ul_last_state"],
            )
            all_event_objs.extend(part)
        event_count = len(all_event_objs)
        path = write_stream_events(stream, all_event_objs, csv_header_line=csv_header_line)
        if bfd_emit_state_update:
            scenario_name, activation = bfd_emit_state_update
            sequence_state["ios_bfd_last_emit_state"][scenario_name] = int(activation)
        emitted += event_count
        per_stream_counts[f"{stream['index']}#{stream['sourcetype']}"] = (
            per_stream_counts.get(f"{stream['index']}#{stream['sourcetype']}", 0)
            + event_count
        )
        eis_note = (
            f" event_interval_sec={event_interval_sec}" if event_interval_sec else ""
        )
        print(
            f"live_log: wrote {event_count} events to {path} "
            f"(tick={tick_ts} index={stream['index']} sourcetype={stream['sourcetype']} interval={interval}"
            f"{eis_note})",
            flush=True,
        )

    return emitted, active_scenarios, per_stream_counts


def next_minute_sleep_seconds():
    now = time.time()
    next_minute = ((int(now) // 60) + 1) * 60
    return max(0.2, next_minute - now)


def main():
    base_cfg = read_effective_conf()
    start_tick, start_reason = resolve_start_tick(base_cfg)
    if start_tick is None:
        print("live_log: missing baseline.backfill_start_time; skipping", flush=True)
        write_generation_log("skip_missing_backfill_start_time")
        return

    tzinfo, region = get_region_tz(base_cfg)
    start_sequence = resolve_start_sequence()
    print(
        f"live_log: starting minute scheduler start_tick={start_tick} "
        f"region={region} tz={tzinfo.key} reason={start_reason} start_sequence={start_sequence}",
        flush=True,
    )
    write_generation_log(
        "start",
        start_tick=start_tick,
        region=region,
        timezone=tzinfo.key,
        start_reason=start_reason,
        start_sequence=start_sequence,
    )

    cursor = int(start_tick)
    sequence_state = {
        "seq": int(start_sequence),
        "telemetry_rate_state": {},
        "twamp_ul_last_state": resolve_twamp_ul_last_state(),
        "ios_bfd_last_emit_state": resolve_ios_bfd_last_emit_state(),
    }
    last_effective_conf_sig = effective_conf_signature()

    while True:
        now_tick = (int(time.time()) // 60) * 60
        if cursor > now_tick:
            time.sleep(next_minute_sleep_seconds())
            continue

        total_emitted = 0
        active_seen = set()
        stream_totals = {}
        batch_start = cursor
        ticks_this_batch = 0
        while (
            cursor <= now_tick and ticks_this_batch < LIVE_CATCHUP_BATCH_MINUTES
        ):
            base_cfg = read_effective_conf()
            conf_sig = effective_conf_signature()
            if conf_sig != last_effective_conf_sig:
                # Apply config edits immediately: drop smoothing carry-over so new
                # per-interface rates and scenario overrides are reflected next tick.
                sequence_state["telemetry_rate_state"] = {}
                last_effective_conf_sig = conf_sig
                write_generation_log(
                    "effective_conf_changed",
                    tick=cursor,
                    default_conf_sig=str(conf_sig[0]),
                    local_conf_sig=str(conf_sig[1]),
                )
            emitted, active_scenarios, per_stream_counts = process_tick(
                cursor, sequence_state, base_cfg=base_cfg
            )
            total_emitted += emitted
            for name in active_scenarios:
                active_seen.add(name)
            for key, count in per_stream_counts.items():
                stream_totals[key] = stream_totals.get(key, 0) + count
            persist_live_cursor(cursor)
            cursor += 60
            ticks_this_batch += 1
        persist_last_sequence(sequence_state["seq"])
        persist_twamp_ul_last_state(sequence_state["twamp_ul_last_state"])
        persist_ios_bfd_last_emit_state(sequence_state["ios_bfd_last_emit_state"])

        write_generation_log(
            "tick_batch_processed",
            batch_start=batch_start,
            batch_end=cursor - 60,
            emitted_events=total_emitted,
            active_scenarios=sorted(active_seen),
            stream_totals=stream_totals,
        )
        if total_emitted == 0:
            print(
                f"live_log: tick batch {batch_start}->{now_tick} emitted no events",
                flush=True,
            )
        # Still behind wall clock: spread catch-up across passes so we do not peg one core.
        if cursor <= now_tick:
            time.sleep(
                float(os.environ.get("AI_LAB_LIVE_CATCHUP_COOLDOWN_SEC", "0.05"))
            )
            continue

        time.sleep(next_minute_sleep_seconds())


if __name__ == "__main__":
    main()
