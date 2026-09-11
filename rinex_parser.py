import gzip
import re

###############################################
# Chargement RINEX / CRINEX
###############################################

def load_rinex(path):
    if path.endswith(".gz"):
        with gzip.open(path, "rt", errors="ignore") as f:
            return f.readlines()
    else:
        with open(path, "r", errors="ignore") as f:
            return f.readlines()

###############################################
# Parsing de l'entête RINEX
###############################################

def parse_header(lines):
    header = {
        "version": None,
        "sat_system": None,
        "obs_types": [],
        "interval": None
    }

    for line in lines:
        if "RINEX VERSION" in line:
            header["version"] = float(line[:9])
            header["sat_system"] = line[40].strip()

        if "SYS / # / OBS TYPES" in line:
            parts = line.split()
            sys = parts[0]
            count = int(parts[1])
            types = parts[2:]
            header["obs_types"].append((sys, types))

        if "INTERVAL" in line:
            try:
                header["interval"] = float(line.split()[0])
            except:
                pass

        if "END OF HEADER" in line:
            break

    return header

###############################################
# Parsing des epochs + satellites
###############################################

epoch_regex = re.compile(r"> (\d{4}) (\d{2}) (\d{2}) (\d{2}) (\d{2}) (\d{2}\.\d+)")

def parse_epochs(lines):
    epochs = []
    current_epoch = None

    for line in lines:
        if line.startswith(">"):
            m = epoch_regex.match(line)
            if m:
                year, month, day, hour, minute, sec = m.groups()
                current_epoch = {
                    "time": f"{year}-{month}-{day} {hour}:{minute}:{sec}",
                    "sats": []
                }
                epochs.append(current_epoch)

        elif current_epoch and line[:1] in ("G", "R", "E", "C"):
            sat = line[:3].strip()
            current_epoch["sats"].append(sat)

    return epochs

###############################################
# Extraction des métriques GNSS
###############################################

def extract_metrics(lines):
    satellites_seen = set()
    observations = 0
    cycle_slips = 0
    snr_values = []

    for line in lines:
        if line[:1] in ("G", "R", "E", "C"):
            satellites_seen.add(line[:3].strip())

        if "SNR" in line.upper():
            parts = line.split()
            try:
                snr_values.append(float(parts[-1]))
            except:
                pass

        if "SLIP" in line.upper():
            cycle_slips += 1

        observations += 1

    snr_avg = sum(snr_values) / len(snr_values) if snr_values else None

    return {
        "satellites": len(satellites_seen),
        "observations": observations,
        "cycle_slips": cycle_slips,
        "snr_avg": snr_avg
    }

###############################################
# Fonction principale
###############################################

def parse_rinex_file(path):
    lines = load_rinex(path)
    header = parse_header(lines)
    epochs = parse_epochs(lines)
    metrics = extract_metrics(lines)

    return {
        "header": header,
        "epochs": epochs,
        "metrics": metrics
    }
