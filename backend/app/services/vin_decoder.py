"""VIN decoder and validator — deterministic, no AI dependency.

Decodes 17-character VINs to extract manufacturer, model year, country
of origin, and right-hand-drive status for Australian compliance purposes.
"""
import re

VIN_PATTERN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")

WMI_MAP: dict[str, tuple[str, str]] = {
    "JNA": ("Nissan", "Japan"),
    "JN1": ("Nissan", "Japan"),
    "JNK": ("Nissan", "Japan"),
    "JNR": ("Nissan", "Japan"),
    "JTE": ("Toyota", "Japan"),
    "JT2": ("Toyota", "Japan"),
    "JT3": ("Toyota", "Japan"),
    "JT4": ("Toyota", "Japan"),
    "JTD": ("Toyota", "Japan"),
    "JZZ": ("Toyota", "Japan"),
    "JMB": ("Mitsubishi", "Japan"),
    "JMZ": ("Mazda", "Japan"),
    "JMA": ("Mazda", "Japan"),
    "JF1": ("Subaru", "Japan"),
    "JF2": ("Subaru", "Japan"),
    "JHL": ("Honda", "Japan"),
    "JH2": ("Honda", "Japan"),
    "JH3": ("Honda", "Japan"),
    "JS1": ("Suzuki", "Japan"),
    "JYA": ("Yamaha", "Japan"),
    "1G1": ("Chevrolet", "USA"),
    "1G6": ("Cadillac", "USA"),
    "1GC": ("Chevrolet", "USA"),
    "1GM": ("Pontiac", "USA"),
    "1FT": ("Ford", "USA"),
    "1FA": ("Ford", "USA"),
    "1FD": ("Ford", "USA"),
    "1HD": ("Harley-Davidson", "USA"),
    "1HG": ("Honda", "USA"),
    "1J4": ("Jeep", "USA"),
    "1J8": ("Jeep", "USA"),
    "2C3": ("Chrysler", "USA"),
    "2D4": ("Dodge", "USA"),
    "3VW": ("Volkswagen", "USA"),
    "WBA": ("BMW", "Germany"),
    "WBS": ("BMW M", "Germany"),
    "WDB": ("Mercedes-Benz", "Germany"),
    "WDD": ("Mercedes-Benz", "Germany"),
    "WVW": ("Volkswagen", "Germany"),
    "WV1": ("Volkswagen Commercial", "Germany"),
    "WF0": ("Ford", "Germany"),
    "SAJ": ("Jaguar", "UK"),
    "SAR": ("Rover", "UK"),
    "SCC": ("Lotus", "UK"),
    "VF1": ("Renault", "France"),
    "VF3": ("Peugeot", "France"),
    "ZAR": ("Alfa Romeo", "Italy"),
    "ZFF": ("Ferrari", "Italy"),
    "SNT": ("Porsche", "Germany"),
}

