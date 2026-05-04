import json
import os
import random
import re
import time
import csv
from configparser import ConfigParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")
SAMPLES_DIR = os.path.join(APP_ROOT, "samples")
SPOOL_ROOT = os.path.join(APP_ROOT, "var", "spool", "ai_lab")
GEN_LOG_DIR = os.path.join(SPOOL_ROOT, "ai_lab_log", "log_generation")


def _apply_sandbox_env():
    """
    When AI_LAB_SANDBOX_ROOT is set, write state and spool under that directory
    instead of the app local/ and var/spool paths (offline / pre-Splunk dry run).
    """
    global LOCAL_CONF, SPOOL_ROOT, GEN_LOG_DIR
    root = os.environ.get("AI_LAB_SANDBOX_ROOT", "").strip()
    if not root:
        return
    root = os.path.abspath(root)
    LOCAL_CONF = os.path.join(root, "ai_lab_scenarios.conf")
    SPOOL_ROOT = os.path.join(root, "spool", "ai_lab")
    GEN_LOG_DIR = os.path.join(SPOOL_ROOT, "ai_lab_log", "log_generation")
LOOKUPS_DIR = os.path.join(APP_ROOT, "lookups")
SEQUENCE_LAST_KEY = "sequence_last_value"
TWAMP_UL_LAST_STATE_KEY = "twamp_ul_lastpktseq_state_json"
TWAMP_UL_FIRSTPKTSEQ_SEED = 5_000_000

PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")

REGION_TZ = {
    "au": "Australia/Sydney",
    "jp": "Asia/Tokyo",
}

def build_streams():
    """Use current SPOOL_ROOT so sandbox env can redirect output paths."""
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
            "index": "twamp",
            "sourcetype": "pca_twamp_csv",
            "sample": os.path.join(SAMPLES_DIR, "twamp", "pca_twamp_csv", "sample.csv"),
            "spool_dir": os.path.join(SPOOL_ROOT, "twamp", "pca_twamp_csv"),
        },
    ]


def telemetry_link_lookup_path():
    # Prefer the newly introduced filename when present, but support the legacy one.
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


def interface_to_placeholder_token(interface_name):
    token = str(interface_name).strip()
    # Keep Bundle-Ether semantic token while converting path separators.
    token = token.replace("Bundle-Ether", "Bundle_Ether")
    token = token.replace("/", "_")
    return token


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
    pb = "telemetry#cnc_interface_counter_json#"
    v = parse_float(cfg, section, f"{pb}directional_min_receive_fraction", default=None)
    if v is None:
        return 0.99
    return max(0.0, min(1.0, v))


def enforce_telemetry_directional_conservation(
    replacements, placeholder_index, links, cfg, section
):
    # Enforce packet-loss-only model (no packet creation in transit). Baseline:
    # bound modeled drop rate under 1% per link direction via
    # telemetry#cnc_interface_counter_json#directional_min_receive_fraction = 0.99.
    # Scenario overlays may set that fraction to 0 to allow large intentional gaps.
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
    # ai_lab keys contain ":" characters; force "=" delimiter only.
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


