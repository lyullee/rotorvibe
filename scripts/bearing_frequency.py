"""Resolve source-specific bearing coefficients into Hz. Python standard library only."""
import argparse
import json
import math
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / 'data/public_validation/metadata/bearing_frequency_catalog.json'


def geometry_orders(rolling_elements, rolling_diameter, pitch_diameter, contact_angle_deg=0):
    if rolling_elements < 1 or not 0 < rolling_diameter < pitch_diameter:
        raise ValueError('Invalid bearing geometry')
    ratio = rolling_diameter / pitch_diameter
    c = math.cos(math.radians(contact_angle_deg))
    bsf = (1 - (ratio * c) ** 2) / (2 * ratio)
    return {'BPFI': rolling_elements / 2 * (1 + ratio * c),
            'BPFO': rolling_elements / 2 * (1 - ratio * c),
            'FTF': (1 - ratio * c) / 2,
            'BSF': bsf, '2BSF': 2 * bsf}


def frequencies(profile, rpm):
    if not math.isfinite(rpm) or rpm <= 0:
        raise ValueError('RPM must be finite and positive')
    if 'orders' in profile:
        return {k: v * rpm / 60 for k, v in profile['orders'].items()}
    if 'hz_per_rpm' in profile:
        return {k: v * rpm for k, v in profile['hz_per_rpm'].items()}
    return {k: v * rpm / 60 for k, v in geometry_orders(**profile['geometry']).items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bearing', required=True, help='Catalog record id, e.g. cwru_de_skf_6205')
    parser.add_argument('--rpm', type=float, required=True)
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    match = next((r for r in catalog['bearings'] if r['id'] == args.bearing), None)
    if match is None:
        raise SystemExit('Unknown bearing id; inspect bearing_frequency_catalog.json')
    print(json.dumps({'bearing': args.bearing, 'rpm': args.rpm,
                      'shaft_hz': args.rpm / 60, 'frequencies_hz': frequencies(match,args.rpm),
                      'note': match.get('note')}, ensure_ascii=False,indent=2))