YEAR_CODES: dict[str, int] = {
    "A": 2010, "B": 2011, "C": 2012, "D": 2013, "E": 2014,
    "F": 2015, "G": 2016, "H": 2017, "J": 2018, "K": 2019,
    "L": 2020, "M": 2021, "N": 2022, "P": 2023, "R": 2024,
    "S": 2025, "T": 2026, "V": 2027, "W": 2028, "X": 2029,
    "Y": 2030,
    "1": 2001, "2": 2002, "3": 2003, "4": 2004, "5": 2005,
    "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}

JAPANESE_MAKERS = {
    "Nissan", "Toyota", "Mitsubishi", "Mazda", "Subaru",
    "Honda", "Suzuki", "Yamaha", "Daihatsu", "Isuzu",
}

LHD_MAKERS = {
    "Chevrolet", "Cadillac", "Pontiac", "Ford", "Chrysler",
    "Dodge", "Jeep", "Harley-Davidson", "Renault", "Peugeot",
    "Alfa Romeo", "Ferrari",
}

RHD_MAKERS = {
    "Nissan", "Toyota", "Mitsubishi", "Mazda", "Subaru",
    "Honda", "Suzuki", "Yamaha", "Daihatsu", "Isuzu",
    "Jaguar", "Rover", "Lotus",
}

COUNTRY_CODES: dict[str, str] = {
    "J": "Japan", "1": "USA", "2": "Canada", "3": "Mexico",
    "4": "USA", "5": "USA", "W": "Germany", "S": "UK",
    "V": "France/Spain", "T": "Switzerland", "Z": "Italy",
    "K": "South Korea", "L": "China", "M": "India/Thailand",
    "Y": "Sweden/Finland",
}

VDW_POSITIONS = {
    0: "A", 1: "B", 2: "C", 3: "D", 4: "E", 5: "F", 6: "G", 7: "H",
    8: "J", 9: "K", 10: "L", 11: "M", 12: "N", 13: "P", 14: "R", 15: "S", 16: "T",
}

CHECK_DIGITS = {0: "0", 1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7",
                8: "8", 9: "9", 10: "X"}


def validate_vin(vin: str) -> tuple[bool, list[str]]:
    """Validate a VIN per ISO 3779 with Australian-specific heuristics.

    Returns (is_valid, errors).
    """
    errors: list[str] = []
    vin = vin.upper().strip()

    if not vin:
        errors.append("VIN is required")
        return False, errors

    if len(vin) != 17:
        errors.append(f"VIN must be 17 characters, got {len(vin)}")
        return False, errors

    invalid = [c for c in vin if c not in "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"]
    if invalid:
        errors.append(f"VIN contains invalid characters (I, O, Q not allowed): {invalid}")

    wmi = vin[:3]
    if wmi not in WMI_MAP:
        errors.append(f"Unknown WMI prefix '{wmi}' — manufacturer not in database")

    year_code = vin[9]
    if year_code not in YEAR_CODES:
        errors.append(f"Invalid model year code '{year_code}' at position 10")

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_check_digit(vin: str) -> bool:
    """Validate the VIN check digit (position 9) per ISO 3779 transliteration."""
    vin = vin.upper().strip()
    if len(vin) != 17 or not VIN_PATTERN.match(vin):
        return False

    # ISO 3779 transliteration table — letters map to numeric values
    # A=1 B=2 C=3 D=4 E=5 F=6 G=7 H=8 J=1 K=2 L=3 M=4 N=5 P=7 R=9 S=2 T=3 U=4 V=5 W=6 X=7 Y=8 Z=9
    translit_map = {
        "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
        "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7,
        "R": 9, "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
    }

    translit = []
    for ch in vin:
        if ch.isdigit():
            translit.append(int(ch))
        else:
            translit.append(translit_map.get(ch, 0))

    weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]
    weighted_sum = sum(t * w for t, w in zip(translit, weights)) % 11
    expected = CHECK_DIGITS.get(weighted_sum)
    return vin[8] == expected


def decode_vin(vin: str) -> dict:
    """Decode a 17-character VIN into structured data.

    Returns a dict with: vin, wmi, vds, year, country, manufacturer, rhd.
    """
    vin = vin.upper().strip()
    if len(vin) != 17:
        raise ValueError(f"VIN must be 17 characters, got {len(vin)}")
    if not VIN_PATTERN.match(vin):
        raise ValueError("VIN contains invalid characters (I, O, Q not allowed)")

    wmi = vin[:3]
    vds = vin[3:9]
    year = YEAR_CODES.get(vin[9])
    country = WMI_MAP.get(wmi, (None, COUNTRY_CODES.get(vin[0], "Unknown")))[1]
    manufacturer = WMI_MAP.get(wmi, (None, None))[0]

    rhd = None
    if manufacturer:
        if manufacturer in JAPANESE_MAKERS or manufacturer in RHD_MAKERS:
            rhd = True
        elif manufacturer in LHD_MAKERS:
            rhd = False
        elif country == "UK":
            rhd = True

    return {
        "vin": vin,
        "wmi": wmi,
        "vds": vds,
        "year": year,
        "country": country,
        "manufacturer": manufacturer,
        "is_right_hand_drive": rhd,
    }


def estimate_vehicle_age_years(year_of_manufacture: int, reference_year: int = 2026) -> int:
    return reference_year - year_of_manufacture