def write_generation_log(event, **fields):
    os.makedirs(GEN_LOG_DIR, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": "backfill_log",
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
    # ISO-style wall time with numeric offset; must match default/props.conf TIME_FORMAT %z.
    return local_dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def parse_float(cfg, section, key, default=None):
    try:
        return float(cfg.get(section, key))
    except Exception:
        return default


def parse_int(cfg, section, key, default=None):
    try:
        return int(float(cfg.get(section, key)))
    except Exception:
        return default


def load_last_sequence():
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


def load_twamp_ul_last_state():
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
    local_cfg.set("baseline", TWAMP_UL_LAST_STATE_KEY, json.dumps(normalized, separators=(",", ":")))
    write_local_conf(local_cfg)


def weekend_multiplier(local_dt, configured):
    if configured is None:
        return 1.0
    # Smooth Fri->Sat and Sun->Mon transitions to avoid abrupt metric jumps.
    weekday = local_dt.weekday()  # Mon=0 .. Sun=6
    hour = local_dt.hour + (local_dt.minute / 60.0)

    weekend_weight = 0.0
    # Ramp up from Friday 18:00 to Saturday 00:00.
    if weekday == 4 and hour >= 18.0:
        weekend_weight = min(max((hour - 18.0) / 6.0, 0.0), 1.0)
    # Full weekend on Saturday.
    elif weekday == 5:
        weekend_weight = 1.0
    # Sunday: full weekend until 18:00, then ramp down to Monday 00:00.
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


# TWAMP slice placeholders that inherit twamp#pca_twamp_csv#default.noise_stdev (delay/jitter only).
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
    parts = prefix.split("#", 2)
    if len(parts) != 3:
        return None
    return f"{parts[0]}#{parts[1]}#default"


def resolve_noise_stdev(cfg, section, prefix):
    own = f"{prefix}.noise_stdev"
    if cfg.has_option(section, own):
        return parse_float(cfg, section, own, default=0.0) or 0.0
    parts = prefix.split("#", 2)
    if len(parts) == 3 and parts[0] == "twamp" and parts[1] == "pca_twamp_csv":
        if _TWAMP_DELAY_JITTER_NAME.match(parts[2]):
            dp = stream_default_metric_prefix(prefix)
            if dp:
                return parse_float(cfg, section, f"{dp}.noise_stdev", default=0.0) or 0.0
    return 0.0


def format_pca_twamp_csv_metric(_placeholder, value):
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
    prefix_base = f"{stream['index']}#{stream['sourcetype']}#"
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

            # Template may omit *_rxpkts_expected / *_rxpkts_drop_rate; resolve from conf.
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
        # Sample templates use {{timestamp}} as a domain timestamp string; it must reflect
        # the selected workshop region's local wall time (not UTC), with a short TZ suffix.
        return format_domain_timestamp(local_dt, region)
    if placeholder == "startTime":
        return format_domain_timestamp(local_dt, region)
    if placeholder == "sequence":
        return sequence
    if placeholder == "sourcetype":
        return stream["sourcetype"]
    if placeholder == "intervalms":
        ib = f"{stream['index']}#{stream['sourcetype']}#"
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


def generate_stream(
    cfg, stream, start_ts, end_ts, tzinfo, region, sequence_start, twamp_ul_last_state
):
    section = "baseline"
    prefix_base = f"{stream['index']}#{stream['sourcetype']}#"
    interval = parse_int(cfg, section, f"{prefix_base}interval", default=1)
    interval = max(interval or 1, 1)
    event_interval_sec = parse_int(
        cfg, section, f"{prefix_base}event_interval_sec", default=None
    )
    if event_interval_sec is not None and event_interval_sec <= 0:
        event_interval_sec = None
    if event_interval_sec:
        step = int(event_interval_sec)
    else:
        step = interval * 60

    with open(stream["sample"], "r") as f:
        full_template_text = f.read()

    output_ext = sample_extension(stream["sample"])
    csv_header_line = None
    if output_ext == ".csv":
        csv_header_line, template_text = csv_header_and_body(
            full_template_text, stream["sample"]
        )
    else:
        template_text = full_template_text

    placeholders = sorted(set(PLACEHOLDER_RE.findall(template_text)))
    telemetry_placeholder_index = {}
    telemetry_links = []
    if stream["index"] == "telemetry" and stream["sourcetype"] == "cnc_interface_counter_json":
        telemetry_placeholder_index = index_telemetry_placeholders(placeholders)
        telemetry_links = load_telemetry_bidirectional_links()
    os.makedirs(stream["spool_dir"], exist_ok=True)
    output_path = os.path.join(
        stream["spool_dir"],
        f"backfill_{int(time.time() * 1_000_000)}_{os.getpid()}_{stream['index']}_{stream['sourcetype'].replace(':', '_')}{output_ext}",
    )

    sequence = int(sequence_start) + 1
    count = 0
    telemetry_rate_state = {}
    yield_chunk = int(os.environ.get("AI_LAB_BACKFILL_YIELD_EVERY", "200"))
    yield_sleep = float(os.environ.get("AI_LAB_BACKFILL_YIELD_SLEEP_SEC", "0.002"))
    csv_header_written = False
    with open(output_path, "w") as out:
        for ts_index, ts in enumerate(range(start_ts, end_ts, step)):
            if (
                yield_chunk > 0
                and ts_index > 0
                and ts_index % yield_chunk == 0
                and yield_sleep > 0
            ):
                time.sleep(yield_sleep)
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
            if telemetry_links:
                enforce_telemetry_directional_conservation(
                    replacements, telemetry_placeholder_index, telemetry_links, cfg, section
                )
            apply_twamp_ul_packet_sequence(
                replacements, stream, twamp_ul_last_state, cfg, section, local_dt
            )
            if stream.get("sourcetype") == "pca_twamp_csv":
                normalize_pca_twamp_csv_replacements(replacements)
            payloads = render_template(template_text, replacements, stream["sample"])
            for payload in payloads:
                if csv_header_line is not None and not csv_header_written:
                    out.write(csv_header_line + "\n")
                    csv_header_written = True
                out.write(payload)
                if not payload.endswith("\n"):
                    out.write("\n")
                count += 1
            sequence += 1

    step_note = (
        f" step_sec={event_interval_sec}"
        if event_interval_sec
        else f" step_sec={interval * 60}"
    )
    print(
        f"backfill_log: wrote {count} events to {output_path} "
        f"(index={stream['index']} sourcetype={stream['sourcetype']}{step_note})",
        flush=True,
    )
    write_generation_log(
        "stream_written",
        index=stream["index"],
        sourcetype=stream["sourcetype"],
        events=count,
        output_path=output_path,
    )
    return sequence - 1


def mark_backfill_completed():
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    now = str(int(time.time()))
    local_cfg.set("baseline", "backfill_completed", "true")
    local_cfg.set("baseline", "backfill_completed_time", now)
    write_local_conf(local_cfg)


def record_backfill_run_started():
    """Wall-clock start of this backfill_log process (for duration vs. data anchor time)."""
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    local_cfg.set("baseline", "backfill_run_started_time", str(int(time.time())))
    write_local_conf(local_cfg)


def main():
    _apply_sandbox_env()

    cfg = read_effective_conf()

    start_anchor = parse_int(cfg, "baseline", "backfill_start_time", default=None)
    if start_anchor is None:
        print("backfill_log: missing baseline.backfill_start_time; skipping", flush=True)
        write_generation_log("skip_missing_backfill_start_time")
        return

    completed = cfg.get("baseline", "backfill_completed", fallback="false").strip().lower()
    if completed == "true":
        print("backfill_log: already completed; skipping", flush=True)
        write_generation_log("skip_already_completed")
        return

    sandbox_min_raw = os.environ.get("AI_LAB_SANDBOX_WINDOW_MINUTES", "").strip()
    if sandbox_min_raw:
        try:
            sandbox_minutes = max(1, int(sandbox_min_raw))
        except ValueError:
            sandbox_minutes = 5
        end_ts = int(start_anchor)
        start_ts = end_ts - sandbox_minutes * 60
        backfill_days = 0
        print(
            f"backfill_log: sandbox window AI_LAB_SANDBOX_WINDOW_MINUTES={sandbox_minutes} "
            f"-> start={start_ts} end={end_ts}",
            flush=True,
        )
    else:
        backfill_days = parse_int(cfg, "baseline", "backfill_days", default=7) or 7
        start_ts = start_anchor - (backfill_days * 86400)
        end_ts = start_anchor

    tzinfo, region = get_region_tz(cfg)
    print(
        f"backfill_log: starting backfill window start={start_ts} end={end_ts} "
        f"days={backfill_days} region={region} tz={tzinfo.key}",
        flush=True,
    )
    write_generation_log(
        "start",
        backfill_start_time=start_anchor,
        start_ts=start_ts,
        end_ts=end_ts,
        backfill_days=backfill_days,
        region=region,
        timezone=tzinfo.key,
    )

    record_backfill_run_started()

    last_sequence = load_last_sequence()
    twamp_ul_last_state = load_twamp_ul_last_state()
    for stream in build_streams():
        last_sequence = generate_stream(
            cfg,
            stream,
            start_ts,
            end_ts,
            tzinfo,
            region,
            last_sequence,
            twamp_ul_last_state,
        )
    persist_last_sequence(last_sequence)
    persist_twamp_ul_last_state(twamp_ul_last_state)

    mark_backfill_completed()
    print("backfill_log: completed", flush=True)
    write_generation_log(
        "completed",
        backfill_start_time=start_anchor,
        start_ts=start_ts,
        end_ts=end_ts,
        backfill_days=backfill_days,
        region=region,
        timezone=tzinfo.key,
    )


if __name__ == "__main__":
    main()
